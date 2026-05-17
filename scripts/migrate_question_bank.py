#!/usr/bin/env python3
"""Map legacy question rows to unified Agent schema (level 1-5, source_type)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalize_question(q: dict) -> dict:
    level = q.get("level") or q.get("difficulty") or 2
    if isinstance(level, str):
        level = {"简单": 1, "easy": 1, "困难": 5, "hard": 5}.get(level.lower(), 2)
    level = max(1, min(5, int(level)))
    return {
        **q,
        "level": level,
        "difficulty": level,
        "source": q.get("source") or "database",
        "source_type": q.get("source_type") or "database",
        "knowledge_point": q.get("knowledge_point")
        or (q.get("skill_tags") or ["general"])[0].replace("grammar.", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("questions", [])
    out = [normalize_question(q) for q in items]
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(out)} questions to {args.output}")


if __name__ == "__main__":
    main()
