"""Load question bank from game PostgreSQL (questions_grammar / questions_words)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from swigar_tools.db_url import prepare_postgres_urls

logger = logging.getLogger(__name__)


def _difficulty_to_int(value: Any) -> int:
    if isinstance(value, int):
        return max(1, min(3, value))
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("简单", "easy", "1"):
            return 1
        if s in ("困难", "hard", "3"):
            return 3
    return 2


def _parse_options(raw: Any) -> tuple[list[str], str]:
    """Return (choices list, correct answer text)."""
    if raw is None:
        return [], ""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [], ""
    if isinstance(raw, list):
        return [str(x) for x in raw if x], ""
    if isinstance(raw, dict):
        keys = sorted(raw.keys())
        choices = [str(raw[k]) for k in keys if raw.get(k) is not None]
        return choices, ""
    return [], ""


def _correct_from_option_key(options: dict[str, Any], correct_option: str | None) -> str:
    if not correct_option or not isinstance(options, dict):
        return ""
    key = str(correct_option).strip()
    if key in options:
        return str(options[key])
    upper = key.upper()
    if upper in options:
        return str(options[upper])
    return key


def map_grammar_row(row: dict[str, Any]) -> dict[str, Any] | None:
    prompt = (row.get("question_text") or row.get("questionText") or "").strip()
    if not prompt:
        return None
    options_raw = row.get("options")
    choices, _ = _parse_options(options_raw)
    if isinstance(options_raw, dict):
        correct_answer = _correct_from_option_key(options_raw, row.get("correct_option"))
    else:
        correct_answer = str(row.get("correct_option") or "")
    if not correct_answer and choices:
        correct_answer = choices[0]
    kp = (row.get("knowledge_point") or row.get("knowledgePoint") or "grammar").strip()
    tag = "grammar." + "".join(c if c.isalnum() else "_" for c in kp.lower())[:48]
    return {
        "id": f"g_{row['id']}",
        "game_id": row["id"],
        "source": "grammar",
        "skill_tags": [tag],
        "difficulty": _difficulty_to_int(row.get("difficulty")),
        "type": "multiple_choice" if len(choices) > 1 else "fill_blank",
        "prompt": prompt,
        "correct_answer": correct_answer,
        "choices": choices,
        "knowledge_point": kp,
        "grade": row.get("grade"),
        "unit": row.get("unit"),
        "explanation": row.get("explanation") or "",
    }


def map_words_row(row: dict[str, Any]) -> dict[str, Any] | None:
    eng = (row.get("eng") or "").strip()
    cn = (row.get("cn") or "").strip()
    if not eng or not cn:
        return None
    options_raw = row.get("options")
    choices, _ = _parse_options(options_raw)
    correct_option = row.get("correct_option")
    if isinstance(options_raw, dict) and correct_option:
        correct_answer = _correct_from_option_key(options_raw, correct_option)
    elif choices:
        correct_answer = cn if cn in choices else (choices[0] if choices else cn)
    else:
        choices = [cn]
        correct_answer = cn
    prompt = (row.get("question_text") or "").strip() or f'请选择 "{eng}" 的正确中文意思：'
    kp = (row.get("knowledge_point") or row.get("knowledgePoint") or eng).strip()
    tag = "vocabulary." + "".join(c if c.isalnum() else "_" for c in kp.lower())[:48]
    return {
        "id": f"w_{row['id']}",
        "game_id": row["id"],
        "source": "words",
        "skill_tags": [tag],
        "difficulty": _difficulty_to_int(row.get("difficulty")),
        "type": "multiple_choice",
        "prompt": prompt,
        "correct_answer": correct_answer,
        "choices": choices if len(choices) > 1 else [cn],
        "knowledge_point": kp,
        "grade": row.get("grade"),
        "unit": row.get("unit"),
        "explanation": row.get("explanation") or "",
    }


async def fetch_questions_async(database_url: str) -> list[dict[str, Any]]:
    import asyncpg

    _, _, dsn, ssl = prepare_postgres_urls(database_url)
    conn = await asyncpg.connect(
        dsn,
        ssl=ssl if ssl is not None else None,
        timeout=float(os.environ.get("SWIGAR_PG_CONNECT_TIMEOUT", "20")),
    )
    try:
        grammar_rows = await conn.fetch("SELECT * FROM questions_grammar")
        words_rows = await conn.fetch("SELECT * FROM questions_words")
    finally:
        await conn.close()

    out: list[dict[str, Any]] = []
    for row in grammar_rows:
        mapped = map_grammar_row(dict(row))
        if mapped:
            out.append(mapped)
    for row in words_rows:
        mapped = map_words_row(dict(row))
        if mapped:
            out.append(mapped)
    logger.info(
        "Loaded %d grammar + %d words rows -> %d agent questions",
        len(grammar_rows),
        len(words_rows),
        len(out),
    )
    return out


def fetch_questions_from_postgres(database_url: str) -> list[dict[str, Any]]:
    """Sync entry (CLI). Safe when no event loop or when called from a worker thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fetch_questions_async(database_url))

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, fetch_questions_async(database_url)).result()
