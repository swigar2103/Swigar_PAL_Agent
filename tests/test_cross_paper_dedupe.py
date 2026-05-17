"""Cross-paper dedupe, bank shuffle, and cluster rotation."""

from __future__ import annotations

from swigar_core.models import LearnerProfile, PaperPlan, QuestionItem
from swigar_skills.reserve_select import select_from_reserve
from swigar_tools.knowledge_clusters import (
    cluster_should_rotate,
    pick_alternate_cluster,
    rotate_plan_if_mastered,
)
from swigar_tools.question_bank import QuestionBankTool, retrieve_shuffle_enabled


def _bank() -> QuestionBankTool:
    items = [
        {
            "id": f"g_{i}",
            "skill_tags": ["grammar.past_simple"],
            "difficulty": 1 + (i % 3),
            "type": "multiple_choice",
            "prompt": f"Past simple question {i}",
            "correct_answer": "A",
            "choices": ["A", "B"],
            "knowledge_point": "past simple",
            "source": "grammar",
        }
        for i in range(12)
    ]
    bank = QuestionBankTool()
    bank.replace_all(items)
    return bank


def test_shuffle_off_returns_stable_json_order(monkeypatch):
    monkeypatch.setenv("SWIGAR_RETRIEVE_SHUFFLE", "false")
    bank = _bank()
    a = [q["id"] for q in bank.find(skill_tags=["grammar.past_simple"], limit=4)]
    b = [q["id"] for q in bank.find(skill_tags=["grammar.past_simple"], limit=4)]
    assert a == b == ["g_0", "g_1", "g_2", "g_3"]


def test_shuffle_on_enabled_by_default():
    assert retrieve_shuffle_enabled() is True


def test_find_respects_exclude_ids():
    bank = _bank()
    first = bank.find(skill_tags=["grammar.past_simple"], limit=4)
    ids = {q["id"] for q in first}
    second = bank.find(skill_tags=["grammar.past_simple"], exclude_ids=list(ids), limit=4)
    assert second
    assert not {q["id"] for q in second} & ids


def test_select_from_reserve_skips_recent_correct():
    plan = PaperPlan(
        knowledge_point="past simple",
        skill_tags=["grammar.past_simple"],
        target_level_min=1,
        target_level_max=3,
        strategy="practice",
        rationale="t",
    )
    reserve = [
        QuestionItem(
            id="r_ok",
            source="generated",
            skill_tags=["grammar.past_simple"],
            knowledge_point="past simple",
            level=2,
            prompt="ok",
            correct_answer="a",
            choices=["a", "b"],
        ),
        QuestionItem(
            id="r_skip",
            source="generated",
            skill_tags=["grammar.past_simple"],
            knowledge_point="past simple",
            level=2,
            prompt="skip",
            correct_answer="a",
            choices=["a", "b"],
        ),
    ]
    _, generated = select_from_reserve(
        reserve, plan, max_mistake=0, max_generated=2, exclude_correct_ids={"r_skip"}
    )
    assert all(q.id != "r_skip" for q in generated)


def test_cluster_rotation_when_mastered():
    profile = LearnerProfile(
        learner_id="u1",
        accuracy_by_kp={
            "past simple": 0.9,
            "past continuous": 0.85,
            "past perfect": 0.88,
            "irregular past": 0.82,
        },
    )
    plan = PaperPlan(
        knowledge_point="past simple",
        skill_tags=["grammar.past_simple"],
        target_level_min=1,
        target_level_max=3,
        strategy="consolidate",
        rationale="test",
        knowledge_cluster_id="past_tenses",
    )
    assert cluster_should_rotate(profile, "past_tenses")
    rotated = rotate_plan_if_mastered(plan, profile)
    assert rotated.knowledge_cluster_id != "past_tenses"
    assert "rotated_cluster" in (rotated.rationale or "")


def test_pick_alternate_prefers_weak_cluster():
    profile = LearnerProfile(
        learner_id="u1",
        weak_points=["grammar.modal_verbs"],
        accuracy_by_kp={"past simple": 0.95, "modal verbs": 0.4},
    )
    alt = pick_alternate_cluster(profile, "past_tenses")
    assert alt == "modals"
