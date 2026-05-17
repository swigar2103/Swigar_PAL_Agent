"""Infer learner error patterns from recent wrong answers."""

from __future__ import annotations

import re
from typing import Any


_OVERGENERALISED_ED = re.compile(r"\b\w+ed\b", re.I)


def infer_error_pattern(
    recent_wrong_answers: list[str],
    weak_points: list[str] | None = None,
) -> dict[str, Any]:
    """Rule-based error pattern inference for generation targeting."""
    wrong = [w.strip().lower() for w in recent_wrong_answers if w and w.strip()]
    weak = list(weak_points or [])

    if not wrong and not weak:
        return {
            "pattern": "general_practice",
            "focus": "consolidate target knowledge point",
            "examples": [],
            "targets_irregular_contrast": False,
        }

    ed_errors = [w for w in wrong if _OVERGENERALISED_ED.match(w) and w not in ("played", "walked", "helped")]
    irregular_hints = ("goed", "eated", "buyed", "seed", "runned", "writed", "eated")

    if any(h in wrong for h in irregular_hints) or len(ed_errors) >= 2:
        return {
            "pattern": "overgeneralised_regular_ed_on_irregular",
            "focus": "Use irregular past forms; distractors should include regularised -ed errors",
            "examples": wrong[:5],
            "targets_irregular_contrast": True,
        }

    if any("present" in w or "perfect" in w for w in weak):
        return {
            "pattern": "present_perfect_usage",
            "focus": "present perfect form and time markers",
            "examples": wrong[:5],
            "targets_irregular_contrast": False,
        }

    if any("past" in w for w in weak):
        return {
            "pattern": "past_tense_usage",
            "focus": "past tense including irregular verbs",
            "examples": wrong[:5],
            "targets_irregular_contrast": True,
        }

    return {
        "pattern": "targeted_remediation",
        "focus": weak[0] if weak else "address recent mistakes",
        "examples": wrong[:5],
        "targets_irregular_contrast": bool(ed_errors),
    }


def score_error_targeting(
    candidate: dict[str, Any],
    error_pattern: dict[str, Any],
) -> float:
    """0-100 score for how well item targets learner error pattern."""
    if not error_pattern or error_pattern.get("pattern") == "general_practice":
        return 75.0

    stem = str(candidate.get("prompt") or "").lower()
    choices = [str(c).lower() for c in (candidate.get("choices") or [])]
    meta = candidate.get("variation_strategy") or candidate.get("generation_meta", {}).get("variation_strategy") or []
    if isinstance(meta, list) and any("error" in str(m).lower() for m in meta):
        return 95.0

    if error_pattern.get("targets_irregular_contrast"):
        has_ed_distractor = any(c.endswith("ed") and c not in choices[0:1] for c in choices)
        irregular_in_choices = any(
            c in ("went", "ate", "saw", "bought", "took", "wrote", "gave", "made", "did", "had")
            for c in choices
        )
        if has_ed_distractor and irregular_in_choices:
            return 92.0
        if irregular_in_choices:
            return 80.0
        return 55.0

    focus = str(error_pattern.get("focus", "")).lower()
    if focus and any(tok in stem for tok in focus.split()[:3] if len(tok) > 4):
        return 85.0
    return 70.0
