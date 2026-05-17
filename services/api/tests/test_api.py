import pytest
from httpx import ASGITransport, AsyncClient

from swigar_api.db import init_db
from swigar_api.main import app


@pytest.fixture
async def client():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_orchestrate(client):
    r = await client.post("/v1/orchestrate?learner_id=test_u&session_id=test_s")
    assert r.status_code == 200
    data = r.json()
    assert "action_type" in data
    assert "narrative_hook" in data
