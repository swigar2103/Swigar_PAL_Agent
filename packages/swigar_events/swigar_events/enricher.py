"""Rule-based semantic enrichment of learning events."""

from __future__ import annotations

from swigar_core.models import LearningEvent, LearningEventType, LearningSignal, SignalType


def enrich_event(event: LearningEvent) -> list[LearningSignal]:
    signals: list[LearningSignal] = []
    skill_tags = event.payload.get("skill_tags", [])
    if not isinstance(skill_tags, list):
        skill_tags = [str(skill_tags)] if skill_tags else []

    if event.type in (LearningEventType.ON_ANSWER, LearningEventType.ON_MISTAKE):
        is_correct = event.payload.get("is_correct", True)
        if event.type == LearningEventType.ON_MISTAKE or is_correct is False:
            for tag in skill_tags:
                domain = SignalType.GRAMMAR_WEAKNESS if tag.startswith("grammar.") else SignalType.VOCAB_WEAKNESS
                signals.append(
                    LearningSignal(
                        signal_type=domain,
                        skill_tag=tag,
                        confidence=0.75 if event.type == LearningEventType.ON_MISTAKE else 0.6,
                        evidence_event_ids=[event.event_id],
                        detail=f"Incorrect answer on {tag}",
                    )
                )

    if event.type == LearningEventType.ON_ANSWER and event.payload.get("is_correct"):
        for tag in skill_tags:
            signals.append(
                LearningSignal(
                    signal_type=SignalType.MASTERY_GAIN,
                    skill_tag=tag,
                    confidence=0.7,
                    evidence_event_ids=[event.event_id],
                    detail=f"Correct answer on {tag}",
                )
            )

    if event.type == LearningEventType.ON_LOW_ENGAGE:
        signals.append(
            LearningSignal(
                signal_type=SignalType.ENGAGEMENT_DROP,
                skill_tag="engagement",
                confidence=0.8,
                evidence_event_ids=[event.event_id],
                detail=event.payload.get("reason", "low engagement"),
            )
        )

    if event.type == LearningEventType.ON_TASK_DONE:
        time_spent = event.payload.get("time_spent_ms", 0)
        expected = event.payload.get("expected_ms", 60000)
        if time_spent and expected and time_spent > expected * 2:
            signals.append(
                LearningSignal(
                    signal_type=SignalType.TASK_STRUGGLE,
                    skill_tag=skill_tags[0] if skill_tags else "general",
                    confidence=0.65,
                    evidence_event_ids=[event.event_id],
                    detail="Task took much longer than expected",
                )
            )

    return signals
