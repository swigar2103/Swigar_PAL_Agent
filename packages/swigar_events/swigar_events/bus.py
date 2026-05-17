"""In-process learning event bus with debug broadcast."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Awaitable

from swigar_core.models import LearningEvent, LearningSignal, TraceStep
from swigar_events.enricher import enrich_event


def _payload_summary(payload: dict) -> str:
    tags = payload.get("skill_tags", [])
    tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
    if payload.get("is_correct") is False:
        return f"答错 · {tag_str} · 作答: {payload.get('user_answer', '')}"
    if payload.get("is_correct") is True:
        return f"答对 · {tag_str}"
    return tag_str or "学习行为"


class EventBus:
    """Publish learning events; fan-out to memory, orchestrator, debug."""

    def __init__(self):
        self._subscribers: list[Callable[[dict[str, Any]], Awaitable[None]]] = []
        self._mistake_streak: dict[str, int] = defaultdict(int)

    def subscribe(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._subscribers.append(handler)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        for handler in self._subscribers:
            try:
                await handler(message)
            except Exception as exc:
                message.setdefault("errors", []).append(str(exc))

    async def publish(
        self,
        event: LearningEvent,
        *,
        memory_writer: Callable[[LearningEvent], str] | None = None,
        orchestrator_trigger: Callable[[LearningEvent, list[LearningSignal]], Awaitable[Any]] | None = None,
    ) -> dict[str, Any]:
        signals = enrich_event(event)
        result: dict[str, Any] = {
            "kind": "event_processed",
            "event": event.model_dump(mode="json"),
            "signals": [s.model_dump(mode="json") for s in signals],
        }

        await self._broadcast(
            {
                "kind": "trace",
                "step": TraceStep(
                    step="enrich",
                    phase="events",
                    input_data={
                        "event_type": event.type.value,
                        "learner_id": event.learner_id,
                        "payload_summary": _payload_summary(event.payload),
                    },
                    output_data={
                        "signal_count": len(signals),
                        "signals": result["signals"],
                    },
                ).model_dump(mode="json"),
            }
        )

        drawer_id = None
        if memory_writer:
            drawer_id = memory_writer(event)
            result["drawer_id"] = drawer_id
            await self._broadcast(
                {
                    "kind": "trace",
                    "step": TraceStep(
                        step="verbatim_write",
                        phase="memory",
                        output_data={"drawer_id": drawer_id},
                    ).model_dump(mode="json"),
                }
            )

        should_orchestrate = self._should_trigger_orchestrator(event, signals)
        result["orchestrator_triggered"] = should_orchestrate

        if should_orchestrate and orchestrator_trigger:
            decision = await orchestrator_trigger(event, signals)
            result["decision"] = decision.model_dump(mode="json") if decision else None

        await self._broadcast({"kind": "event_processed", **result})
        return result

    def _should_trigger_orchestrator(self, event: LearningEvent, signals: list[LearningSignal]) -> bool:
        key = f"{event.learner_id}:{event.session_id}"
        from swigar_core.models import LearningEventType

        if event.type == LearningEventType.ON_MISTAKE:
            self._mistake_streak[key] += 1
            if self._mistake_streak[key] >= 2:
                return True
        elif event.type in (LearningEventType.ON_ANSWER,):
            if not event.payload.get("is_correct", True):
                self._mistake_streak[key] += 1
                if self._mistake_streak[key] >= 3:
                    return True
            else:
                self._mistake_streak[key] = 0
        elif event.type in (LearningEventType.ON_TASK_DONE, LearningEventType.ON_LOW_ENGAGE):
            return True
        elif event.type == LearningEventType.ON_SESSION_START:
            return True

        if any(s.signal_type.value == "engagement_drop" for s in signals):
            return True
        return False
