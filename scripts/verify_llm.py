#!/usr/bin/env python3
"""Verify DashScope (百炼) API connectivity. Run from repo root after configuring .env."""

import json
import sys
from pathlib import Path

# Load .env before importing swigar modules
root = Path(__file__).resolve().parents[1]
env_file = root / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        import os

        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

sys.path.insert(0, str(root))

from swigar_tools.llm import get_llm_client
from swigar_tools.llm_prompts import PLAN_SYSTEM


def main():
    llm = get_llm_client()
    print(f"Enabled: {llm.enabled}")
    print(f"Configured: {llm.is_configured}")
    print(f"Base URL: {llm.base_url}")
    print(f"Model: {llm.model}")

    if not llm.is_configured:
        print("\n[FAIL] Copy .env.example to .env and set DASHSCOPE_API_KEY")
        sys.exit(1)

    result = llm.complete_json(
        system=PLAN_SYSTEM,
        user=json.dumps(
            {
                "diagnosis": {
                    "weaknesses": [{"skill_tag": "grammar.present_perfect", "score": 0.9}],
                    "root_cause": "present perfect",
                    "confidence": 0.85,
                },
                "goals": [],
                "recent_mistakes": 3,
            }
        ),
    )
    if result:
        print("\n[OK] LLM response:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n[FAIL] No JSON returned — check API key, model name, and network")
        sys.exit(1)


if __name__ == "__main__":
    main()
