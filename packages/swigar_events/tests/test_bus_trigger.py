from swigar_core.models import LearningEvent, LearningEventType
from swigar_events.bus import EventBus


def test_mistake_streak_triggers():
    bus = EventBus()
    ev = LearningEvent(
        type=LearningEventType.ON_MISTAKE,
        learner_id="u1",
        session_id="s1",
        payload={"skill_tags": ["grammar.past_simple"]},
    )
    assert bus._should_trigger_orchestrator(ev, []) is False
    assert bus._should_trigger_orchestrator(ev, []) is True
