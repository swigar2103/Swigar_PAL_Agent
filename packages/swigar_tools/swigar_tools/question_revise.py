"""Targeted one-shot revision for borderline question candidates."""

from __future__ import annotations

import json
from typing import Any, Callable

QUESTION_REVISE_SYSTEM = """You revise ONE English multiple-choice item to fix specific validation issues.
Change ONLY the fields listed in failed_reasons. Do not copy the source question.
Respond with JSON only: the same candidate object with prompt, choices, correct_answer, explanation, level."""


async def revise_candidate_once(
    llm,
    candidate: dict[str, Any],
    failed_reasons: list[str],
    sources: list[dict[str, Any]],
    *,
    trace: Callable[[str, dict], None] | None = None,
) -> dict[str, Any] | None:
    if not llm.is_configured:
        return None

    payload = {
        "candidate": candidate,
        "failed_reasons": failed_reasons,
        "source_stems_preview": [str(s.get("prompt", ""))[:80] for s in sources[:2]],
    }

    def _t(step: str, d: dict) -> None:
        if trace:
            trace(step, {**d, "skill": "question_revise"})

    data = await llm.complete_json_async(
        system=QUESTION_REVISE_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False),
        trace=_t,
    )
    if not data:
        return None
    return data.get("candidate") or data
