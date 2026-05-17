from __future__ import annotations

from datetime import datetime

from swigar_core.models import LearningEvent, LearningReport, LearningSignal


class ReportSkill:
    def run(
        self,
        learner_id: str,
        events: list[LearningEvent],
        signals: list[LearningSignal],
        period_start: datetime,
        period_end: datetime,
    ) -> LearningReport:
        weaknesses = set()
        strengths = set()
        for sig in signals:
            if "weakness" in sig.signal_type.value:
                weaknesses.add(sig.skill_tag)
            elif sig.signal_type.value == "mastery_gain":
                strengths.add(sig.skill_tag)

        correct = sum(1 for e in events if e.payload.get("is_correct"))
        total_answers = sum(1 for e in events if e.type.value == "onAnswer")
        accuracy = (correct / total_answers * 100) if total_answers else 0

        summary = (
            f"Learner {learner_id} had {len(events)} events between "
            f"{period_start.date()} and {period_end.date()}. "
            f"Answer accuracy: {accuracy:.0f}%. "
            f"Focus areas: {', '.join(weaknesses) or 'none identified'}."
        )
        return LearningReport(
            learner_id=learner_id,
            period_start=period_start,
            period_end=period_end,
            summary=summary,
            weaknesses=list(weaknesses),
            strengths=list(strengths),
            events_count=len(events),
        )
