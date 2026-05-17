"""Select historical wrong answers for inclusion in new exam papers."""

from __future__ import annotations

from typing import Any, Callable

from swigar_core.models import QuestionItem
from swigar_tools.paper_builder import MISTAKE_REVIEW_COUNT


class MistakeReviewSkill:
    def __init__(self, tools):
        self.tools = tools

    def run(
        self,
        candidates: list[dict[str, Any]],
        exclude_ids: list[str] | None = None,
        limit: int = MISTAKE_REVIEW_COUNT,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> list[QuestionItem]:
        exclude = set(exclude_ids or [])
        ids: list[str] = []
        meta: dict[str, str] = {}
        source_by: dict[str, str] = {}
        for c in candidates:
            qid = str(c.get("question_id", ""))
            if not qid or qid in exclude or qid in ids:
                continue
            ids.append(qid)
            meta[qid] = str(c.get("paper_id", ""))
            source_by[qid] = str(c.get("source", ""))
            if len(ids) >= limit:
                break
        if not ids:
            if trace:
                trace("mistake_review_empty", {"count": 0})
            return []

        raw = self.tools.question_bank.find_by_ids(ids)
        items: list[QuestionItem] = []
        for q in raw:
            item = QuestionItem.from_bank_dict(q)
            src = source_by.get(item.id, "")
            item.origin = "carry_over" if src == "unanswered_carry" else "mistake_review"
            item.mistake_from_paper_id = meta.get(item.id)
            items.append(item)
        if trace:
            trace(
                "mistake_review_done",
                {"count": len(items), "ids": [q.id for q in items], "skill": "mistake_review"},
            )
        return items
