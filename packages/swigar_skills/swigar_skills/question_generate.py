"""Generate AI variant questions: analyse → plan → over-generate → filter → rank → select."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable
from uuid import uuid4

from swigar_core.models import PaperPlan, QuestionItem
from swigar_tools.error_pattern import infer_error_pattern
from swigar_tools.knowledge_clusters import (
    allowed_knowledge_points,
    kp_mix_enabled,
    kp_slot_plan_for_generation,
    min_distinct_kp,
)
from swigar_tools.llm_prompts import (
    QUESTION_ANALYSE_SYSTEM,
    QUESTION_OVERGENERATE_SYSTEM,
    QUESTION_TRANSFORM_PLAN_SYSTEM,
)
from swigar_tools.paper_builder import GENERATED_COUNT
from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer
from swigar_tools.question_revise import revise_candidate_once
from swigar_tools.question_scoring import score_candidate
from swigar_tools.question_similarity import (
    check_duplicate_against_pool,
    check_duplicate_against_sources,
    select_diverse_candidates,
)

_VARIATION_SLOTS = ("G1", "G2", "G3", "G4", "G5", "G6")


def _candidate_count() -> int:
    return max(12, min(24, int(os.environ.get("SWIGAR_GENERATE_CANDIDATE_COUNT", "20"))))


def _min_error_targeted() -> int:
    return max(1, min(6, int(os.environ.get("SWIGAR_MIN_ERROR_TARGETED_GENERATED", "3"))))


def _max_revise_candidates() -> int:
    return max(0, min(8, int(os.environ.get("SWIGAR_MAX_REVISE_CANDIDATES", "2"))))


class QuestionGenerateSkill:
    def __init__(self, tools):
        self.tools = tools

    async def run(
        self,
        plan: PaperPlan,
        seeds: list[QuestionItem],
        count: int = GENERATED_COUNT,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        learner_recent_errors: list[str] | None = None,
        weak_points: list[str] | None = None,
        surplus_out: list[dict[str, Any]] | None = None,
    ) -> list[QuestionItem]:
        if self.tools.llm.is_configured and seeds:
            items = await self._run_pipeline(
                plan,
                seeds,
                count,
                trace,
                learner_recent_errors=learner_recent_errors,
                weak_points=weak_points,
                surplus_out=surplus_out,
            )
            if items:
                return items
        return self._run_fallback(
            plan,
            seeds,
            count,
            trace,
            learner_recent_errors=learner_recent_errors,
            weak_points=weak_points,
        )

    def _trace_step(
        self, trace: Callable[[str, dict[str, Any]], None] | None, step: str, data: dict
    ) -> None:
        if trace:
            trace(step, {**data, "skill": "question_generate"})

    async def _run_pipeline(
        self,
        plan: PaperPlan,
        seeds: list[QuestionItem],
        count: int,
        trace: Callable[[str, dict[str, Any]], None] | None,
        *,
        learner_recent_errors: list[str] | None = None,
        weak_points: list[str] | None = None,
        surplus_out: list[dict[str, Any]] | None = None,
    ) -> list[QuestionItem]:
        seed_dicts = [s.model_dump(mode="json") for s in seeds[:4]]
        base_n = _candidate_count()
        n_candidates = base_n if count >= GENERATED_COUNT else max(6, min(base_n, count * 4))
        error_pattern = infer_error_pattern(learner_recent_errors or [], weak_points)
        min_targeted = _min_error_targeted()
        allowed_kps = allowed_knowledge_points(plan)
        kp_slots = kp_slot_plan_for_generation(plan) if kp_mix_enabled() else []
        slot_to_kp = {s["slot"]: s["knowledge_point"] for s in kp_slots}

        analyse_payload = {
            "target_knowledge_point": plan.knowledge_point,
            "primary_knowledge_point": plan.knowledge_point,
            "related_knowledge_points": [
                r.model_dump(mode="json") for r in plan.related_knowledge_points
            ],
            "allowed_knowledge_points": allowed_kps,
            "learner_level": plan.target_level_max,
            "seeds": seed_dicts,
            "learner_recent_errors": (learner_recent_errors or [])[:12],
            "inferred_error_pattern": error_pattern,
        }

        def _t(step: str, d: dict) -> None:
            if trace:
                trace(step, {**d, "skill": "question_generate"})

        analysis = await self.tools.llm.complete_json_async(
            system=QUESTION_ANALYSE_SYSTEM,
            user=json.dumps(analyse_payload, ensure_ascii=False, default=str),
            trace=_t,
        )
        self._trace_step(trace, "step1_analyse_sources", {"ok": bool(analysis)})
        if not analysis:
            return []

        slot_plan = [
            {"slot": s, "goal": _slot_goal(s)} for s in _VARIATION_SLOTS
        ]
        plan_payload = {
            "target_knowledge_point": plan.knowledge_point,
            "primary_knowledge_point": plan.knowledge_point,
            "related_knowledge_points": [
                r.model_dump(mode="json") for r in plan.related_knowledge_points
            ],
            "allowed_knowledge_points": allowed_kps,
            "kp_slot_plan": kp_slots,
            "source_analyses": analysis.get("source_analyses") or [],
            "skill_tags": plan.skill_tags,
            "target_levels": [plan.target_level_min, plan.target_level_max],
            "candidate_target_count": n_candidates,
            "variation_slots": slot_plan,
            "learner_recent_errors": (learner_recent_errors or [])[:12],
            "inferred_error_pattern": error_pattern,
        }
        transform_plan = await self.tools.llm.complete_json_async(
            system=QUESTION_TRANSFORM_PLAN_SYSTEM,
            user=json.dumps(plan_payload, ensure_ascii=False, default=str),
            trace=_t,
        )
        self._trace_step(trace, "step3_transformation_plan", {"ok": bool(transform_plan)})

        gen_payload_base = {
            "knowledge_point": plan.knowledge_point,
            "primary_knowledge_point": plan.knowledge_point,
            "related_knowledge_points": [
                r.model_dump(mode="json") for r in plan.related_knowledge_points
            ],
            "allowed_knowledge_points": allowed_kps,
            "kp_slot_plan": kp_slots,
            "skill_tags": plan.skill_tags,
            "target_levels": [plan.target_level_min, plan.target_level_max],
            "seeds": seed_dicts,
            "source_analyses": analysis.get("source_analyses") or [],
            "transformation_plan": (transform_plan or {}).get("transformation_plan") or [],
            "constraints": (transform_plan or {}).get("constraints") or [],
            "learner_recent_errors": (learner_recent_errors or [])[:12],
            "inferred_error_pattern": error_pattern,
            "min_error_targeted_count": min_targeted,
        }
        lanes = max(1, int(os.environ.get("SWIGAR_GENERATE_PARALLEL_LANES", "3")))
        lane_slots = [
            (["G1", "G2"], ["G1", "G2"]),
            (["G3", "G4"], ["G3", "G4"]),
            (["G5", "G6"], ["G5", "G6"]),
        ]
        raw_candidates: list[dict[str, Any]] = []
        if lanes >= 2 and n_candidates >= 8:
            per_lane = max(4, n_candidates // lanes)
            tasks = []
            for slots, slot_keys in lane_slots[:lanes]:
                lane_plan = [{"slot": s, "goal": _slot_goal(s)} for s in slot_keys]
                payload = {
                    **gen_payload_base,
                    "count": per_lane,
                    "variation_slots": lane_plan,
                }
                tasks.append(
                    self.tools.llm.complete_json_async(
                        system=QUESTION_OVERGENERATE_SYSTEM,
                        user=json.dumps(payload, ensure_ascii=False, default=str),
                        trace=_t,
                    )
                )
            overs = await asyncio.gather(*tasks)
            for over in overs:
                raw_candidates.extend(
                    (over or {}).get("candidates") or (over or {}).get("questions") or []
                )
            self._trace_step(
                trace,
                "step4_over_generate_parallel",
                {"raw_count": len(raw_candidates), "lanes": lanes},
            )
        else:
            gen_payload = {
                **gen_payload_base,
                "count": n_candidates,
                "variation_slots": slot_plan,
            }
            over = await self.tools.llm.complete_json_async(
                system=QUESTION_OVERGENERATE_SYSTEM,
                user=json.dumps(gen_payload, ensure_ascii=False, default=str),
                trace=_t,
            )
            raw_candidates = (over or {}).get("candidates") or (over or {}).get("questions") or []
            self._trace_step(trace, "step4_over_generate", {"raw_count": len(raw_candidates)})

        sources_for_check = seed_dicts
        filtered: list[dict[str, Any]] = []
        for c in raw_candidates:
            slot = str(c.get("variation_slot") or c.get("slot") or "")
            if slot and slot in slot_to_kp and not c.get("knowledge_point"):
                c["knowledge_point"] = slot_to_kp[slot]
            too_sim, reason = check_duplicate_against_sources(c, sources_for_check)
            if too_sim:
                if "structural" in reason.lower() or "frame" in reason.lower():
                    self._trace_step(
                        trace,
                        "step5b_structural_reject",
                        {"reason": reason, "stem": (c.get("prompt") or "")[:80]},
                    )
                else:
                    self._trace_step(
                        trace,
                        "step5_reject_duplicate",
                        {"reason": reason, "stem": (c.get("prompt") or "")[:80]},
                    )
                continue
            filtered.append(c)
        self._trace_step(
            trace,
            "step5_filter_duplicates",
            {"kept": len(filtered), "dropped": len(raw_candidates) - len(filtered)},
        )

        scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        revise_count = 0
        max_revises = _max_revise_candidates()
        for c in filtered:
            sc = score_candidate(
                c,
                sources_for_check,
                target_knowledge_point=plan.knowledge_point,
                target_level_min=plan.target_level_min,
                target_level_max=plan.target_level_max,
                error_pattern=error_pattern,
                learner_level=plan.target_level_max,
                allowed_knowledge_points=allowed_kps if kp_mix_enabled() else None,
            )
            decision = sc.get("final_decision", "reject")
            score_val = float(sc.get("score") or 0)

            if decision == "revise" and 70 <= score_val < 85 and revise_count < max_revises:
                revise_count += 1
                revised = await revise_candidate_once(
                    self.tools.llm,
                    c,
                    sc.get("failed_reasons", []),
                    sources_for_check,
                    trace=_t,
                )
                if revised:
                    c = revised
                    sc = score_candidate(
                        c,
                        sources_for_check,
                        target_knowledge_point=plan.knowledge_point,
                        target_level_min=plan.target_level_min,
                        target_level_max=plan.target_level_max,
                        error_pattern=error_pattern,
                        learner_level=plan.target_level_max,
                        allowed_knowledge_points=allowed_kps if kp_mix_enabled() else None,
                    )
                    decision = sc.get("final_decision", "reject")
                    score_val = float(sc.get("score") or 0)
                    self._trace_step(trace, "step6_revise_once", {"score": score_val, "decision": decision})

            self._trace_step(
                trace,
                "step6_score_candidate",
                {
                    "decision": decision,
                    "score": sc.get("score"),
                    "reasons": sc.get("failed_reasons"),
                    "stem": (c.get("prompt") or "")[:60],
                    "variation_slot": c.get("variation_slot"),
                },
            )
            if decision == "reject" or score_val < 70:
                continue
            c["_validation_score"] = sc
            scored.append((score_val, c, sc))

        gen_min_kp = min(2, min_distinct_kp()) if kp_mix_enabled() and plan.related_knowledge_points else 0
        selected_raw = select_diverse_candidates(
            scored,
            sources_for_check,
            count,
            min_distinct_kp=gen_min_kp,
            max_per_kp=4,
        )
        if len(selected_raw) < count:
            self._trace_step(trace, "step6b_intra_fill", {"have": len(selected_raw), "need": count})
            for score_val, c, _ in sorted(scored, key=lambda x: x[0], reverse=True):
                if len(selected_raw) >= count:
                    break
                too_intra, reason = check_duplicate_against_pool(c, selected_raw)
                if too_intra:
                    self._trace_step(
                        trace,
                        "step5c_intra_reject",
                        {"reason": reason, "stem": (c.get("prompt") or "")[:60]},
                    )
                    continue
                c_stem = str(c.get("prompt") or "").strip().lower()
                if not any(
                    c_stem == str(s.get("prompt") or "").strip().lower() for s in selected_raw
                ):
                    selected_raw.append(c)

        targeted = sum(
            1
            for c in selected_raw
            if (c.get("_validation_score") or {}).get("dimension_scores", {}).get(
                "learner_error_targeting", 0
            )
            >= 80
            or "error" in str(c.get("variation_strategy", "")).lower()
        )
        self._trace_step(
            trace,
            "step6_error_targeting",
            {"targeted_count": targeted, "min_required": min_targeted},
        )

        selected_ids = {str(c.get("id") or c.get("prompt", ""))[:80] for c in selected_raw}
        if surplus_out is not None:
            for score_val, c, sc in scored:
                if score_val < 70:
                    continue
                key = str(c.get("id") or c.get("prompt", ""))[:80]
                if key in selected_ids:
                    continue
                c_copy = dict(c)
                c_copy["_validation_score"] = sc
                surplus_out.append(c_copy)
                if len(surplus_out) >= 24:
                    break

        items = self._to_question_items(selected_raw, plan, count)
        items = self._apply_difficulty_gradient(items, count)
        self._trace_step(trace, "step7_select_final", {"selected": len(items), "target": count})
        return items[:count]

    def _to_question_items(
        self, raw_list: list[dict[str, Any]], plan: PaperPlan, count: int
    ) -> list[QuestionItem]:
        items: list[QuestionItem] = []
        for q in raw_list[: count * 2]:
            choices = normalize_choices(list(q.get("choices") or q.get("options") or []))
            correct = normalize_correct_answer(
                str(q.get("correct_answer") or q.get("answer") or ""), choices
            )
            sc = q.pop("_validation_score", None)
            meta = {
                "generated_from": q.get("generated_from") or [],
                "variation_strategy": q.get("variation_strategy") or [],
                "variation_slot": q.get("variation_slot") or q.get("slot"),
                "distractor_rationales": q.get("distractor_rationales") or {},
                "similarity_check": q.get("similarity_check"),
                "validation_status": "pending",
                "validation_score": sc,
            }
            items.append(
                QuestionItem(
                    id=f"gen_{uuid4().hex[:12]}",
                    source="generated",
                    skill_tags=list(q.get("skill_tags") or plan.skill_tags),
                    knowledge_point=str(q.get("knowledge_point") or plan.knowledge_point),
                    level=max(
                        1,
                        min(5, int(q.get("level") or q.get("difficulty") or plan.target_level_min)),
                    ),
                    prompt=str(q.get("prompt") or q.get("stem") or ""),
                    correct_answer=correct,
                    choices=choices,
                    explanation=str(q.get("explanation") or ""),
                    validation_status="pending",
                    generation_meta=meta,
                )
            )
        return items

    def _apply_difficulty_gradient(self, items: list[QuestionItem], count: int) -> list[QuestionItem]:
        if len(items) <= 1:
            return items
        items.sort(key=lambda q: q.level)
        targets = []
        n = min(count, len(items))
        for i in range(n):
            if i < 2:
                targets.append(1 if i == 0 else 2)
            elif i < 4:
                targets.append(2 if i == 2 else 3)
            else:
                targets.append(4 if i < n - 1 else 5)
        out: list[QuestionItem] = []
        used = set()
        for tgt in targets:
            best = None
            best_dist = 999
            for j, q in enumerate(items):
                if j in used:
                    continue
                d = abs(q.level - tgt)
                if d < best_dist:
                    best_dist = d
                    best = j
            if best is not None:
                used.add(best)
                q = items[best].model_copy(deep=True)
                q.level = tgt
                out.append(q)
        for j, q in enumerate(items):
            if j not in used and len(out) < count:
                out.append(q)
        return out

    def _run_fallback(
        self,
        plan: PaperPlan,
        seeds: list[QuestionItem],
        count: int,
        trace: Callable | None,
        *,
        learner_recent_errors: list[str] | None = None,
        weak_points: list[str] | None = None,
    ) -> list[QuestionItem]:
        items: list[QuestionItem] = []
        exclude = [s.id for s in seeds]
        seed_dicts = [s.model_dump(mode="json") for s in seeds]
        extra = self.tools.question_bank.find(
            skill_tags=plan.skill_tags,
            knowledge_point=plan.knowledge_point,
            exclude_ids=exclude,
            limit=count * 4,
        )
        pool: list[dict[str, Any]] = []
        for raw in extra:
            if len(items) >= count:
                break
            if isinstance(raw, QuestionItem):
                cand = raw.model_copy(deep=True)
            else:
                cand = QuestionItem.from_bank_dict(raw if isinstance(raw, dict) else raw.model_dump())
            d = cand.model_dump(mode="json")
            too_sim, reason = check_duplicate_against_sources(d, seed_dicts)
            if too_sim:
                if trace:
                    trace("fallback_reject", {"id": cand.id, "reason": reason})
                continue
            too_intra, _ = check_duplicate_against_pool(d, pool)
            if too_intra:
                continue
            cand.id = f"gen_fb_{uuid4().hex[:8]}"
            cand.source = "generated"
            cand.validation_status = "passed"
            cand.generation_meta = {"variation_strategy": ["bank_fallback_filtered"], "fallback": True}
            items.append(cand)
            pool.append(d)
        if trace:
            trace("generate_fallback", {"count": len(items)})
        return items


def _slot_goal(slot: str) -> str:
    return {
        "G1": "basic recognition",
        "G2": "short daily context",
        "G3": "contrast regular vs irregular",
        "G4": "short dialogue",
        "G5": "two-clause sentence",
        "G6": "mixed review / inference",
    }.get(slot, "variant practice")
