"""Select questions from learner reserve pool for hybrid paper assembly."""

from __future__ import annotations

from swigar_core.models import PaperPlan, QuestionItem
from swigar_tools.paper_builder import DB_COUNT, GENERATED_COUNT, MISTAKE_REVIEW_COUNT


def select_from_reserve(
    reserve: list[QuestionItem],
    plan: PaperPlan,
    *,
    max_mistake: int = MISTAKE_REVIEW_COUNT,
    max_generated: int = GENERATED_COUNT,
    exclude_correct_ids: set[str] | None = None,
) -> tuple[list[QuestionItem], list[QuestionItem]]:
    """Return (mistake_slot_items, generated_slot_items) from reserve."""
    if not reserve:
        return [], []

    allowed_kps = {plan.knowledge_point}
    for rel in plan.related_knowledge_points or []:
        if rel.knowledge_point:
            allowed_kps.add(rel.knowledge_point)

    lvl_min = plan.target_level_min
    lvl_max = plan.target_level_max

    def _score(q: QuestionItem) -> float:
        kp = q.knowledge_point or ""
        kp_ok = 2.0 if kp in allowed_kps or plan.knowledge_point in kp else 0.0
        lvl = int(q.level or 2)
        if lvl < lvl_min - 1 or lvl > lvl_max + 1:
            return -1.0
        lvl_dist = abs(lvl - (lvl_min + lvl_max) / 2)
        origin_bonus = 1.5 if getattr(q, "origin", "") in ("carry_over", "mistake_review") else 0.0
        return kp_ok + origin_bonus - lvl_dist * 0.3

    skip_correct = exclude_correct_ids or set()
    ranked = sorted(reserve, key=_score, reverse=True)
    mistakes: list[QuestionItem] = []
    generated: list[QuestionItem] = []
    used: set[str] = set()

    for q in ranked:
        if _score(q) < 0:
            continue
        if q.id in used:
            continue
        if q.id in skip_correct:
            continue
        origin = getattr(q, "origin", "") or "normal"
        if origin in ("carry_over", "mistake_review") and len(mistakes) < max_mistake:
            mistakes.append(q)
            used.add(q.id)
        elif len(generated) < max_generated:
            generated.append(q)
            used.add(q.id)
        if len(mistakes) >= max_mistake and len(generated) >= max_generated:
            break

    for q in ranked:
        if len(generated) >= max_generated:
            break
        if q.id in used or q.id in skip_correct or _score(q) < 0:
            continue
        generated.append(q)
        used.add(q.id)

    return mistakes, generated
