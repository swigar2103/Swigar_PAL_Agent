"""Content safety filter for agent outputs."""

from __future__ import annotations

import re

BLOCKED_PATTERNS = [
    re.compile(r"\b(kill|suicide|self-harm)\b", re.I),
    re.compile(r"\b(password|credit\s*card|ssn)\b", re.I),
]


class SafetyFilterTool:
    def filter_text(self, text: str) -> tuple[str, bool]:
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(text):
                return "[Content filtered for safety]", False
        return text, True

    def filter_decision_content(self, content: dict) -> dict:
        safe = {}
        for key, value in content.items():
            if isinstance(value, str):
                safe[key], _ = self.filter_text(value)
            else:
                safe[key] = value
        return safe
