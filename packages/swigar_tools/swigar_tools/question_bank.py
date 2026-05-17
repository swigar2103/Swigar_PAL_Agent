"""Question bank: built-in MVP, JSON file, or game PostgreSQL."""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def retrieve_shuffle_enabled() -> bool:
    return os.environ.get("SWIGAR_RETRIEVE_SHUFFLE", "true").lower() in ("1", "true", "yes")


def _shuffle_matches(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not retrieve_shuffle_enabled() or len(candidates) <= 1:
        return candidates
    out = list(candidates)
    random.shuffle(out)
    return out


DEFAULT_BANK = [
    {
        "id": "q_pp_001",
        "skill_tags": ["grammar.present_perfect"],
        "difficulty": 2,
        "type": "fill_blank",
        "prompt": "I have ___ (go) to London twice.",
        "correct_answer": "gone",
        "choices": ["went", "gone", "go", "going"],
    },
    {
        "id": "q_pp_002",
        "skill_tags": ["grammar.present_perfect"],
        "difficulty": 2,
        "type": "multiple_choice",
        "prompt": "Which sentence uses the present perfect correctly?",
        "correct_answer": "She has lived here for five years.",
        "choices": [
            "She has lived here for five years.",
            "She lived here since five years.",
            "She has live here for five years.",
        ],
    },
    {
        "id": "q_past_001",
        "skill_tags": ["grammar.past_simple"],
        "difficulty": 1,
        "type": "fill_blank",
        "prompt": "Yesterday I ___ (visit) the museum.",
        "correct_answer": "visited",
        "choices": ["visit", "visited", "visiting", "visits"],
    },
    {
        "id": "q_vocab_001",
        "skill_tags": ["vocabulary.animals"],
        "difficulty": 1,
        "type": "multiple_choice",
        "prompt": "What is a young cat called?",
        "correct_answer": "kitten",
        "choices": ["puppy", "kitten", "calf", "chick"],
    },
]


class QuestionBankTool:
    def __init__(self, bank_path: Path | None = None):
        self._questions: list[dict[str, Any]] = list(DEFAULT_BANK)
        if bank_path and bank_path.exists():
            self._questions = json.loads(bank_path.read_text(encoding="utf-8"))

    def find_diverse(
        self,
        slots: list[tuple[list[str], str, int]],
        *,
        exclude_ids: list[str] | None = None,
        level_min: int | None = None,
        level_max: int | None = None,
        source: str | None = None,
        fallback_tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve per-slot quotas; prefer distinct normalized knowledge_point per slot."""
        exclude = set(exclude_ids or [])
        results: list[dict[str, Any]] = []
        used_kps: set[str] = set()

        def _nk(q: dict) -> str:
            kp = str(q.get("knowledge_point") or "").lower().strip()
            if kp:
                return kp[:64]
            return " ".join(q.get("skill_tags") or [])[:64]

        for skill_tags, kp, quota in slots:
            batch = self.find(
                skill_tags=skill_tags or fallback_tags,
                knowledge_point=kp,
                exclude_ids=list(exclude),
                limit=max(quota * 3, quota),
                level_min=level_min,
                level_max=level_max,
                source=source,
            )
            picked = 0
            for q in batch:
                if picked >= quota:
                    break
                if q["id"] in exclude:
                    continue
                nk = _nk(q)
                if nk in used_kps and picked > 0 and len(batch) > quota:
                    continue
                results.append(q)
                exclude.add(q["id"])
                used_kps.add(nk)
                picked += 1
            if picked < quota and fallback_tags:
                extra = self.find(
                    skill_tags=fallback_tags,
                    exclude_ids=list(exclude),
                    limit=quota - picked,
                    level_min=level_min,
                    level_max=level_max,
                    source=source,
                )
                for q in extra:
                    if picked >= quota:
                        break
                    results.append(q)
                    exclude.add(q["id"])
                    picked += 1
        return results

    def find(
        self,
        skill_tags: list[str] | None = None,
        difficulty: int | None = None,
        exclude_ids: list[str] | None = None,
        limit: int = 1,
        knowledge_point: str | None = None,
        level_min: int | None = None,
        level_max: int | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        exclude = set(exclude_ids or [])
        kp_norm = (knowledge_point or "").lower().replace("_", " ").strip()
        matched: list[dict[str, Any]] = []
        for q in self._questions:
            if q["id"] in exclude:
                continue
            if source and q.get("source") != source and source == "database":
                if q.get("source") == "generated":
                    continue
            if skill_tags and not any(t in q.get("skill_tags", []) for t in skill_tags):
                if kp_norm:
                    q_kp = str(q.get("knowledge_point", "")).lower()
                    q_tags = " ".join(q.get("skill_tags", [])).lower()
                    if kp_norm not in q_kp and kp_norm not in q_tags:
                        continue
                elif not skill_tags:
                    pass
                else:
                    continue
            elif kp_norm:
                q_kp = str(q.get("knowledge_point", "")).lower()
                q_tags = " ".join(q.get("skill_tags", [])).lower()
                if kp_norm not in q_kp and kp_norm not in q_tags:
                    tag_tail = kp_norm.split(".")[-1] if "." in kp_norm else kp_norm
                    if tag_tail not in q_kp and tag_tail not in q_tags:
                        continue
            lvl = q.get("level") or q.get("difficulty") or 1
            if isinstance(lvl, str):
                lvl = {"简单": 1, "easy": 1, "困难": 5, "hard": 5}.get(lvl.lower(), 2)
            lvl = int(lvl)
            if level_min is not None and lvl < level_min - 1:
                continue
            if level_max is not None and lvl > level_max + 1:
                continue
            if difficulty is not None and lvl > difficulty + 1:
                continue
            matched.append(q)
        matched = _shuffle_matches(matched)
        results = matched[:limit]
        if len(results) < limit:
            fallback: list[dict[str, Any]] = []
            for q in self._questions:
                if q["id"] in exclude or q in results:
                    continue
                fallback.append(q)
            fallback = _shuffle_matches(fallback)
            for q in fallback:
                results.append(q)
                if len(results) >= limit:
                    break
        return results

    def get_by_id(self, question_id: str) -> dict[str, Any] | None:
        for q in self._questions:
            if q["id"] == question_id:
                return q
        return None

    def find_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(question_ids)
        found: list[dict[str, Any]] = []
        for q in self._questions:
            if q["id"] in wanted:
                found.append(q)
        return found

    @property
    def size(self) -> int:
        return len(self._questions)

    def replace_all(self, questions: list[dict[str, Any]]) -> None:
        self._questions = list(questions)


def create_question_bank(
    *,
    source: str | None = None,
    database_url: str | None = None,
    json_path: Path | None = None,
    defer_postgres_load: bool = False,
) -> QuestionBankTool:
    """
    source: auto | postgres | json | builtin
    - auto: postgres if DATABASE_URL looks like PostgreSQL, else builtin
    """
    src = (source or os.environ.get("SWIGAR_QUESTION_BANK_SOURCE", "auto")).lower().strip()
    db_url = database_url or os.environ.get("DATABASE_URL", "")
    bank = QuestionBankTool(bank_path=json_path)

    if src == "auto":
        src = "postgres" if db_url.startswith(("postgresql", "postgres")) else "builtin"

    if src == "json":
        if json_path and json_path.exists():
            return bank
        logger.warning("SWIGAR_QUESTION_BANK_SOURCE=json but file missing; using builtin")
        return QuestionBankTool()

    if src == "postgres":
        if defer_postgres_load:
            logger.info("Deferring PostgreSQL question bank load to API lifespan")
            return QuestionBankTool()
        if not db_url.startswith(("postgresql", "postgres")):
            logger.warning("postgres question bank requested but DATABASE_URL is not PostgreSQL")
            return QuestionBankTool()
        try:
            from swigar_tools.postgres_question_bank import fetch_questions_from_postgres

            loaded = fetch_questions_from_postgres(db_url)
            if loaded:
                bank.replace_all(loaded)
                return bank
            logger.warning("PostgreSQL question bank empty; falling back to builtin")
        except Exception as exc:
            logger.exception("Failed to load questions from PostgreSQL: %s", exc)
        return QuestionBankTool()

    return QuestionBankTool()
