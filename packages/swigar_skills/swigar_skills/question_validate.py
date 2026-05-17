"""Validate generated questions (rules + similarity scoring + revise loop)."""

from __future__ import annotations

import json
from typing import Any, Callable

from swigar_core.models import QuestionItem
from swigar_tools.error_pattern import infer_error_pattern
from swigar_tools.llm_prompts import QUESTION_VALIDATE_SYSTEM
from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer
from swigar_tools.question_scoring import score_candidate
from swigar_tools.question_similarity import check_duplicate_against_sources
from swigar_tools.question_validation_rules import (
    check_answer_leakage,
    check_level_fit,
    check_option_category,
)


class QuestionValidateSkill:
    def __init__(self, tools):
        self.tools = tools

    def run(
        self,
        questions: list[QuestionItem],
        knowledge_point: str,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        source_questions: list[QuestionItem] | None = None,
        learner_level: int = 2,
        learner_recent_errors: list[str] | None = None,
        weak_points: list[str] | None = None,
    ) -> tuple[list[QuestionItem], list[QuestionItem]]:
        sources = [s.model_dump(mode="json") for s in (source_questions or [])]
        error_pattern = infer_error_pattern(learner_recent_errors or [], weak_points)
        passed: list[QuestionItem] = []
        failed: list[QuestionItem] = []

        for q in questions:
            result = self._validate_one(
                q,
                knowledge_point,
                sources,
                learner_level,
                error_pattern,
                trace,
            )
            if result:
                passed.append(result)
            else:
                failed.append(q)

        return passed, failed

    def _validate_one(
        self,
        q: QuestionItem,
        knowledge_point: str,
        sources: list[dict],
        learner_level: int,
        error_pattern: dict,
        trace: Callable | None,
    ) -> QuestionItem | None:
        q.choices = normalize_choices(list(q.choices))
        q.correct_answer = normalize_correct_answer(q.correct_answer, q.choices)

        ok, reason = self._rule_check(q, knowledge_point, learner_level)
        if not ok:
            q.validation_status = "failed"
            if trace:
                trace("validate_fail", {"id": q.id, "reason": reason})
            return None

        cand = q.model_dump(mode="json")
        if sources and q.source == "generated":
            too_sim, sim_reason = check_duplicate_against_sources(cand, sources)
            if too_sim:
                if trace:
                    trace("validate_fail_similarity", {"id": q.id, "reason": sim_reason})
                return None

        sc = score_candidate(
            cand,
            sources,
            target_knowledge_point=knowledge_point,
            target_level_min=1,
            target_level_max=5,
            error_pattern=error_pattern,
            learner_level=learner_level,
        )
        decision = sc.get("final_decision", "reject")

        q.generation_meta = {**(q.generation_meta or {}), "validation_score": sc}
        if decision == "revise":
            if sc.get("score", 0) >= 78:
                decision = "accept"
            else:
                if trace:
                    trace("validate_needs_revise", {"id": q.id, "score": sc.get("score")})
                return None
        if decision == "reject":
            if trace:
                trace(
                    "validate_reject_score",
                    {"id": q.id, "score": sc.get("score"), "reasons": sc.get("failed_reasons")},
                )
            return None

        q.validation_status = "passed"
        if trace:
            trace("validate_pass", {"id": q.id, "score": sc.get("score")})
        return q

    def _rule_check(
        self, q: QuestionItem, knowledge_point: str, learner_level: int
    ) -> tuple[bool, str]:
        if not q.prompt or not q.correct_answer:
            return False, "missing prompt or answer"
        if not q.choices or len(q.choices) < 2:
            return False, "need at least 2 choices"
        norm_correct = q.correct_answer.strip().lower()
        norms = [c.strip().lower() for c in q.choices]
        if norm_correct not in norms:
            return False, "correct_answer not in choices"
        if norms.count(norm_correct) > 1:
            return False, "ambiguous correct"

        leak, lr = check_answer_leakage(q.prompt, q.correct_answer, q.choices)
        if leak:
            return False, lr

        bad_cat, cr = check_option_category(q.choices)
        if bad_cat:
            return False, cr

        bad_lvl, lr2 = check_level_fit(q.prompt, q.level, learner_level)
        if bad_lvl:
            return False, lr2

        return True, ""

    def _llm_batch_review(self, questions, trace):
        payload = {"questions": [q.model_dump(mode="json") for q in questions]}

        def _t(step: str, d: dict) -> None:
            if trace:
                trace(step, {**d, "skill": "question_validate"})

        data = self.tools.llm.complete_json(
            system=QUESTION_VALIDATE_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False),
            trace=_t,
        )
        if not data:
            return
        if data.get("passed") is False:
            for q in questions:
                if q.source == "generated":
                    q.validation_status = "failed"
