"""Tests for reserve select, cold-start gate, and paper store abandon behavior."""

from __future__ import annotations

import pytest

from swigar_core.models import LearnerProfile, PaperPlan, QuestionItem
from swigar_skills.reserve_select import select_from_reserve
from swigar_orchestrator.paper_orchestrator import PaperOrchestrator


def test_is_cold_start():
    p = LearnerProfile(learner_id="u1", total_answers=0, papers_completed=0)
    assert PaperOrchestrator.is_cold_start(p) is True
    p.total_answers = 1
    assert PaperOrchestrator.is_cold_start(p) is False


def test_select_from_reserve_prioritizes_kp():
    plan = PaperPlan(
        knowledge_point="grammar.present_perfect",
        skill_tags=["grammar.present_perfect"],
        target_level_min=1,
        target_level_max=3,
        strategy="practice",
        rationale="t",
    )
    reserve = [
        QuestionItem(
            id="r1",
            source="generated",
            skill_tags=["grammar.present_perfect"],
            knowledge_point="grammar.present_perfect",
            level=2,
            prompt="Q1",
            correct_answer="a",
            choices=["a", "b"],
        ),
        QuestionItem(
            id="r2",
            source="generated",
            skill_tags=["grammar.other"],
            knowledge_point="grammar.other",
            level=2,
            prompt="Q2",
            correct_answer="a",
            choices=["a", "b"],
        ),
    ]
    mistakes, generated = select_from_reserve(reserve, plan, max_mistake=0, max_generated=2)
    assert len(generated) >= 1
    assert generated[0].knowledge_point == "grammar.present_perfect"
