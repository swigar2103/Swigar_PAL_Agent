from __future__ import annotations

import json
from typing import Any, Callable

from swigar_core.models import LearningDecision, LearningEvent, LearningSituation, PlanIntent
from swigar_tools.llm_prompts import QUEST_MAP_SYSTEM


class QuestMappingSkill:
    def __init__(self, tools):
        self.tools = tools

    def run(
        self,
        intent: PlanIntent,
        situation: LearningSituation,
        event: LearningEvent | None,
        memory_refs: list[str],
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[LearningDecision, dict[str, Any]]:
        llm_fields = self._run_llm(intent, situation, event, trace)
        if llm_fields:
            decision = self._build_from_llm(llm_fields, intent, situation, event, memory_refs)
            return decision, {"source": "llm", "skill": "quest_mapping"}
        decision = self._run_rules(intent, situation, event, memory_refs)
        return decision, {"source": "rules", "skill": "quest_mapping"}

    def _run_llm(
        self,
        intent: PlanIntent,
        situation: LearningSituation,
        event: LearningEvent | None,
        trace: Callable[[str, dict[str, Any]], None] | None,
    ) -> dict[str, Any] | None:
        if not self.tools.llm.is_configured:
            return None

        ctx = situation.world_state
        if event:
            ctx = {**ctx, **event.game_context.model_dump(exclude_none=True)}

        user_payload = {
            "plan": intent.model_dump(),
            "game_context": ctx,
            "learner_id": situation.learner_id,
        }
        def _trace(step: str, data: dict) -> None:
            if trace:
                trace(step, {**data, "skill": "quest_mapping"})

        return self.tools.llm.complete_json(
            system=QUEST_MAP_SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False, default=str),
            trace=_trace,
        )

    def _build_from_llm(
        self,
        data: dict[str, Any],
        intent: PlanIntent,
        situation: LearningSituation,
        event: LearningEvent | None,
        memory_refs: list[str],
    ) -> LearningDecision:
        valid_actions = {
            "assign_task",
            "npc_dialogue",
            "dungeon_quiz",
            "feedback_reward",
            "hint",
            "difficulty_adjust",
        }
        action_type = data.get("action_type", "dungeon_quiz")
        if action_type not in valid_actions:
            action_type = "dungeon_quiz"
        difficulty = 1 if intent.difficulty == "easier" else 2
        questions = self.tools.question_bank.find(
            skill_tags=intent.skill_tags,
            difficulty=difficulty,
            limit=2 if action_type == "dungeon_quiz" else 1,
        )

        content: dict[str, Any] = {"skill_tags": intent.skill_tags, "questions": questions}
        if data.get("dialogue_lines"):
            content["dialogue_lines"] = data["dialogue_lines"]
        if data.get("hint"):
            content["hint"] = data["hint"]
        if action_type == "feedback_reward":
            content = {"xp": 50, "item": "skill_shard", **content}

        return LearningDecision(
            learner_id=situation.learner_id,
            session_id=event.session_id if event else None,
            action_type=action_type,
            narrative_hook=data.get("narrative_hook", intent.rationale),
            content=content,
            rationale=data.get("rationale", intent.rationale),
            memory_refs=memory_refs,
        )

    def _run_rules(
        self,
        intent: PlanIntent,
        situation: LearningSituation,
        event: LearningEvent | None,
        memory_refs: list[str],
    ) -> LearningDecision:
        ctx = situation.world_state
        map_name = ctx.get("map_id") or (event.game_context.map_id if event else "training_grounds")
        npc = ctx.get("npc_id") or (event.game_context.npc_id if event else "mentor")

        if intent.intent == "review":
            questions = self.tools.question_bank.find(
                skill_tags=intent.skill_tags,
                difficulty=1 if intent.difficulty == "easier" else 2,
                limit=1,
            )
            q = questions[0] if questions else {}
            hook = (
                f"While exploring {map_name}, {npc} noticed you keep mixing up "
                f"{intent.skill_tags[0].split('.')[-1].replace('_', ' ')}. "
                f"Time for a dungeon quiz to sharpen that skill!"
            )
            return LearningDecision(
                learner_id=situation.learner_id,
                session_id=event.session_id if event else None,
                action_type="dungeon_quiz",
                narrative_hook=hook,
                content={"questions": [q], "skill_tags": intent.skill_tags},
                rationale=intent.rationale,
                memory_refs=memory_refs,
            )

        if intent.intent == "reward":
            return LearningDecision(
                learner_id=situation.learner_id,
                session_id=event.session_id if event else None,
                action_type="feedback_reward",
                narrative_hook=f"Great work in {map_name}! You've earned bonus XP and a skill shard.",
                content={"xp": 50, "item": "skill_shard"},
                rationale=intent.rationale,
                memory_refs=memory_refs,
            )

        if intent.intent == "hint":
            return LearningDecision(
                learner_id=situation.learner_id,
                session_id=event.session_id if event else None,
                action_type="hint",
                narrative_hook=f"{npc} whispers a clue to help you on your quest.",
                content={"hint": f"Focus on: {', '.join(intent.skill_tags)}"},
                rationale=intent.rationale,
                memory_refs=memory_refs,
            )

        if intent.intent == "new_knowledge":
            questions = self.tools.question_bank.find(skill_tags=intent.skill_tags, limit=1)
            return LearningDecision(
                learner_id=situation.learner_id,
                session_id=event.session_id if event else None,
                action_type="assign_task",
                narrative_hook=f"A new quest awaits in {map_name}. Master something new with {npc}.",
                content={"task_type": "learn_new", "questions": questions},
                rationale=intent.rationale,
                memory_refs=memory_refs,
            )

        questions = self.tools.question_bank.find(skill_tags=intent.skill_tags, limit=1)
        return LearningDecision(
            learner_id=situation.learner_id,
            session_id=event.session_id if event else None,
            action_type="npc_dialogue",
            narrative_hook=(
                f"{npc} in {map_name} wants to practice with you. "
                f"Let's work on {intent.skill_tags[0] if intent.skill_tags else 'English'}."
            ),
            content={
                "dialogue_lines": [f"Ready to practice {intent.skill_tags[0]}?"],
                "questions": questions,
            },
            rationale=intent.rationale,
            memory_refs=memory_refs,
        )
