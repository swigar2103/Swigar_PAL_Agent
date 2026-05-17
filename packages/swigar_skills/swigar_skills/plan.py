from __future__ import annotations

import json
from typing import Any, Callable

from swigar_core.models import DiagnosisResult, GoalRecord, PlanIntent
from swigar_tools.llm_prompts import PLAN_SYSTEM


class PlanSkill:
    def __init__(self, tools=None):
        self.tools = tools

    def run(
        self,
        diagnosis: DiagnosisResult,
        goals: list[GoalRecord],
        recent_mistakes: int = 0,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[PlanIntent, dict[str, Any]]:
        llm_result = self._run_llm(diagnosis, goals, recent_mistakes, trace)
        if llm_result is not None:
            return llm_result, {"source": "llm", "skill": "plan"}
        return self._run_rules(diagnosis, goals, recent_mistakes), {"source": "rules", "skill": "plan"}

    def _run_llm(
        self,
        diagnosis: DiagnosisResult,
        goals: list[GoalRecord],
        recent_mistakes: int,
        trace: Callable[[str, dict[str, Any]], None] | None,
    ) -> PlanIntent | None:
        if not self.tools or not self.tools.llm.is_configured:
            return None

        user_payload = {
            "diagnosis": diagnosis.model_dump(),
            "goals": [g.model_dump(mode="json") for g in goals],
            "recent_mistakes": recent_mistakes,
        }
        def _trace(step: str, data: dict) -> None:
            if trace:
                trace(step, {**data, "skill": "plan"})

        data = self.tools.llm.complete_json(
            system=PLAN_SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False, default=str),
            trace=_trace,
        )
        if not data:
            if self.tools.llm.fallback_on_error:
                return self._run_rules(diagnosis, goals, recent_mistakes)
            return None

        try:
            return PlanIntent.model_validate(data)
        except Exception:
            if self.tools.llm.fallback_on_error:
                return self._run_rules(diagnosis, goals, recent_mistakes)
            return None

    def _run_rules(
        self,
        diagnosis: DiagnosisResult,
        goals: list[GoalRecord],
        recent_mistakes: int,
    ) -> PlanIntent:
        goal_tags = []
        for g in goals:
            goal_tags.extend(g.skill_tags)

        if recent_mistakes >= 3 or (diagnosis.weaknesses and diagnosis.confidence > 0.7):
            skill = diagnosis.weaknesses[0]["skill_tag"] if diagnosis.weaknesses else "grammar.general"
            return PlanIntent(
                intent="review",
                skill_tags=[skill],
                difficulty="easier",
                rationale="Repeated mistakes or high-confidence weakness detected (rules)",
            )

        if goal_tags:
            pending = [g for g in goals if not g.completed]
            if pending:
                return PlanIntent(
                    intent="practice",
                    skill_tags=pending[0].skill_tags or goal_tags,
                    difficulty="same",
                    rationale=f"Working toward goal: {pending[0].title}",
                )

        if diagnosis.weaknesses:
            return PlanIntent(
                intent="practice",
                skill_tags=[diagnosis.weaknesses[0]["skill_tag"]],
                difficulty="same",
                rationale="Light practice on weakest skill (rules)",
            )

        return PlanIntent(
            intent="new_knowledge",
            skill_tags=["vocabulary.general"],
            difficulty="same",
            rationale="No urgent issues (rules)",
        )
