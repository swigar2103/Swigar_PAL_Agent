"""Learning director agent: Observe → Recall → Plan → Act → Log."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Awaitable, Callable

from swigar_core.models import LearningDecision, LearningEvent, LearningSignal, TraceStep
from swigar_memory import LearnerMemoryStore
from swigar_skills import SkillRegistry
from swigar_tools import ToolRegistry


class OrchestratorState(str, Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    PLANNING = "planning"
    AWAITING_GAME = "awaiting_game"
    COOLDOWN = "cooldown"


class LearningOrchestrator:
    def __init__(
        self,
        tools: ToolRegistry | None = None,
        skills: SkillRegistry | None = None,
        trace_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self.tools = tools or ToolRegistry()
        self.skills = skills or SkillRegistry(self.tools)
        self._state = OrchestratorState.IDLE
        self._trace_callback = trace_callback

    @property
    def state(self) -> OrchestratorState:
        return self._state

    async def _trace(self, step: str, phase: str, input_data: dict | None = None, output_data: dict | None = None, duration_ms: float | None = None):
        if self._trace_callback:
            await self._trace_callback(
                {
                    "kind": "trace",
                    "step": TraceStep(
                        step=step,
                        phase=phase,
                        input_data=input_data or {},
                        output_data=output_data or {},
                        duration_ms=duration_ms,
                    ).model_dump(mode="json"),
                }
            )

    async def run(
        self,
        event: LearningEvent | None,
        signals: list[LearningSignal],
        situation_store,
        goals_store,
        learner_id: str,
    ) -> LearningDecision:
        self._state = OrchestratorState.OBSERVING
        t0 = time.perf_counter()

        memory = LearnerMemoryStore(learner_id)
        situation = await situation_store.get(learner_id)
        if event:
            situation.recent_events = (situation.recent_events + [event])[-20:]
            situation.world_state.update(event.game_context.model_dump(exclude_none=True))
            await situation_store.save(situation)

        await self._trace("observe", "orchestrator", output_data={"event_id": event.event_id if event else None})

        self._state = OrchestratorState.PLANNING
        t_recall = time.perf_counter()
        wake = memory.wake_up()
        query = signals[0].skill_tag if signals else "english learning mistakes"
        snippets = memory.search(query, n=5)
        kg_weak = memory.query_weaknesses()
        await self._trace(
            "recall",
            "memory",
            input_data={"query": query},
            output_data={"snippet_count": len(snippets), "wake_len": len(wake)},
            duration_ms=(time.perf_counter() - t_recall) * 1000,
        )

        llm_traces: list[tuple[str, dict]] = []

        def llm_trace(step: str, data: dict) -> None:
            llm_traces.append((step, data))

        async def flush_llm_traces() -> None:
            for step, data in llm_traces:
                await self._trace(step, "llm", output_data=data)
            llm_traces.clear()

        t_diag = time.perf_counter()
        diagnosis, diag_meta = self.skills.diagnosis.run(
            signals, situation, snippets, kg_weak, trace=llm_trace
        )
        await flush_llm_traces()
        await self._trace(
            "diagnose",
            "skills",
            output_data={
                **diagnosis.model_dump(),
                "engine": diag_meta.get("source"),
                "llm_configured": self.tools.llm.is_configured,
            },
            duration_ms=(time.perf_counter() - t_diag) * 1000,
        )

        goals = await goals_store.list_for_learner(learner_id)
        recent_mistakes = sum(1 for s in signals if "weakness" in s.signal_type.value)
        plan, plan_meta = self.skills.plan.run(
            diagnosis, goals, recent_mistakes=recent_mistakes, trace=llm_trace
        )
        await flush_llm_traces()
        await self._trace(
            "plan",
            "skills",
            output_data={
                **plan.model_dump(),
                "engine": plan_meta.get("source"),
                "llm_configured": self.tools.llm.is_configured,
            },
        )

        memory_refs = [s.get("id", "") for s in snippets if isinstance(s, dict) and s.get("id")][:5]
        decision, quest_meta = self.skills.quest_mapping.run(
            plan, situation, event, memory_refs, trace=llm_trace
        )
        await flush_llm_traces()
        decision.content = self.tools.safety.filter_decision_content(decision.content)
        decision.narrative_hook, _ = self.tools.safety.filter_text(decision.narrative_hook)

        memory.write_plan_summary(
            f"Plan: {plan.intent} on {plan.skill_tags}. Decision: {decision.action_type}. {decision.rationale}",
            plan.skill_tags,
        )

        await self._trace(
            "act",
            "orchestrator",
            output_data={
                **decision.model_dump(mode="json"),
                "engine": quest_meta.get("source"),
            },
            duration_ms=(time.perf_counter() - t0) * 1000,
        )

        self._state = OrchestratorState.AWAITING_GAME
        return decision
