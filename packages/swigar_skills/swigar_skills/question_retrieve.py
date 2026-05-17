"""Retrieve database questions for exam papers."""

from __future__ import annotations

from typing import Any, Callable

from swigar_core.models import PaperPlan, QuestionItem
from swigar_tools.knowledge_clusters import expand_allowed_tags, kp_mix_enabled, retrieve_quotas
from swigar_tools.paper_builder import DB_COUNT


class QuestionRetrieveSkill:
    def __init__(self, tools):
        self.tools = tools

    def run(
        self,
        plan: PaperPlan,
        exclude_ids: list[str] | None = None,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> list[QuestionItem]:
        if kp_mix_enabled() and plan.related_knowledge_points:
            return self.retrieve_with_mix(plan, exclude_ids, trace)
        return self._retrieve_single(plan, exclude_ids, trace)

    def retrieve_with_mix(
        self,
        plan: PaperPlan,
        exclude_ids: list[str] | None = None,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> list[QuestionItem]:
        from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer

        quotas = retrieve_quotas(plan)
        slots: list[tuple[list[str], str, int]] = []
        slot_labels: list[str] = []

        for label, entry, quota in quotas:
            if entry is None:
                slots.append((list(plan.skill_tags), plan.knowledge_point, quota))
            else:
                slots.append((list(entry.skill_tags), entry.knowledge_point, quota))
            slot_labels.extend([label] * quota)

        fallback = expand_allowed_tags(plan)
        raw = self.tools.question_bank.find_diverse(
            slots,
            exclude_ids=exclude_ids,
            level_min=plan.target_level_min,
            level_max=plan.target_level_max,
            source="database",
            fallback_tags=fallback,
        )

        items: list[QuestionItem] = []
        for i, q in enumerate(raw[:DB_COUNT]):
            item = QuestionItem.from_bank_dict(q)
            item.source = "database"
            item.choices = normalize_choices(list(item.choices))
            item.correct_answer = normalize_correct_answer(item.correct_answer, item.choices)
            kp_slot = slot_labels[i] if i < len(slot_labels) else "primary"
            item.generation_meta = {**(item.generation_meta or {}), "kp_slot": kp_slot}
            items.append(item)

        while len(items) < DB_COUNT:
            extra = self._retrieve_single(plan, exclude_ids, trace)
            for e in extra:
                if e.id not in {x.id for x in items}:
                    items.append(e)
                if len(items) >= DB_COUNT:
                    break
            break

        if trace:
            trace(
                "retrieve_done",
                {
                    "count": len(items),
                    "ids": [q.id for q in items],
                    "kp_slots": [q.generation_meta.get("kp_slot") for q in items],
                    "knowledge_points": [q.knowledge_point for q in items],
                    "mixed": True,
                },
            )
        return items

    def _retrieve_single(
        self,
        plan: PaperPlan,
        exclude_ids: list[str] | None = None,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> list[QuestionItem]:
        raw = self.tools.question_bank.find(
            skill_tags=plan.skill_tags or None,
            knowledge_point=plan.knowledge_point,
            level_min=plan.target_level_min,
            level_max=plan.target_level_max,
            exclude_ids=exclude_ids,
            limit=DB_COUNT,
            source="database",
        )
        from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer

        items = [QuestionItem.from_bank_dict(q) for q in raw]
        for q in items:
            q.source = "database"
            q.choices = normalize_choices(list(q.choices))
            q.correct_answer = normalize_correct_answer(q.correct_answer, q.choices)
        if trace:
            trace("retrieve_done", {"count": len(items), "ids": [q.id for q in items], "mixed": False})
        return items
