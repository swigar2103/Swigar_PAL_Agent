"""Normalize LLM-produced question fields for validation."""

from __future__ import annotations

import re


def normalize_choices(choices: list[str]) -> list[str]:
    out: list[str] = []
    for c in choices:
        text = str(c).strip()
        # Strip leading "A. " / "A) " labels
        text = re.sub(r"^[A-Da-d][\.\)、:\s]+", "", text).strip()
        if text:
            out.append(text)
    return out


def normalize_correct_answer(correct_answer: str, choices: list[str]) -> str:
    """Map letter keys (A-D) or index to the exact choice text."""
    if not choices:
        return correct_answer.strip()
    ans = correct_answer.strip()
    if not ans:
        return ans
    letter_map = {chr(ord("A") + i): choices[i] for i in range(min(4, len(choices)))}
    upper = ans.upper()
    if len(ans) == 1 and upper in letter_map:
        return letter_map[upper]
    # Already full text — find closest match
    norm = ans.lower()
    for c in choices:
        if c.strip().lower() == norm:
            return c
    for c in choices:
        if norm in c.lower() or c.lower() in norm:
            return c
    return ans
