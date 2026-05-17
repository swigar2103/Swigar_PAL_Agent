#!/usr/bin/env python3
"""Export game PostgreSQL questions to local JSON for offline Agent use."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from swigar_api.config import settings  # noqa: E402
from swigar_tools.postgres_question_bank import fetch_questions_from_postgres  # noqa: E402


def main() -> int:
    out = ROOT / "data" / "question_bank.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    if not settings.database_url.startswith(("postgresql", "postgres")):
        print("DATABASE_URL must be PostgreSQL (same as TacticalDuel game).", file=sys.stderr)
        return 1

    questions = fetch_questions_from_postgres(settings.database_url)
    out.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(questions)} questions to {out}")
    print("Set SWIGAR_QUESTION_BANK_SOURCE=json to use this file offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
