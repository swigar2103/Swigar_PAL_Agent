from __future__ import annotations

import json
from typing import Any, Callable

from swigar_core.models import DiagnosisResult, LearningSignal, LearningSituation
from swigar_tools.llm_prompts import DIAGNOSIS_SYSTEM


class DiagnosisSkill:
    def __init__(self, tools):
        self.tools = tools

    def run(
        self,
        signals: list[LearningSignal],
        situation: LearningSituation,
        memory_snippets: list[dict[str, Any]],
        kg_weaknesses: list[dict],
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[DiagnosisResult, dict[str, Any]]:
        llm_result = self._run_llm(signals, situation, memory_snippets, kg_weaknesses, trace)
        if llm_result is not None:
            return llm_result, {"source": "llm", "skill": "diagnosis"}
        return self._run_rules(signals, situation, kg_weaknesses), {"source": "rules", "skill": "diagnosis"}

    def _run_llm(
        self,
        signals: list[LearningSignal],
        situation: LearningSituation,
        memory_snippets: list[dict[str, Any]],
        kg_weaknesses: list[dict],
        trace: Callable[[str, dict[str, Any]], None] | None,
    ) -> DiagnosisResult | None:
        llm = self.tools.llm
        if not llm.is_configured:
            return None

        user_payload = {
            "signals": [s.model_dump(mode="json") for s in signals],
            "recent_events": [e.model_dump(mode="json") for e in situation.recent_events[-10:]],
            "memory_snippets": memory_snippets[:5],
            "kg_weaknesses": kg_weaknesses,
            "learner_state": situation.learner_state.model_dump(),
        }
        def _trace(step: str, data: dict) -> None:
            if trace:
                trace(step, {**data, "skill": "diagnosis"})

        data = llm.complete_json(
            system=DIAGNOSIS_SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False, default=str),
            trace=_trace,
        )
        if not data:
            return None if not llm.fallback_on_error else self._run_rules(signals, situation, kg_weaknesses)

        try:
            return DiagnosisResult.model_validate(data)
        except Exception:
            if llm.fallback_on_error:
                return self._run_rules(signals, situation, kg_weaknesses)
            return None

    def _run_rules(
        self,
        signals: list[LearningSignal],
        situation: LearningSituation,
        kg_weaknesses: list[dict],
    ) -> DiagnosisResult:
        weaknesses: list[dict[str, Any]] = []
        tag_counts: dict[str, float] = {}

        for sig in signals:
            if sig.signal_type.value.endswith("weakness"):
                tag_counts[sig.skill_tag] = tag_counts.get(sig.skill_tag, 0) + sig.confidence

        for row in kg_weaknesses:
            obj = row.get("object") if isinstance(row, dict) else str(row)
            tag = f"grammar.{obj}" if obj and "." not in obj else str(obj)
            tag_counts[tag] = tag_counts.get(tag, 0) + 0.5

        history = self.tools.evaluator.history_summary(
            [e.model_dump() for e in situation.recent_events]
        )
        for tag, count in history.get("wrong_counts", {}).items():
            tag_counts[tag] = tag_counts.get(tag, 0) + count * 0.3

        for tag, score in sorted(tag_counts.items(), key=lambda x: -x[1])[:5]:
            weaknesses.append({"skill_tag": tag, "score": round(score, 2)})

        root = weaknesses[0]["skill_tag"] if weaknesses else "general review"
        confidence = min(0.95, 0.5 + len(weaknesses) * 0.1)
        return DiagnosisResult(
            weaknesses=weaknesses,
            root_cause=root,
            confidence=confidence,
        )
