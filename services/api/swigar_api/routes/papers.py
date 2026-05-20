"""Exam paper REST API."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from swigar_core.models import (
    AnswerRecord,
    ExamPaper,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from swigar_orchestrator.paper_orchestrator import PaperOrchestrator

from swigar_api.answer_queue import (
    AnswerPersistJob,
    MemoryWriteJob,
    enqueue_answer_persist,
    enqueue_memory_write,
    set_paper_orchestrator as set_queue_paper_orchestrator,
)

from swigar_api.config import settings
from swigar_api.db import SessionLocal, get_session
from swigar_api.db_ready import ensure_db_ready, is_db_ready
from swigar_core.models import QuestionItem
from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer

from swigar_api.paper_stores import (
    AnswerStore,
    PaperStore,
    ProfileStore,
    ReserveStore,
    SessionStore,
    WorkflowStore,
    normalize_question_fields,
)

router = APIRouter(prefix="/v1", tags=["papers"])

_paper_orchestrator: PaperOrchestrator | None = None
_broadcast_debug = None
_assembly_locks: dict[str, asyncio.Lock] = {}
_prefetch_tasks: dict[str, asyncio.Task] = {}
_prefetch_semaphores: dict[str, asyncio.Semaphore] = {}


def _reserve_store(db) -> ReserveStore:
    return ReserveStore(db, ttl_days=settings.swigar_reserve_ttl_days)


async def _load_history_exclude_ids(db, learner_id: str) -> list[str]:
    """近期答对题 ID，组卷时从题库/reserve 检索中排除。"""
    return await AnswerStore(db).list_recent_correct_ids(learner_id)


def init_paper_routes(orchestrator: PaperOrchestrator, broadcast_fn) -> None:
    global _paper_orchestrator, _broadcast_debug
    _paper_orchestrator = orchestrator
    _broadcast_debug = broadcast_fn
    set_queue_paper_orchestrator(orchestrator)


async def _generate_paper_isolated(
    orchestrator: PaperOrchestrator,
    learner_id: str,
    session_id: str,
    profile: Any,
    *,
    method: str = "full",
    **kwargs: Any,
) -> ExamPaper | tuple[ExamPaper, list[dict], set[str]]:
    """Run async组卷 in a worker thread so /health and other routes stay responsive."""
    main_loop = asyncio.get_running_loop()
    orchestrator._trace_loop = main_loop

    async def _coro():
        history_exclude_ids = kwargs.pop("history_exclude_ids", None)
        if method == "cold_start":
            return await orchestrator.generate_cold_start_paper(
                learner_id,
                session_id,
                profile,
                status=kwargs.get("status", "active"),
                history_exclude_ids=history_exclude_ids,
            )
        if method == "hybrid":
            reserve = kwargs.pop("reserve_questions", [])
            return await orchestrator.complete_paper_from_reserve(
                learner_id,
                session_id,
                profile,
                reserve,
                status=kwargs.get("status", "active"),
                last_accuracy=kwargs.get("last_accuracy"),
                mistake_candidates=kwargs.get("mistake_candidates"),
                history_exclude_ids=history_exclude_ids,
            )
        return await orchestrator.generate_paper(
            learner_id, session_id, profile, history_exclude_ids=history_exclude_ids, **kwargs
        )

    def _run():
        return asyncio.run(_coro())

    return await asyncio.to_thread(_run)


async def _harvest_paper_to_reserve(
    db,
    learner_id: str,
    paper: ExamPaper,
    *,
    source_origin: str,
) -> int:
    astore = AnswerStore(db)
    answered = await astore.list_indexed_for_paper(paper.paper_id)
    return await _reserve_store(db).harvest_unanswered_from_paper(
        learner_id, paper, set(answered.keys()), source_origin=source_origin
    )


async def _persist_surplus_raw(db, learner_id: str, surplus_raw: list[dict], plan_kp: str) -> None:
    if not surplus_raw:
        return
    reserve = _reserve_store(db)
    for c in surplus_raw[:20]:
        choices = normalize_choices(list(c.get("choices") or c.get("options") or []))
        correct = normalize_correct_answer(
            str(c.get("correct_answer") or c.get("answer") or ""), choices
        )
        if not choices or not correct:
            continue
        qid = str(c.get("id") or f"surplus_{uuid4().hex[:10]}")
        q = QuestionItem(
            id=qid,
            source="generated",
            skill_tags=list(c.get("skill_tags") or []),
            knowledge_point=str(c.get("knowledge_point") or plan_kp),
            level=max(1, min(5, int(c.get("level") or c.get("difficulty") or 2))),
            prompt=str(c.get("prompt") or c.get("stem") or ""),
            correct_answer=correct,
            choices=choices,
            explanation=str(c.get("explanation") or ""),
            validation_status="passed",
            generation_meta={"source_origin": "gen_surplus"},
        )
        await reserve.upsert_question(learner_id, q, source_origin="gen_surplus")


async def _promote_queued_response(
    db,
    learner_id: str,
    sid: str,
    paper_store: PaperStore,
    session_store: SessionStore,
    *,
    message: str,
) -> dict[str, Any]:
    paper = await paper_store.promote_queued_to_active(learner_id)
    if not paper:
        raise HTTPException(500, "Failed to activate queued paper")
    await session_store.set_active_paper(sid, paper.paper_id)
    await _wf(db, learner_id, sid, "出题", message, {"module": "next_adapt", "assembly_mode": "promoted"})
    return {
        "session_id": sid,
        "paper": _paper_summary(paper),
        "from_queue": True,
        "assembly_mode": "promoted",
    }


async def _wait_for_assembly_unlock(lock: asyncio.Lock, timeout_sec: float = 600.0) -> None:
    """When workbench + game share a learner_id, the second caller should wait, not 409."""
    deadline = time.monotonic() + timeout_sec
    while lock.locked():
        if time.monotonic() >= deadline:
            raise HTTPException(
                408,
                "组卷等待超时：另一客户端正在组卷（通常 1–3 分钟）。请查看 API 终端日志。",
            )
        await asyncio.sleep(1.0)


async def _require_db_ready() -> None:
    if is_db_ready():
        return
    if await ensure_db_ready():
        return
    raise HTTPException(
        503,
        "数据库未就绪：API 启动时 init_db 失败（/health 中 db_ready=false）。"
        "请查看「Swigar API :8000」窗口日志；确认 Neon/DATABASE_URL 可连，或改用 sqlite+aiosqlite:///./swigar.db 后重启 API。",
    )


def _format_assembly_error(exc: BaseException) -> str:
    msg = str(exc).strip()
    if msg:
        return msg
    return f"{type(exc).__name__}（详见 API 终端日志）"


async def _wf(session: AsyncSession, learner_id: str, session_id: str | None, category: str, message: str, data: dict | None = None):
    await WorkflowStore(session).log(learner_id, session_id, category, message, data)
    if _broadcast_debug:
        await _broadcast_debug({"kind": "workflow", "category": category, "message": message, "data": data or {}})


@router.post("/sessions/{learner_id}/start")
async def start_session(
    learner_id: str,
    session_id: str | None = Query(None),
    fresh: bool = Query(True, description="游戏端兼容：True=放弃未完成卷并重新组卷"),
    intent: str | None = Query(
        None,
        description="工作台：next=完成当前卷后组下一卷；resume=继续当前 active 卷；promote=激活 queued。不传则按 fresh 走兼容逻辑",
    ),
):
    """Start session and bind/generate active paper.

    LLM paper generation can take minutes — must not hold a request-scoped DB
  connection (Neon/asyncpg will close it mid-flight).
    """
    if not _paper_orchestrator:
        raise HTTPException(503, "Paper orchestrator not initialized")
    await _require_db_ready()

    lock = _assembly_locks.setdefault(learner_id, asyncio.Lock())
    if lock.locked():
        await _wait_for_assembly_unlock(lock)
        async with SessionLocal() as db:
            active = await PaperStore(db).get_active_paper(learner_id)
            if active and active.status == "active":
                sess = await SessionStore(db).get_or_create(learner_id, session_id)
                return {
                    "session_id": sess.session_id,
                    "paper": _paper_summary(active),
                    "reused": True,
                    "message": "已复用刚组好的试卷（工作台/游戏共用同一 learner）",
                }

    async with lock:
        mode = intent or ("legacy_fresh" if fresh else "resume")
        try:
            result = await _start_session_body(learner_id, session_id, mode)
        except HTTPException:
            raise
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("start_session failed learner=%s mode=%s", learner_id, mode)
            raise HTTPException(503, f"组卷失败: {_format_assembly_error(exc)}") from exc
    assembly_mode = result.get("assembly_mode", "")
    skip_prefetch = assembly_mode in ("cold_start", "promoted") or result.get("reused")
    if (
        settings.swigar_prefetch_on_session_start
        and result.get("paper")
        and not skip_prefetch
        and not result.get("from_queue")
    ):
        schedule_prefetch_next(learner_id, result["session_id"])
    return result


async def _start_session_body(
    learner_id: str,
    session_id: str | None,
    mode: str,
) -> dict[str, Any]:
    profile: Any
    sid: str
    session_store: SessionStore

    async with SessionLocal() as db:
        sess = await SessionStore(db).get_or_create(learner_id, session_id)
        sid = sess.session_id
        session_store = SessionStore(db)
        profile = await ProfileStore(db).get(learner_id)
        paper_store = PaperStore(db)

        stale = await paper_store.abandon_stale_queued(learner_id, settings.swigar_queued_max_age_days)
        if stale:
            await _harvest_paper_to_reserve(db, learner_id, stale, source_origin="queued_stale")

        if mode in ("resume", "promote"):
            active = await paper_store.get_active_paper(learner_id)
            if active and active.status == "active":
                await session_store.set_active_paper(sid, active.paper_id)
                await _wf(db, learner_id, sid, "出题", f"继续当前试卷 {active.paper_id[:8]}…")
                return {
                    "session_id": sid,
                    "paper": _paper_summary(active),
                    "assembly_mode": "resumed",
                }
            queued = await paper_store.get_queued_paper(learner_id)
            if queued:
                return await _promote_queued_response(
                    db,
                    learner_id,
                    sid,
                    paper_store,
                    session_store,
                    message=f"已激活排队试卷 {queued.paper_id[:8]}…",
                )

        if mode == "next":
            active = await paper_store.get_active_paper(learner_id)
            if active and active.status == "active":
                raise HTTPException(
                    409,
                    "请先完成当前试卷并点击「完成试卷」，再使用「开始下一卷」",
                )
            queued = await paper_store.get_queued_paper(learner_id)
            if queued:
                return await _promote_queued_response(
                    db,
                    learner_id,
                    sid,
                    paper_store,
                    session_store,
                    message=f"下一卷已激活（预生成）{queued.paper_id[:8]}…",
                )

        if mode == "legacy_fresh":
            queued = await paper_store.get_queued_paper(learner_id)
            if queued:
                return await _promote_queued_response(
                    db,
                    learner_id,
                    sid,
                    paper_store,
                    session_store,
                    message=f"新局激活预生成卷 {queued.paper_id[:8]}…",
                )
            abandoned = await paper_store.abandon_active_papers(learner_id)
            for p in abandoned:
                await _harvest_paper_to_reserve(db, learner_id, p, source_origin="carry_over")

    mistake_candidates: list[dict] = []
    async with SessionLocal() as db:
        astore = AnswerStore(db)
        mistake_candidates = await astore.list_mistake_candidates(learner_id)
        unanswered = await astore.list_unanswered_candidates(learner_id)
        seen = {c["question_id"] for c in mistake_candidates}
        for u in unanswered:
            if u["question_id"] not in seen:
                mistake_candidates.append(u)
                seen.add(u["question_id"])

    assembly_mode = "full"
    paper: ExamPaper
    history_exclude_ids: list[str] = []
    async with SessionLocal() as db:
        history_exclude_ids = await _load_history_exclude_ids(db, learner_id)

    if _paper_orchestrator and PaperOrchestrator.is_cold_start(profile):
        paper = await _generate_paper_isolated(  # type: ignore[assignment]
            _paper_orchestrator,
            learner_id,
            sid,
            profile,
            method="cold_start",
            status="active",
            history_exclude_ids=history_exclude_ids,
        )
        assembly_mode = "cold_start"
    else:
        reserve_count = 0
        reserve_questions: list[QuestionItem] = []
        async with SessionLocal() as db:
            reserve_count = await _reserve_store(db).count(learner_id)
            if reserve_count >= settings.swigar_reserve_min_for_hybrid:
                reserve_questions = await _reserve_store(db).list_questions(learner_id, limit=40)

        if reserve_questions and _paper_orchestrator:
            result = await _generate_paper_isolated(
                _paper_orchestrator,
                learner_id,
                sid,
                profile,
                method="hybrid",
                status="active",
                reserve_questions=reserve_questions,
                mistake_candidates=mistake_candidates,
                history_exclude_ids=history_exclude_ids,
            )
            paper, surplus_raw, used_ids = result  # type: ignore[misc]
            assembly_mode = "hybrid"
            async with SessionLocal() as db:
                await _reserve_store(db).remove_ids(learner_id, used_ids)
                await _persist_surplus_raw(db, learner_id, surplus_raw, paper.knowledge_point)
        else:
            surplus_raw: list[dict] = []
            paper = await _generate_paper_isolated(
                _paper_orchestrator,
                learner_id,
                sid,
                profile,
                status="active",
                mistake_candidates=mistake_candidates,
                surplus_out=surplus_raw,
                history_exclude_ids=history_exclude_ids,
            )
            async with SessionLocal() as db:
                await _persist_surplus_raw(db, learner_id, surplus_raw, paper.knowledge_point)

    async with SessionLocal() as db:
        await PaperStore(db).save_paper(paper)
        await SessionStore(db).set_active_paper(sid, paper.paper_id)
        await _wf(
            db,
            learner_id,
            sid,
            "出题",
            f"学习会话已开始，当前试卷 {paper.paper_id[:8]}…",
            {"assembly_mode": assembly_mode},
        )

    return {
        "session_id": sid,
        "paper": _paper_summary(paper),
        "assembly_mode": assembly_mode,
    }


def schedule_prefetch_next(learner_id: str, session_id: str) -> None:
    """Background prefetch — LLM runs in thread pool; does not block answer API."""
    if not _paper_orchestrator:
        return
    existing = _prefetch_tasks.get(learner_id)
    if existing is not None and not existing.done():
        return

    async def _run() -> None:
        delay = max(0.0, float(settings.swigar_prefetch_delay_sec))
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with SessionLocal() as db:
                if await PaperStore(db).get_queued_paper(learner_id):
                    return
                profile = await ProfileStore(db).get(learner_id)
                if PaperOrchestrator.is_cold_start(profile):
                    return
            sem = _prefetch_semaphores.setdefault(learner_id, asyncio.Semaphore(1))
            async with sem:
                await _prefetch_next_locked(learner_id, session_id)
        finally:
            _prefetch_tasks.pop(learner_id, None)

    _prefetch_tasks[learner_id] = asyncio.create_task(_run(), name=f"prefetch-{learner_id[:8]}")


async def _prefetch_next_locked(learner_id: str, session_id: str) -> None:
    async with SessionLocal() as db:
        if await PaperStore(db).get_queued_paper(learner_id):
            return
        profile = await ProfileStore(db).get(learner_id)

    mistake_candidates: list[dict] = []
    history_exclude_ids: list[str] = []
    async with SessionLocal() as db:
        mistake_candidates = await AnswerStore(db).list_mistake_candidates(learner_id)
        history_exclude_ids = await _load_history_exclude_ids(db, learner_id)

    async with SessionLocal() as db:
        await WorkflowStore(db).log(
            learner_id,
            session_id,
            "出题",
            "后台预生成下一卷（排队，不影响当前答题）",
            {
                "module": "next_adapt",
                "phase": "queued_prefetch",
                "background": True,
            },
        )

    surplus_raw: list[dict] = []
    _paper_orchestrator.push_trace_context(
        background=True,
        phase="queued_prefetch",
        assembly_mode="full_prefetch",
    )
    try:
        paper = await _generate_paper_isolated(
            _paper_orchestrator,
            learner_id,
            session_id,
            profile,
            status="queued",
            mistake_candidates=mistake_candidates,
            surplus_out=surplus_raw,
            history_exclude_ids=history_exclude_ids,
        )
    finally:
        _paper_orchestrator.pop_trace_context("background", "phase", "assembly_mode")

    async with SessionLocal() as db:
        await PaperStore(db).save_paper(paper)
        await _persist_surplus_raw(db, learner_id, surplus_raw, paper.knowledge_point)
        await _wf(
            db,
            learner_id,
            session_id,
            "出题",
            f"下一卷已预生成（排队）{paper.paper_id[:8]}…",
            {
                "assembly_mode": "full_prefetch",
                "background": True,
                "phase": "queued_prefetch",
            },
        )


@router.get("/papers/current")
async def current_paper(learner_id: str = Query(...), db: AsyncSession = Depends(get_session)):
    paper = await PaperStore(db).get_active_paper(learner_id)
    if not paper:
        raise HTTPException(404, "No active paper")
    return _paper_summary(paper)


@router.get("/papers/{paper_id}/preview")
async def paper_preview(paper_id: str, db: AsyncSession = Depends(get_session)):
    """Workbench: stems for unanswered; answered items include feedback (no future answers)."""
    paper = await PaperStore(db).get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    answer_store = AnswerStore(db)
    answered = await answer_store.list_indexed_for_paper(paper_id)
    questions_out: list[dict[str, Any]] = []
    for i, q in enumerate(paper.questions):
        item: dict[str, Any] = {
            "index": i,
            "id": q.id,
            "source": q.source,
            "origin": getattr(q, "origin", "normal"),
            "level": q.level,
            "prompt": q.prompt,
            "choices": q.choices,
            "validation_status": q.validation_status,
        }
        rec = answered.get(i)
        if rec is not None:
            item["answered"] = True
            item["is_correct"] = bool(rec.get("is_correct"))
            item["user_answer"] = rec.get("user_answer", "")
            item["explanation"] = q.explanation or ""
        questions_out.append(item)
    return {
        "paper_id": paper_id,
        "knowledge_point": paper.knowledge_point,
        "total": len(paper.questions),
        "current_index": paper.current_index,
        "status": paper.status,
        "questions": questions_out,
    }


@router.get("/papers/{paper_id}/questions/{index}")
async def get_question(paper_id: str, index: int, db: AsyncSession = Depends(get_session)):
    paper = await PaperStore(db).get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    if index < 0 or index >= len(paper.questions):
        raise HTTPException(404, "Question index out of range")
    q = paper.questions[index]
    return {
        "paper_id": paper_id,
        "index": index,
        "total": len(paper.questions),
        "current_index": paper.current_index,
        "source": q.source,
        "origin": getattr(q, "origin", "normal") or "normal",
        "level": q.level,
        "knowledge_point": q.knowledge_point,
        "type": q.type,
        "prompt": q.prompt,
        "choices": q.choices,
    }


async def _broadcast(module: str, category: str, message: str, data: dict | None = None) -> None:
    payload = {"kind": "workflow", "category": category, "message": message, "data": {**(data or {}), "module": module}}
    if _broadcast_debug:
        await _broadcast_debug(payload)


@router.post("/papers/{paper_id}/answers")
async def post_answer(
    paper_id: str,
    body: SubmitAnswerRequest,
):
    """Rule-based grading returns immediately; DB + MemPalace go to background queues."""
    if not _paper_orchestrator:
        raise HTTPException(503, "Paper orchestrator not initialized")
    async with SessionLocal() as read_db:
        paper = await PaperStore(read_db).get_paper(paper_id)
        if not paper:
            raise HTTPException(404, "Paper not found")
        if paper.status != "active":
            raise HTTPException(409, "Paper is not active")
        idx = paper.current_index
        if body.question_index is not None:
            req = body.question_index
            if req < 0 or req >= len(paper.questions):
                raise HTTPException(400, "Invalid question_index")
            # Idempotent retry: question already graded (e.g. double-click / slow client).
            prior = await AnswerStore(read_db).get_for_paper_index(paper_id, req)
            if prior:
                await _ensure_paper_index_advanced(paper_id, req)
                paper = await PaperStore(read_db).get_paper(paper_id)
                if not paper:
                    raise HTTPException(404, "Paper not found")
                return _answer_from_existing(paper, req, prior)
            if req != idx:
                raise HTTPException(409, "Must answer current question in order")
        if idx < 0 or idx >= len(paper.questions):
            raise HTTPException(400, "No more questions on this paper")
        existing = await AnswerStore(read_db).get_for_paper_index(paper_id, idx)
        if existing:
            await _ensure_paper_index_advanced(paper_id, idx)
            paper = await PaperStore(read_db).get_paper(paper_id)
            if not paper:
                raise HTTPException(404, "Paper not found")
            return _answer_from_existing(paper, idx, existing)

    await _broadcast("event_bus", "答题", f"onAnswer 第 {idx + 1} 题", {"index": idx, "paper_id": paper_id})

    resp, record_data = await _paper_orchestrator.submit_answer(
        paper, idx, body.user_answer, body.time_spent_ms, None
    )

    paper.current_index = idx + 1
    record = AnswerRecord(
        paper_id=paper_id,
        learner_id=paper.learner_id,
        question_index=idx,
        question_id=record_data["question_id"],
        user_answer=body.user_answer,
        is_correct=record_data["is_correct"],
        time_spent_ms=body.time_spent_ms,
    )
    cat = "记忆" if record.is_correct else "调整"
    wf_message = f"第 {idx + 1} 题 {'正确' if record.is_correct else '错误'}"

    await _broadcast(
        "evaluator",
        cat,
        wf_message,
        {"index": idx, "is_correct": record.is_correct, "question_id": record.question_id},
    )

    async with SessionLocal() as write_db:
        saved = await AnswerStore(write_db).save(record)
        if not saved:
            prior = await AnswerStore(write_db).get_for_paper_index(paper_id, idx)
            if prior:
                paper = await PaperStore(write_db).get_paper(paper_id)
                if paper:
                    return _answer_from_existing(paper, idx, prior)
            raise HTTPException(409, "Question already answered")
        await PaperStore(write_db).save_paper(paper)

    fb_q = settings.swigar_prefetch_fallback_at_question
    trigger_prefetch = fb_q > 0 and idx >= (fb_q - 1)

    enqueue_answer_persist(
        AnswerPersistJob(
            record=record,
            paper=paper,
            workflow_category=cat,
            workflow_message=wf_message,
            workflow_data={"index": idx},
            trigger_prefetch=trigger_prefetch,
            skip_record_and_paper=True,
            skip_workflow_broadcast=True,
        )
    )
    enqueue_memory_write(
        MemoryWriteJob(
            learner_id=paper.learner_id,
            session_id=paper.session_id,
            paper_id=paper_id,
            question_index=idx,
            is_correct=record.is_correct,
            skill_tags=list(paper.questions[idx].skill_tags),
        )
    )

    resp.next_paper_ready = False
    return resp.model_dump(mode="json")


@router.post("/papers/{paper_id}/finish")
async def finish_paper(paper_id: str, db: AsyncSession = Depends(get_session)):
    from swigar_skills.next_paper_adapt import NextPaperAdaptSkill

    paper_store = PaperStore(db)
    paper = await paper_store.get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    records = await AnswerStore(db).list_for_paper(paper_id)
    profile_store = ProfileStore(db)
    profile = await profile_store.get(paper.learner_id)
    profile = NextPaperAdaptSkill().update_profile_from_paper(profile, paper, records)
    await profile_store.save(profile)

    paper.status = "completed"
    paper.completed_at = datetime.utcnow()
    await paper_store.save_paper(paper)

    await _wf(
        db,
        paper.learner_id,
        paper.session_id,
        "调整",
        "本卷已完成；请点击「开始下一卷」生成或激活下一份试卷",
        {"module": "next_adapt"},
    )

    return {
        "paper_id": paper_id,
        "status": "completed",
        "profile": profile.model_dump(mode="json"),
        "next_paper": None,
    }


@router.get("/papers/queue")
async def paper_queue(learner_id: str = Query(...), db: AsyncSession = Depends(get_session)):
    queued = await PaperStore(db).get_queued_paper(learner_id)
    return {"ready": queued is not None, "paper": _paper_summary(queued) if queued else None}


@router.get("/learners/{learner_id}/reserve")
async def learner_reserve(learner_id: str, db: AsyncSession = Depends(get_session)):
    await _require_db_ready()
    try:
        count = await _reserve_store(db).count(learner_id)
    except Exception:
        count = 0
    return {"learner_id": learner_id, "reserve_count": count}


@router.get("/learners/{learner_id}/profile")
async def learner_profile(learner_id: str, db: AsyncSession = Depends(get_session)):
    await _require_db_ready()
    profile = await ProfileStore(db).get(learner_id)
    return profile.model_dump(mode="json")


@router.get("/learners/{learner_id}/workflow")
async def learner_workflow(
    learner_id: str,
    since: str | None = Query(None, description="ISO8601：仅返回此时间之后的日志"),
    db: AsyncSession = Depends(get_session),
):
    await _require_db_ready()
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo:
                since_dt = since_dt.replace(tzinfo=None)
        except ValueError:
            raise HTTPException(400, "Invalid since timestamp") from None
    logs = await WorkflowStore(db).recent(learner_id, limit=80, since=since_dt)
    paper = await PaperStore(db).get_active_paper(learner_id)
    try:
        reserve_count = await _reserve_store(db).count(learner_id)
    except Exception:
        reserve_count = 0
    return {
        "active_paper": _paper_summary(paper) if paper else None,
        "workflow_logs": logs,
        "reserve_count": reserve_count,
    }


async def _ensure_paper_index_advanced(paper_id: str, answered_index: int) -> None:
    """Repair papers where an answer row exists but current_index was not advanced."""
    async with SessionLocal() as write_db:
        paper = await PaperStore(write_db).get_paper(paper_id)
        if not paper:
            return
        needed = answered_index + 1
        if paper.current_index < needed:
            paper.current_index = needed
            await PaperStore(write_db).save_paper(paper)


def _answer_from_existing(paper: ExamPaper, idx: int, record: dict) -> dict[str, Any]:
    from swigar_tools.registry import ToolRegistry

    q = paper.questions[idx]
    normalize_question_fields(q)
    ev = ToolRegistry().evaluator.evaluate(
        str(record.get("user_answer", "")),
        q.correct_answer,
        q.model_dump(),
    )
    return SubmitAnswerResponse(
        is_correct=bool(ev["is_correct"]),
        correct_answer=str(ev.get("correct_answer") or q.correct_answer),
        explanation=q.explanation or "",
        feedback=str(ev.get("feedback") or "Already graded."),
        question_index=idx,
        paper_finished=idx >= len(paper.questions) - 1,
        next_paper_ready=False,
    ).model_dump(mode="json")


def _paper_summary(paper: ExamPaper | None) -> dict[str, Any] | None:
    if not paper:
        return None
    return {
        "paper_id": paper.paper_id,
        "learner_id": paper.learner_id,
        "session_id": paper.session_id,
        "knowledge_point": paper.knowledge_point,
        "status": paper.status,
        "strategy": paper.strategy,
        "rationale": paper.rationale,
        "current_index": paper.current_index,
        "total_questions": paper.total_questions,
        "questions_meta": [
            {
                "index": i,
                "id": q.id,
                "source": q.source,
                "origin": getattr(q, "origin", "normal"),
                "level": q.level,
                "validation_status": q.validation_status,
            }
            for i, q in enumerate(paper.questions)
        ],
    }
