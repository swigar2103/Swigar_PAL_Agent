from swigar_core.models import DiagnosisResult, GoalRecord
from swigar_skills.plan import PlanSkill


def test_plan_review_on_weakness():
    diagnosis = DiagnosisResult(
        weaknesses=[{"skill_tag": "grammar.present_perfect", "score": 1.5}],
        root_cause="grammar.present_perfect",
        confidence=0.85,
    )
    plan, meta = PlanSkill().run(diagnosis, [], recent_mistakes=3)
    assert plan.intent == "review"
    assert "present_perfect" in plan.skill_tags[0]
    assert meta["source"] == "rules"
