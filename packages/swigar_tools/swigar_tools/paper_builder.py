"""Assemble exam papers with difficulty gradient and DB/GEN interleaving."""

from __future__ import annotations

import os
from swigar_core.models import ExamPaper, QuestionItem


PAPER_SIZE = 10
DB_COUNT = 4
GENERATED_COUNT = 6
MISTAKE_REVIEW_COUNT = 2

# Q1 DB L1, Q2 GEN L1, Q3 DB L2, Q4 GEN L2, Q5 GEN L3, Q6 DB L3,
# Q7 GEN L4, Q8 GEN L4, Q9 DB L5, Q10 GEN L5
_INTERLEAVE_TEMPLATE: list[tuple[str, int]] = [
    ("db", 1),
    ("gen", 1),
    ("db", 2),
    ("gen", 2),
    ("gen", 3),
    ("db", 3),
    ("gen", 4),
    ("gen", 4),
    ("db", 5),
    ("gen", 5),
]


def _interleave_enabled() -> bool:
    return os.environ.get("SWIGAR_PAPER_INTERLEAVE", "true").lower() in ("1", "true", "yes")


def sort_by_level_gradient(questions: list[QuestionItem]) -> list[QuestionItem]:
    return sorted(questions, key=lambda q: (q.level, q.id))


def assign_gradient_levels(questions: list[QuestionItem], level_min: int, level_max: int) -> list[QuestionItem]:
    if not questions:
        return questions
    n = len(questions)
    if n == 1:
        questions[0].level = level_min
        return questions
    span = max(level_max - level_min, 1)
    for i, q in enumerate(questions):
        q.level = level_min + round((i / (n - 1)) * span)
        q.level = max(1, min(5, q.level))
    return questions


def _pick_by_level(pool: list[QuestionItem], target: int, used_ids: set[str]) -> QuestionItem | None:
    candidates = [q for q in pool if q.id not in used_ids]
    if not candidates:
        return None
    candidates.sort(key=lambda q: (abs(q.level - target), q.id))
    return candidates[0]


def interleave_paper_questions(
    db_questions: list[QuestionItem],
    generated_questions: list[QuestionItem],
) -> list[QuestionItem]:
    """Build 10-question paper with alternating DB and generated slots."""
    db_pool = list(db_questions)
    gen_pool = list(generated_questions)
    used: set[str] = set()
    out: list[QuestionItem] = []

    for src, lvl in _INTERLEAVE_TEMPLATE:
        pool = db_pool if src == "db" else gen_pool
        picked = _pick_by_level(pool, lvl, used)
        if picked is None and pool:
            for q in pool:
                if q.id not in used:
                    picked = q
                    break
        if picked is None:
            fallback = db_pool if src == "db" else gen_pool
            other = gen_pool if src == "db" else db_pool
            picked = _pick_by_level(other, lvl, used) or _pick_by_level(fallback + other, lvl, used)
        if picked is None:
            continue
        q = picked.model_copy(deep=True)
        q.level = lvl
        used.add(picked.id)
        out.append(q)

    remainder_db = [q for q in db_pool if q.id not in used]
    remainder_gen = [q for q in gen_pool if q.id not in used]
    for q in remainder_db + remainder_gen:
        if len(out) >= PAPER_SIZE:
            break
        if q.id in used:
            continue
        used.add(q.id)
        out.append(q.model_copy(deep=True))

    return out[:PAPER_SIZE]


def build_exam_paper(
    *,
    learner_id: str,
    session_id: str,
    knowledge_point: str,
    db_questions: list[QuestionItem],
    generated_questions: list[QuestionItem],
    mistake_questions: list[QuestionItem] | None = None,
    strategy: str,
    rationale: str,
    status: str = "active",
) -> ExamPaper:
    from uuid import uuid4

    db_slice = list(db_questions[:DB_COUNT])
    mistakes = list(mistake_questions or [])[:MISTAKE_REVIEW_COUNT]
    if mistakes:
        replace_n = min(len(mistakes), len(db_slice))
        db_slice = mistakes[:replace_n] + db_slice[replace_n:]
        if len(mistakes) > replace_n:
            db_slice.extend(mistakes[replace_n : MISTAKE_REVIEW_COUNT])

    gen_slice = list(generated_questions[:GENERATED_COUNT])

    if _interleave_enabled():
        combined = interleave_paper_questions(db_slice, gen_slice)
    else:
        combined = db_slice + gen_slice
        combined = sort_by_level_gradient(combined)

    fill_idx = 0
    all_db = list(db_questions)
    while len(combined) < PAPER_SIZE and all_db:
        src = all_db[fill_idx % len(all_db)]
        fill_idx += 1
        if src.id in {x.id for x in combined}:
            continue
        clone = src.model_copy(deep=True)
        clone.id = f"{clone.id}_dup_{uuid4().hex[:6]}"
        clone.source = "generated"
        combined.append(clone)

    if not _interleave_enabled():
        combined = sort_by_level_gradient(combined[:PAPER_SIZE])
    else:
        combined = combined[:PAPER_SIZE]

    return ExamPaper(
        learner_id=learner_id,
        session_id=session_id,
        knowledge_point=knowledge_point,
        questions=combined,
        strategy=strategy,
        rationale=rationale,
        status=status,  # type: ignore[arg-type]
    )
