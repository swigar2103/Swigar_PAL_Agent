from swigar_core.models import LearningEvent, LearningEventType
from swigar_events.enricher import enrich_event


def test_enrich_mistake():
    ev = LearningEvent(
        type=LearningEventType.ON_MISTAKE,
        learner_id="u1",
        session_id="s1",
        payload={"skill_tags": ["grammar.present_perfect"], "is_correct": False},
    )
    signals = enrich_event(ev)
    assert len(signals) >= 1
    assert signals[0].skill_tag == "grammar.present_perfect"
