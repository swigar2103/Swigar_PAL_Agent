"""Paper-based orchestrator: Diagnose → Plan → Retrieve → Generate → Validate → Assemble."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from swigar_core.models import (
    ExamPaper,
    LearnerProfile,
    LearningEvent,
    LearningEventType,
    PaperPlan,
    QuestionItem,
    SubmitAnswerResponse,
)
from swigar_skills.paper_plan import PaperPlanSkill
from swigar_skills.reserve_select import select_from_reserve
from swigar_skills.question_generate import QuestionGenerateSkill
from swigar_skills.question_retrieve import QuestionRetrieveSkill
from swigar_skills.question_validate import QuestionValidateSkill
from swigar_skills.mistake_review import MistakeReviewSkill
from swigar_skills.next_paper_adapt import NextPaperAdaptSkill
from swigar_skills.diagnosis import DiagnosisSkill
from swigar_skills.paper_assembly_validate import try_fix_paper_conflicts, validate_paper_assembly
from swigar_tools.error_pattern import infer_error_pattern
from swigar_tools.paper_builder import build_exam_paper, GENERATED_COUNT, PAPER_SIZE
from swigar_tools.question_similarity import check_duplicate_against_pool, check_duplicate_against_sources
from swigar_tools.registry import ToolRegistry

STEP_MODULE_MAP = {
    "paper_plan": "paper_plan",
    "retrieve_done": "retrieve",
    "generate_done": "generate",
    "validate_done": "validate",
    "mistake_review_done": "mistake_review",
    "mistake_review_empty": "mistake_review",
    "paper_validate_pass": "paper_validate",
    "paper_validate_revise": "paper_validate",
    "paper_validate_reject": "paper_validate",
    "llm_request": "llm",
    "llm_response": "llm",
}


class PaperOrchestrator:
    def __init__(
        self,
        tools: ToolRegistry | None = None,
        trace_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self.tools = tools or ToolRegistry()
        self._trace_callback = trace_callback
        self.plan_skill = PaperPlanSkill(self.tools)
        self.retrieve_skill = QuestionRetrieveSkill(self.tools)
        self.generate_skill = QuestionGenerateSkill(self.tools)
        self.validate_skill = QuestionValidateSkill(self.tools)
        self.mistake_skill = MistakeReviewSkill(self.tools)
        self.adapt_skill = NextPaperAdaptSkill()
        self.diagnosis_skill = DiagnosisSkill(self.tools)
        self._prefetch_tasks: dict[str, asyncio.Task] = {}
        self._trace_context: dict[str, Any] = {}

    def push_trace_context(self, **tags: Any) -> None:
        self._trace_context.update(tags)

    def pop_trace_context(self, *keys: str) -> None:
        for k in keys:
            self._trace_context.pop(k, None)

    def _merge_trace_data(self, data: dict | None) -> dict:
        payload = {**self._trace_context, **(data or {})}
        if "module" not in payload:
            payload["module"] = "orchestrator"
        return payload

    async def _trace(self, category: str, message: str, data: dict | None = None) -> None:
        if self._trace_callback:
            payload = self._merge_trace_data(data)
            await self._trace_callback(
                {
                    "kind": "workflow",
                    "category": category,
                    "message": message,
                    "data": payload,
                }
            )

    async def _emit_llm_trace(self, step: str, data: dict) -> None:
        if not self._trace_callback:
            return
        skill = data.get("skill", "")
        module = STEP_MODULE_MAP.get(step, skill or "llm")
        step_payload = {
            "step": step,
            "phase": "llm",
            "skill": skill,
            "module": module,
            **{k: v for k, v in data.items() if k != "skill"},
        }
        step_payload = {**self._trace_context, **step_payload}
        await self._trace_callback({"kind": "trace", "step": step_payload})

    def _schedule_trace(self, coro: Awaitable[None]) -> None:
        """Schedule trace coroutine from sync code (including LLM worker threads)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
            return
        except RuntimeError:
            pass
        loop = getattr(self, "_trace_loop", None)
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro, loop=loop))

    def _skill_trace(self, skill_module: str) -> Callable[[str, dict], None]:
        def cb(step: str, d: dict) -> None:
            if not self._trace_callback:
                return
            data = {**d, "skill": d.get("skill", skill_module)}
            try:
                if step.startswith("llm_"):
                    self._schedule_trace(self._emit_llm_trace(step, data))
                    return
                module = STEP_MODULE_MAP.get(step, skill_module)

                async def _wf() -> None:
                    await self._trace_callback(
                        {
                            "kind": "workflow",
                            "category": "出题",
                            "message": step,
                            "data": self._merge_trace_data({**data, "module": module}),
                        }
                    )

                self._schedule_trace(_wf())
            except Exception:
                pass

        return cb

    @staticmethod
    def _merge_exclude_ids(
        *parts: list[str] | set[str] | None,
    ) -> list[str] | None:
        merged: set[str] = set()
        for part in parts:
            if not part:
                continue
            merged.update(part)
        return list(merged) if merged else None

    def _collect_recent_errors(self, mistake_candidates: list[dict[str, Any]] | None) -> list[str]:
        errors: list[str] = []
        for c in mistake_candidates or []:
            ua = str(c.get("user_answer") or "").strip()
            if ua:
                errors.append(ua)
        return errors[:20]

    def _filter_mistakes_intra(
        self,
        items: list[QuestionItem],
        db_items: list[QuestionItem],
        trace: Callable | None,
    ) -> list[QuestionItem]:
        pool = [q.model_dump(mode="json") for q in db_items]
        kept: list[QuestionItem] = []
        for q in items:
            d = q.model_dump(mode="json")
            too, reason = check_duplicate_against_pool(d, pool)
            if too:
                if trace:
                    trace("mistake_skip_intra", {"id": q.id, "reason": reason})
                continue
            kept.append(q)
            pool.append(d)
        return kept

    @staticmethod
    def is_cold_start(profile: LearnerProfile) -> bool:
        return profile.total_answers == 0 and profile.papers_completed == 0

    async def _finalize_paper(
        self,
        paper: ExamPaper,
        plan: PaperPlan,
        profile: LearnerProfile,
        *,
        assembly_mode: str,
        error_pattern: dict,
        learner_level: int,
        t0: float,
        extra_trace: dict | None = None,
    ) -> ExamPaper:
        pv = await asyncio.to_thread(
            validate_paper_assembly,
            paper,
            plan,
            error_pattern=error_pattern,
            learner_level=learner_level,
        )
        rec = pv.get("recommendation", "accept")
        trace_pv = self._skill_trace("paper_validate")
        if trace_pv:
            trace_pv(f"paper_validate_{rec}", pv)

        if rec == "revise":
            paper = await asyncio.to_thread(
                try_fix_paper_conflicts,
                paper,
                pv.get("issues", []),
                plan=plan,
                tools=self.tools,
            )
            pv2 = await asyncio.to_thread(
                validate_paper_assembly,
                paper,
                plan,
                error_pattern=error_pattern,
                learner_level=learner_level,
            )
            rec = pv2.get("recommendation", rec)
            pv = pv2

        validation_meta = {
            "paper_score": pv.get("paper_score"),
            "issues": pv.get("issues"),
            "difficulty_path": pv.get("difficulty_path"),
            "recommendation": rec,
            "assembly_mode": assembly_mode,
            **(extra_trace or {}),
        }
        if rec == "reject":
            validation_meta["validation_warnings"] = pv.get("issues")
            await self._trace(
                "出题",
                f"卷级校验未通过，已降级收录（paper_score={pv.get('paper_score')}）",
                {"issues": pv.get("issues")[:8], "module": "paper_validate", "assembly_mode": assembly_mode},
            )
        else:
            await self._trace(
                "出题",
                f"卷级校验通过（paper_score={pv.get('paper_score')}）",
                {
                    "module": "paper_validate",
                    "error_targeted": pv.get("error_targeted_generated"),
                    "kp_distribution": pv.get("kp_distribution"),
                    "assembly_mode": assembly_mode,
                },
            )

        paper = paper.model_copy(update={"rationale": f"{paper.rationale} | paper_validation={rec}"})
        if paper.questions:
            paper.questions[0].generation_meta = {
                **(paper.questions[0].generation_meta or {}),
                "paper_validation": validation_meta,
            }

        duration = (time.perf_counter() - t0) * 1000
        await self._trace(
            "出题",
            f"试卷已生成（{paper.total_questions} 题）",
            {
                "paper_id": paper.paper_id,
                "duration_ms": duration,
                "module": "paper_out",
                "assembly_mode": assembly_mode,
                "ready_for_play": True,
                **(extra_trace or {}),
            },
        )
        if assembly_mode != "full_prefetch" and getattr(paper, "status", "active") == "active":
            await self._trace(
                "出题",
                "本卷已激活，可直接答题",
                {
                    "paper_id": paper.paper_id,
                    "module": "paper_out",
                    "assembly_mode": assembly_mode,
                    "ready_for_play": True,
                },
            )
        return paper

    async def generate_cold_start_paper(
        self,
        learner_id: str,
        session_id: str,
        profile: LearnerProfile,
        *,
        status: str = "active",
        history_exclude_ids: list[str] | None = None,
    ) -> ExamPaper:
        """First paper for new learners: rule plan + DB/fallback only (0 LLM)."""
        self._trace_loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        await self._trace(
            "出题",
            "冷启动组卷（题库快出，无 LLM）",
            {"learner_id": learner_id, "module": "orchestrator", "assembly_mode": "cold_start"},
        )
        plan = self.plan_skill._run_rules(profile, None)
        from swigar_tools.knowledge_clusters import apply_knowledge_mix, rotate_plan_if_mastered

        plan = rotate_plan_if_mastered(apply_knowledge_mix(plan), profile)
        exclude = self._merge_exclude_ids(history_exclude_ids)
        if exclude:
            await self._trace(
                "出题",
                f"跨卷排除近期答对题 {len(exclude)} 道",
                {"exclude_recent_count": len(exclude), "module": "retrieve"},
            )
        retrieve_trace = self._skill_trace("retrieve")
        db_items = await asyncio.to_thread(
            self.retrieve_skill.run,
            plan,
            exclude_ids=exclude,
            trace=retrieve_trace,
        )
        generated = await asyncio.to_thread(
            self.generate_skill._run_fallback,
            plan,
            db_items[:4] if db_items else [],
            GENERATED_COUNT,
            self._skill_trace("generate"),
        )
        learner_level = max(1, min(5, int(profile.current_level or 2)))
        error_pattern = infer_error_pattern([], profile.weak_points)
        paper = build_exam_paper(
            learner_id=learner_id,
            session_id=session_id,
            knowledge_point=plan.knowledge_point,
            db_questions=db_items,
            generated_questions=generated,
            mistake_questions=[],
            strategy=plan.strategy,
            rationale=f"{plan.rationale} | cold_start",
            status=status,  # type: ignore[arg-type]
        )
        return await self._finalize_paper(
            paper,
            plan,
            profile,
            assembly_mode="cold_start",
            error_pattern=error_pattern,
            learner_level=learner_level,
            t0=t0,
        )

    async def complete_paper_from_reserve(
        self,
        learner_id: str,
        session_id: str,
        profile: LearnerProfile,
        reserve_questions: list[QuestionItem],
        *,
        status: str = "active",
        last_accuracy: float | None = None,
        mistake_candidates: list[dict[str, Any]] | None = None,
        history_exclude_ids: list[str] | None = None,
    ) -> tuple[ExamPaper, list[dict[str, Any]], set[str]]:
        """Hybrid assembly: reserve + DB + LLM only for gaps. Returns paper, surplus, used_ids."""
        self._trace_loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        await self._trace(
            "出题",
            f"补卷组卷（reserve {len(reserve_questions)} 道候选）",
            {"learner_id": learner_id, "module": "orchestrator", "assembly_mode": "hybrid"},
        )

        learner_recent_errors = self._collect_recent_errors(mistake_candidates)
        error_pattern = infer_error_pattern(learner_recent_errors, profile.weak_points)
        learner_level = max(1, min(5, int(profile.current_level or 2)))

        plan_trace = self._skill_trace("paper_plan")
        plan, _ = await self.plan_skill.run(profile, last_accuracy, trace=plan_trace)

        history_set = set(history_exclude_ids or [])
        reserve_mistakes, reserve_generated = select_from_reserve(
            reserve_questions, plan, exclude_correct_ids=history_set
        )
        used_ids = {q.id for q in reserve_mistakes + reserve_generated}

        mistake_items: list[QuestionItem] = list(reserve_mistakes)
        if mistake_candidates and len(mistake_items) < 2:
            extra = await asyncio.to_thread(
                self.mistake_skill.run,
                mistake_candidates,
                trace=self._skill_trace("mistake_review"),
            )
            for q in extra:
                if q.id not in used_ids:
                    mistake_items.append(q)
                    used_ids.add(q.id)
                if len(mistake_items) >= 2:
                    break

        exclude = self._merge_exclude_ids(list(used_ids), history_exclude_ids)
        if history_set:
            await self._trace(
                "出题",
                f"跨卷排除近期答对题 {len(history_set)} 道",
                {"exclude_recent_count": len(history_set), "module": "retrieve"},
            )
        retrieve_trace = self._skill_trace("retrieve")
        db_items = await asyncio.to_thread(
            self.retrieve_skill.run,
            plan,
            exclude_ids=exclude,
            trace=retrieve_trace,
        )
        for q in db_items:
            used_ids.add(q.id)

        generated = list(reserve_generated)
        gap_gen = max(0, GENERATED_COUNT - len(generated))
        surplus_raw: list[dict[str, Any]] = []
        if gap_gen > 0:
            llm_gen = await self.generate_skill.run(
                plan,
                db_items,
                count=gap_gen,
                trace=self._skill_trace("generate"),
                learner_recent_errors=learner_recent_errors,
                weak_points=profile.weak_points,
                surplus_out=surplus_raw,
            )
            for q in llm_gen:
                if q.id not in used_ids:
                    generated.append(q)
                    used_ids.add(q.id)

        if mistake_items:
            mistake_items = self._filter_mistakes_intra(
                mistake_items, db_items, self._skill_trace("mistake_review")
            )

        validate_trace = self._skill_trace("validate")
        passed, failed = await asyncio.to_thread(
            functools.partial(
                self.validate_skill.run,
                generated,
                plan.knowledge_point,
                trace=validate_trace,
                source_questions=db_items,
                learner_level=learner_level,
                learner_recent_errors=learner_recent_errors,
                weak_points=profile.weak_points,
            )
        )
        if failed and len(passed) < gap_gen:
            fallback = await asyncio.to_thread(
                self.retrieve_skill.run,
                plan,
                exclude_ids=self._merge_exclude_ids(list(used_ids), history_exclude_ids),
                trace=retrieve_trace,
            )
            seed_dicts = [q.model_dump(mode="json") for q in db_items]
            pool = seed_dicts + [q.model_dump(mode="json") for q in passed]
            for fb in fallback:
                if len(passed) >= GENERATED_COUNT:
                    break
                ok, _ = self.validate_skill._rule_check(fb, plan.knowledge_point, learner_level)
                if not ok:
                    continue
                d = fb.model_dump(mode="json")
                too_sim, _ = check_duplicate_against_sources(d, seed_dicts)
                too_intra, _ = check_duplicate_against_pool(d, pool)
                if too_sim or too_intra:
                    continue
                fb.source = "generated"
                passed.append(fb)
                pool.append(d)

        paper = build_exam_paper(
            learner_id=learner_id,
            session_id=session_id,
            knowledge_point=plan.knowledge_point,
            db_questions=db_items,
            generated_questions=passed,
            mistake_questions=mistake_items,
            strategy=plan.strategy,
            rationale=f"{plan.rationale} | hybrid",
            status=status,  # type: ignore[arg-type]
        )
        paper = await self._finalize_paper(
            paper,
            plan,
            profile,
            assembly_mode="hybrid",
            error_pattern=error_pattern,
            learner_level=learner_level,
            t0=t0,
            extra_trace={"reserve_used": len(reserve_mistakes) + len(reserve_generated), "gap_gen": gap_gen},
        )
        return paper, surplus_raw, used_ids

    async def generate_paper(
        self,
        learner_id: str,
        session_id: str,
        profile: LearnerProfile,
        *,
        status: str = "active",
        last_accuracy: float | None = None,
        mistake_candidates: list[dict[str, Any]] | None = None,
        surplus_out: list[dict[str, Any]] | None = None,
        history_exclude_ids: list[str] | None = None,
    ) -> ExamPaper:
        self._trace_loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        phase = "预生成下一卷" if status == "queued" else "当前卷"
        assembly_mode = "full_prefetch" if status == "queued" else "full"
        await self._trace(
            "出题",
            f"开始组卷（{phase}）",
            {
                "learner_id": learner_id,
                "session_id": session_id,
                "module": "orchestrator",
                "paper_status": status,
                "assembly_mode": assembly_mode,
            },
        )

        learner_recent_errors = self._collect_recent_errors(mistake_candidates)
        error_pattern = infer_error_pattern(learner_recent_errors, profile.weak_points)
        learner_level = max(1, min(5, int(profile.current_level or 2)))

        plan_trace = self._skill_trace("paper_plan")
        plan, _ = await self.plan_skill.run(profile, last_accuracy, trace=plan_trace)
        await self._trace(
            "出题",
            f"选定知识点：{plan.knowledge_point}",
            {
                "strategy": plan.strategy,
                "rationale": plan.rationale,
                "module": "paper_plan",
                "knowledge_cluster_id": plan.knowledge_cluster_id,
                "related_knowledge_points": [
                    r.knowledge_point for r in plan.related_knowledge_points
                ],
            },
        )

        mistake_items: list[QuestionItem] = []
        if mistake_candidates:
            mistake_items = await asyncio.to_thread(
                self.mistake_skill.run,
                mistake_candidates,
                trace=self._skill_trace("mistake_review"),
            )

        exclude = self._merge_exclude_ids([q.id for q in mistake_items], history_exclude_ids)
        if history_exclude_ids:
            await self._trace(
                "出题",
                f"跨卷排除近期答对题 {len(history_exclude_ids)} 道",
                {"exclude_recent_count": len(history_exclude_ids), "module": "retrieve"},
            )
        retrieve_trace = self._skill_trace("retrieve")
        db_items = await asyncio.to_thread(
            self.retrieve_skill.run,
            plan,
            exclude_ids=exclude,
            trace=retrieve_trace,
        )
        await self._trace(
            "出题",
            f"已从题库选取 {len(db_items)} 道真题",
            {
                "ids": [q.id for q in db_items],
                "module": "retrieve",
                "exclude_recent_count": len(history_exclude_ids or []),
            },
        )

        if mistake_items:
            mistake_items = self._filter_mistakes_intra(
                mistake_items, db_items, self._skill_trace("mistake_review")
            )
            if mistake_items:
                await self._trace(
                    "出题",
                    f"混入 {len(mistake_items)} 道往期错题（卷内去重后）",
                    {"ids": [q.id for q in mistake_items], "module": "mistake_review"},
                )

        generate_trace = self._skill_trace("generate")
        generated = await self.generate_skill.run(
            plan,
            db_items,
            trace=generate_trace,
            learner_recent_errors=learner_recent_errors,
            weak_points=profile.weak_points,
            surplus_out=surplus_out,
        )
        if generated:
            await self._trace("出题", f"LLM 已生成 {len(generated)} 道 AI 变式题", {"module": "generate"})
        else:
            await self._trace("出题", "LLM 未返回变式题（超时或解析失败），改用题库变式", {"module": "generate"})

        validate_trace = self._skill_trace("validate")
        passed, failed = await asyncio.to_thread(
            functools.partial(
                self.validate_skill.run,
                generated,
                plan.knowledge_point,
                trace=validate_trace,
                source_questions=db_items,
                learner_level=learner_level,
                learner_recent_errors=learner_recent_errors,
                weak_points=profile.weak_points,
            )
        )
        if failed:
            reasons = [f"{q.id}:格式" for q in failed[:3]]
            await self._trace(
                "出题",
                f"格式校验未通过 {len(failed)} 题（多为答案与选项不一致），用题库替补",
                {"failed_ids": [q.id for q in failed], "hint": reasons, "module": "validate"},
            )
            fallback = await asyncio.to_thread(
                self.retrieve_skill.run,
                plan,
                exclude_ids=self._merge_exclude_ids(
                    [q.id for q in db_items + passed + mistake_items],
                    history_exclude_ids,
                ),
                trace=retrieve_trace,
            )
            seed_dicts = [q.model_dump(mode="json") for q in db_items]
            pool = seed_dicts + [q.model_dump(mode="json") for q in passed]
            for fb in fallback:
                if len(passed) >= 6:
                    break
                ok, _ = self.validate_skill._rule_check(fb, plan.knowledge_point, learner_level)
                if not ok:
                    continue
                d = fb.model_dump(mode="json")
                too_sim, _ = check_duplicate_against_sources(d, seed_dicts)
                too_intra, _ = check_duplicate_against_pool(d, pool)
                if too_sim or too_intra:
                    continue
                fb.source = "generated"
                passed.append(fb)
                pool.append(d)

        paper = build_exam_paper(
            learner_id=learner_id,
            session_id=session_id,
            knowledge_point=plan.knowledge_point,
            db_questions=db_items,
            generated_questions=passed,
            mistake_questions=mistake_items,
            strategy=plan.strategy,
            rationale=plan.rationale,
            status=status,  # type: ignore[arg-type]
        )

        return await self._finalize_paper(
            paper,
            plan,
            profile,
            assembly_mode=assembly_mode,
            error_pattern=error_pattern,
            learner_level=learner_level,
            t0=t0,
        )

    async def submit_answer(
        self,
        paper: ExamPaper,
        question_index: int,
        user_answer: str,
        time_spent_ms: int,
        profile: LearnerProfile | None = None,
    ) -> tuple[SubmitAnswerResponse, dict]:
        if question_index < 0 or question_index >= len(paper.questions):
            raise ValueError("invalid question_index")
        q = paper.questions[question_index]
        ev = self.tools.evaluator.evaluate(user_answer, q.correct_answer, q.model_dump())
        is_correct = ev["is_correct"]
        if profile is not None:
            profile.total_answers += 1
            if is_correct:
                profile.total_correct += 1

        effect = "boost" if is_correct else "penalty"
        paper_finished = question_index >= len(paper.questions) - 1
        record = {
            "paper_id": paper.paper_id,
            "question_index": question_index,
            "question_id": q.id,
            "user_answer": user_answer,
            "is_correct": is_correct,
            "time_spent_ms": time_spent_ms,
        }
        resp = SubmitAnswerResponse(
            is_correct=is_correct,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
            feedback=ev["feedback"],
            effect_hint=effect,  # type: ignore[arg-type]
            question_index=question_index,
            paper_finished=paper_finished,
        )
        return resp, record

    def schedule_prefetch(self, key: str, coro: Awaitable[ExamPaper]) -> None:
        if key in self._prefetch_tasks and not self._prefetch_tasks[key].done():
            return
        self._prefetch_tasks[key] = asyncio.create_task(coro)  # type: ignore[arg-type]
