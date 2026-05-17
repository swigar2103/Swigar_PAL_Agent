"""Rule-based validation helpers for single questions."""

from __future__ import annotations

import re
from typing import Any


def check_answer_leakage(stem: str, correct: str, choices: list[str]) -> tuple[bool, str]:
    """Return (failed, reason)."""
    if not stem or not correct:
        return False, ""
    c_low = correct.strip().lower()
    stem_low = stem.lower()
    if len(c_low) >= 3 and c_low in stem_low:
        return True, "answer_in_stem"
    for form in (c_low, c_low + "ed", c_low + "ing", c_low + "s"):
        if len(form) >= 4 and re.search(rf"\b{re.escape(form)}\b", stem_low):
            return True, f"answer_form_leak:{form}"
    return False, ""


def check_option_category(choices: list[str]) -> tuple[bool, str]:
    """Grammar items: options should be same grammatical category."""
    if len(choices) < 2:
        return False, ""

    def _category(opt: str) -> str:
        o = opt.strip().lower()
        if o.endswith("ly"):
            return "adv"
        if o.endswith("ing"):
            return "verb"
        if o.endswith("ed") or o in ("went", "ate", "saw", "bought", "did", "had"):
            return "verb"
        if len(o.split()) > 2:
            return "phrase"
        return "word"

    cats = {_category(c) for c in choices}
    if "adv" in cats and "verb" in cats:
        return True, "mixed_adv_verb_options"
    if "phrase" in cats and len(cats) > 2:
        return True, "mixed_phrase_word_options"
    lengths = [len(c) for c in choices]
    if lengths and max(lengths) > min(lengths) * 2.5:
        return True, "option_length_clue"
    return False, ""


def check_level_fit(stem: str, level: int, learner_level: int) -> tuple[bool, str]:
    words = stem.split()
    clauses = stem.count(",") + stem.count(";") + 1
    if learner_level <= 1:
        if len(words) > 14:
            return True, "too_long_for_a1"
        if clauses > 2:
            return True, "too_many_clauses_a1"
    if learner_level <= 2:
        if len(words) > 22:
            return True, "too_long_for_a2"
    if level >= 5 and learner_level <= 2:
        return True, "item_level_too_high"
    return False, ""


def question_to_dict(q: Any) -> dict[str, Any]:
    if hasattr(q, "model_dump"):
        return q.model_dump(mode="json")
    return dict(q)
