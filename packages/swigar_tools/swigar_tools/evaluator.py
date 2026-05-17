"""Answer evaluation tool."""

from __future__ import annotations

from typing import Any

from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer


class EvaluatorTool:
    @staticmethod
    def _match_choice(answer: str, choices: list[str]) -> str:
        """Resolve letter-only answers (A/B/C) to full choice text when possible."""
        a = answer.strip().lower()
        if len(a) == 1 and a.isalpha():
            for choice in choices:
                c = choice.strip()
                if c[:1].lower() == a or c.lower().startswith(f"{a}.") or c.lower().startswith(f"{a})"):
                    return c
        return answer

    def evaluate(self, user_answer: str, correct_answer: str, question: dict[str, Any] | None = None) -> dict[str, Any]:
        raw_choices = list(question.get("choices") or []) if question else []
        choices = normalize_choices(raw_choices) if raw_choices else []
        norm_correct = normalize_correct_answer(correct_answer, choices) if choices else correct_answer.strip()
        resolved_user = self._match_choice(user_answer, choices) if choices else user_answer
        resolved_correct = self._match_choice(norm_correct, choices) if choices else norm_correct
        normalized_user = resolved_user.strip().lower()
        normalized_correct = resolved_correct.strip().lower()
        is_correct = normalized_user == normalized_correct
        if not is_correct and choices:
            for choice in choices:
                if choice.strip().lower() == normalized_user:
                    is_correct = choice.strip().lower() == normalized_correct
                    break
        return {
            "is_correct": is_correct,
            "user_answer": user_answer,
            "correct_answer": norm_correct if choices else correct_answer,
            "feedback": "Correct!" if is_correct else f"Expected: {norm_correct if choices else correct_answer}",
        }

    def history_summary(self, recent_events: list[dict]) -> dict[str, Any]:
        wrong_tags: dict[str, int] = {}
        for ev in recent_events:
            payload = ev.get("payload", {})
            if not payload.get("is_correct", True):
                for tag in payload.get("skill_tags", []):
                    wrong_tags[tag] = wrong_tags.get(tag, 0) + 1
        return {"wrong_counts": wrong_tags, "total_events": len(recent_events)}
