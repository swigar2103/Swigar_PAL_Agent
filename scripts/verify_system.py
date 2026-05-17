#!/usr/bin/env python3
"""Verify LLM (DashScope), ONNX, and MemPalace memory. Run from repo root with project .venv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

# Ensure repo .env overrides stale shell variables before other imports
from swigar_api.config import apply_settings_to_env, settings  # noqa: E402

apply_settings_to_env()


def check_onnx() -> bool:
    print("== ONNX Runtime (MemPalace embeddings, local CPU) ==")
    try:
        import onnxruntime as ort

        print(f"  version: {ort.__version__}")
        print(f"  providers: {ort.get_available_providers()}")
        device = __import__("os").environ.get("MEMPALACE_EMBEDDING_DEVICE", "cpu")
        print(f"  MEMPALACE_EMBEDDING_DEVICE: {device}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        print("  Fix: use project venv, not Anaconda:")
        print("    .\\.venv\\Scripts\\pip install onnxruntime>=1.16")
        return False


def check_llm() -> bool:
    print("\n== DashScope LLM ==")
    from swigar_tools.llm import get_llm_client

    apply_settings_to_env()
    llm = get_llm_client()
    print(f"  SWIGAR_LLM_ENABLED (settings): {settings.swigar_llm_enabled}")
    print(f"  enabled: {llm.enabled}, configured: {llm.is_configured}, model: {llm.model}")
    if not llm.is_configured:
        print("  [FAIL] Set DASHSCOPE_API_KEY in .env; ensure SWIGAR_LLM_ENABLED=true")
        return False
    from swigar_tools.llm_prompts import PLAN_SYSTEM

    result = llm.complete_json(
        system=PLAN_SYSTEM,
        user=json.dumps(
            {
                "diagnosis": {
                    "weaknesses": [{"skill_tag": "grammar.present_perfect", "score": 0.9}],
                    "root_cause": "test",
                    "confidence": 0.8,
                },
                "goals": [],
                "recent_mistakes": 2,
            }
        ),
    )
    if not result:
        print("  [FAIL] LLM returned no JSON")
        return False
    print("  [OK] LLM JSON sample keys:", list(result.keys())[:5])
    return True


def check_memory() -> bool:
    print("\n== MemPalace memory ==")
    import os

    if os.environ.get("SWIGAR_MEMORY_DISABLED", "").lower() in ("1", "true", "yes"):
        print("  [SKIP] SWIGAR_MEMORY_DISABLED=true")
        return True

    from swigar_core.models import GameContext, LearningEvent, LearningEventType
    from swigar_memory import LearnerMemoryStore

    learner_id = "verify_system_user"
    ev = LearningEvent(
        type=LearningEventType.ON_MISTAKE,
        learner_id=learner_id,
        session_id="verify_s1",
        game_context=GameContext(map_id="tactical_duel", quest_id="verify"),
        payload={
            "skill_tags": ["grammar.present_perfect"],
            "is_correct": False,
            "user_answer": "test",
            "correct_answer": "gone",
        },
    )
    store = LearnerMemoryStore(learner_id)
    drawer_id = store.write_event_verbatim(ev)
    if not drawer_id:
        print("  [FAIL] write_event_verbatim returned empty")
        return False
    print(f"  [OK] wrote drawer: {drawer_id}")
    hits = store.search("present perfect grammar mistake", n=3)
    print(f"  [OK] search hits: {len(hits)}")
    wake = store.wake_up()
    print(f"  [OK] wake_up length: {len(wake)} chars")
    return len(hits) > 0


def main() -> None:
    print(f"Python: {sys.executable}\n")
    ok = check_onnx() and check_llm() and check_memory()
    print("\n" + ("[ALL OK] System ready." if ok else "[FAILED] Fix items above."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
