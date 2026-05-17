"""FastAPI application: game API + debug WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from swigar_core.models import GoalCreate, LearningEvent, LearningEventType
from swigar_events import EventBus
from swigar_memory import LearnerMemoryStore
from swigar_orchestrator import LearningOrchestrator, PaperOrchestrator
from swigar_skills import ReportSkill

from pathlib import Path

from swigar_api.config import apply_settings_to_env, settings
from swigar_tools.postgres_question_bank import fetch_questions_async
from swigar_tools.question_bank import create_question_bank
from swigar_tools.registry import ToolRegistry
from swigar_api.db import SessionLocal, get_session, init_db
from swigar_api.db_ready import ensure_db_ready, is_db_ready
from swigar_api.paper_stores import WorkflowStore
from swigar_api.stores import DecisionStore, EventLogStore, GoalStore, SituationStore, TraceStore
from swigar_api.routes.papers import init_paper_routes, router as papers_router

# Must run before LearningOrchestrator(): ToolRegistry caches LLM client at init time
apply_settings_to_env()

_repo_root = Path(__file__).resolve().parents[3]
_question_bank = create_question_bank(
    source=settings.swigar_question_bank_source,
    database_url=settings.database_url,
    json_path=_repo_root / settings.question_bank_json_path,
    defer_postgres_load=True,
)

event_bus = EventBus()
debug_clients: list[WebSocket] = []
_health_snapshot: dict[str, Any] = {"status": "starting"}
_tools = ToolRegistry(question_bank=_question_bank)
orchestrator = LearningOrchestrator(tools=_tools)
paper_orchestrator = PaperOrchestrator(tools=_tools)
init_paper_routes(paper_orchestrator, None)


async def _persist_workflow_broadcast(message: dict[str, Any]) -> None:
    """Persist paper-orchestrator workflow steps so refresh after long组卷 still shows logs."""
    if message.get("kind") != "workflow":
        return
    data = message.get("data") or {}
    learner_id = data.get("learner_id")
    if not learner_id:
        return
    try:
        async with SessionLocal() as db:
            await WorkflowStore(db).log(
                str(learner_id),
                data.get("session_id"),
                str(message.get("category") or "info"),
                str(message.get("message") or ""),
                data if isinstance(data, dict) else None,
            )
    except Exception:
        import logging

        logging.getLogger(__name__).debug("workflow persist skipped", exc_info=True)


async def broadcast_debug(message: dict[str, Any]) -> None:
    # Do not await DB persist on the hot path — long 组卷 must not block /health or answers.
    asyncio.create_task(_persist_workflow_broadcast(message))
    dead = []
    payload = json.dumps(message, default=str)
    for ws in debug_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in debug_clients:
            debug_clients.remove(ws)


async def _load_remote_question_bank() -> None:
    src = settings.swigar_question_bank_source.lower().strip()
    if src == "auto" and settings.database_url.startswith(("postgresql", "postgres")):
        src = "postgres"
    if src != "postgres":
        return
    try:
        loaded = await asyncio.wait_for(
            fetch_questions_async(settings.database_url),
            timeout=float(os.environ.get("SWIGAR_QUESTION_BANK_LOAD_TIMEOUT", "90")),
        )
        if loaded:
            orchestrator.tools.question_bank.replace_all(loaded)
            return
        import logging

        logging.getLogger(__name__).warning("PostgreSQL question bank empty; using builtin")
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Failed to load questions from PostgreSQL")


def _refresh_health_snapshot(*, db_ready: bool, question_bank_loading: bool = False) -> None:
    global _health_snapshot
    from swigar_tools import get_llm_client

    llm = get_llm_client()
    _health_snapshot = {
        "status": "ok" if db_ready else "degraded",
        "db_ready": db_ready,
        "question_bank_loading": question_bank_loading,
        "llm_enabled": llm.enabled,
        "llm_configured": llm.is_configured,
        "llm_model": llm.model if llm.is_configured else None,
        "question_bank_count": _tools.question_bank.size,
        "paper_api": True,
        "database_url_scheme": settings.async_database_url.split("://", 1)[0],
    }


async def _load_remote_question_bank_bg(db_ready: bool) -> None:
    try:
        await asyncio.wait_for(_load_remote_question_bank(), timeout=90.0)
    except asyncio.TimeoutError:
        import logging

        logging.getLogger(__name__).warning(
            "Question bank load timed out (90s); using builtin/JSON fallback"
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Background question bank load failed")
    finally:
        _refresh_health_snapshot(db_ready=is_db_ready(), question_bank_loading=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_settings_to_env()
    from swigar_api.answer_queue import configure_answer_queue, start_answer_workers, stop_answer_workers

    # Expose LLM status immediately — do not block /health on Neon question-bank load.
    _refresh_health_snapshot(db_ready=False, question_bank_loading=True)

    db_ok = await ensure_db_ready()
    if not db_ok:
        import logging

        logging.getLogger(__name__).error(
            "init_db failed after retries — paper API needs DB. "
            "Check DATABASE_URL / Neon, or use sqlite+aiosqlite:///./swigar.db for local dev."
        )

    _refresh_health_snapshot(db_ready=is_db_ready(), question_bank_loading=True)
    bank_task = asyncio.create_task(
        _load_remote_question_bank_bg(is_db_ready()),
        name="load-question-bank",
    )

    async def debug_handler(msg: dict) -> None:
        await broadcast_debug(msg)

    event_bus.subscribe(debug_handler)
    orchestrator._trace_callback = debug_handler
    paper_orchestrator._trace_callback = debug_handler

    init_paper_routes(paper_orchestrator, broadcast_debug)
    configure_answer_queue(broadcast_debug)
    await start_answer_workers()

    yield

    bank_task.cancel()
    try:
        await bank_task
    except asyncio.CancelledError:
        pass
    await stop_answer_workers()


app = FastAPI(
    title="Swigar Learning Agent API",
    version="0.1.0",
    description="AI-driven gamified English learning agent platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers_router)


@app.get("/health")
async def health():
    """Fast liveness probe — must stay non-blocking during long paper assembly."""
    return dict(_health_snapshot)


@app.post("/v1/events")
async def ingest_events(
    events: list[LearningEvent] | LearningEvent,
    session: AsyncSession = Depends(get_session),
):
    if isinstance(events, LearningEvent):
        events = [events]
    results = []
    situation_store = SituationStore(session)
    goal_store = GoalStore(session)
    decision_store = DecisionStore(session)
    event_log = EventLogStore(session)
    trace_store = TraceStore(session)

    for event in events:
        await event_log.log(event)
        memory = LearnerMemoryStore(event.learner_id)

        async def trigger(ev: LearningEvent, signals):
            async def trace_cb(msg):
                await broadcast_debug(msg)
                if msg.get("kind") == "trace":
                    step = msg.get("step", {})
                    await trace_store.append(
                        ev.learner_id,
                        ev.session_id,
                        step.get("step", "unknown"),
                        step.get("phase", "unknown"),
                        step,
                    )

            orchestrator._trace_callback = trace_cb
            decision = await orchestrator.run(ev, signals, situation_store, goal_store, ev.learner_id)
            await decision_store.save(decision)
            await broadcast_debug({"kind": "decision", "decision": decision.model_dump(mode="json")})
            return decision

        result = await event_bus.publish(
            event,
            memory_writer=memory.write_event_verbatim,
            orchestrator_trigger=trigger,
        )
        results.append(result)
    return {"processed": len(results), "results": results}


@app.get("/v1/situation/{learner_id}")
async def get_situation(learner_id: str, session: AsyncSession = Depends(get_session)):
    situation = await SituationStore(session).get(learner_id)
    return situation.model_dump(mode="json")


@app.post("/v1/orchestrate")
async def force_orchestrate(
    learner_id: str,
    session_id: str = "debug",
    session: AsyncSession = Depends(get_session),
):
    from swigar_core.models import GameContext

    fake_event = LearningEvent(
        type=LearningEventType.ON_SESSION_START,
        learner_id=learner_id,
        session_id=session_id,
        game_context=GameContext(map_id="training_grounds", npc_id="mentor"),
        payload={},
    )
    situation_store = SituationStore(session)
    goal_store = GoalStore(session)
    decision_store = DecisionStore(session)
    decision = await orchestrator.run(fake_event, [], situation_store, goal_store, learner_id)
    await decision_store.save(decision)
    await broadcast_debug({"kind": "decision", "decision": decision.model_dump(mode="json")})
    return decision.model_dump(mode="json")


@app.get("/v1/decisions/{learner_id}/pending")
async def pending_decisions(learner_id: str, session: AsyncSession = Depends(get_session)):
    decisions = await DecisionStore(session).get_pending(learner_id)
    return [d.model_dump(mode="json") for d in decisions]


@app.post("/v1/decisions/{decision_id}/ack")
async def ack_decision(decision_id: str, session: AsyncSession = Depends(get_session)):
    ok = await DecisionStore(session).ack(decision_id)
    return {"acked": ok}


@app.get("/v1/goals")
async def list_goals(learner_id: str, session: AsyncSession = Depends(get_session)):
    goals = await GoalStore(session).list_for_learner(learner_id)
    return [g.model_dump(mode="json") for g in goals]


@app.post("/v1/goals")
async def create_goal(goal: GoalCreate, session: AsyncSession = Depends(get_session)):
    record = await GoalStore(session).create(goal)
    return record.model_dump(mode="json")


@app.get("/v1/reports/{learner_id}")
async def get_report(
    learner_id: str,
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select
    from swigar_api.db import EventLogRow
    from swigar_events.enricher import enrich_event

    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(EventLogRow).where(
            EventLogRow.learner_id == learner_id,
            EventLogRow.created_at >= since,
        )
    )
    events = []
    all_signals = []
    for row in result.scalars().all():
        ev = LearningEvent.model_validate(row.data)
        events.append(ev)
        all_signals.extend(enrich_event(ev))

    report = ReportSkill().run(learner_id, events, all_signals, since, datetime.utcnow())
    return report.model_dump(mode="json")


@app.get("/debug/traces/{session_id}")
async def debug_traces(session_id: str, session: AsyncSession = Depends(get_session)):
    traces = await TraceStore(session).list_session(session_id)
    return {"session_id": session_id, "traces": traces}


@app.websocket("/debug/stream")
async def debug_stream(websocket: WebSocket):
    await websocket.accept()
    debug_clients.append(websocket)
    await websocket.send_json({"kind": "connected", "message": "Debug stream ready"})
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"kind": "pong"})
    except WebSocketDisconnect:
        if websocket in debug_clients:
            debug_clients.remove(websocket)


def run():
    import uvicorn

    uvicorn.run("swigar_api.main:app", host=settings.api_host, port=settings.api_port, reload=True)
