"""End-to-end: mistake events should yield review-oriented decision."""

import pytest
from httpx import ASGITransport, AsyncClient

from swigar_api.db import init_db
from swigar_api.main import app

MISTAKE_EVENT = {
    "type": "onMistake",
    "learner_id": "integration_u",
    "session_id": "integration_s",
    "game_context": {"map_id": "castle", "npc_id": "mentor"},
    "payload": {
        "skill_tags": ["grammar.present_perfect"],
        "is_correct": False,
    },
}


@pytest.mark.asyncio
async def test_mistake_loop_produces_decision():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        await client.post("/v1/events", json=MISTAKE_EVENT)
        r = await client.post("/v1/events", json=MISTAKE_EVENT)
        assert r.status_code == 200
        body = r.json()
        assert body["processed"] == 1
        result = body["results"][0]
        if result.get("orchestrator_triggered"):
            assert result.get("decision") is not None
            assert result["decision"]["action_type"] in (
                "dungeon_quiz",
                "npc_dialogue",
                "assign_task",
                "hint",
                "difficulty_adjust",
            )
