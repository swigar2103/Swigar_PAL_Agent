"""Background queues: instant answer API, deferred DB + MemPalace."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from swigar_core.models import AnswerRecord, ExamPaper, LearnerProfile, LearningEvent, LearningEventType
from swigar_memory import LearnerMemoryStore

from swigar_api.db import SessionLocal
from swigar_api.paper_stores import AnswerStore, PaperStore, ProfileStore, WorkflowStore

logger = logging.getLogger(__name__)

_persist_queue: asyncio.Queue["AnswerPersistJob"] | None = None
_memory_queue: asyncio.Queue["MemoryWriteJob"] | None = None
_persist_worker_task: asyncio.Task | None = None
_memory_worker_task: asyncio.Task | None = None
_broadcast_fn = None
_paper_orchestrator = None
_enqueued_persist: set[tuple[str, int]] = set()
_enqueued_memory: set[tuple[str, int]] = set()


def set_paper_orchestrator(orchestrator) -> None:
    global _paper_orchestrator
    _paper_orchestrator = orchestrator


@dataclass
class AnswerPersistJob:
    record: AnswerRecord
    paper: ExamPaper
    workflow_category: str
    workflow_message: str
    workflow_data: dict[str, Any]
    trigger_prefetch: bool
    skip_record_and_paper: bool = False
    skip_workflow_broadcast: bool = False


@dataclass
class MemoryWriteJob:
    learner_id: str
    session_id: str
    paper_id: str
    question_index: int
    is_correct: bool
    skill_tags: list[str]


def configure_answer_queue(broadcast_fn) -> None:
    global _broadcast_fn
    _broadcast_fn = broadcast_fn


def _verbose_workflow() -> bool:
    return os.environ.get("SWIGAR_VERBOSE_WORKFLOW", "false").lower() in ("1", "true", "yes")


async def start_answer_workers() -> None:
    global _persist_queue, _memory_queue, _persist_worker_task, _memory_worker_task
    _persist_queue = asyncio.Queue()
    _memory_queue = asyncio.Queue()
    _persist_worker_task = asyncio.create_task(_persist_worker_loop(), name="answer-persist-worker")
    _memory_worker_task = asyncio.create_task(_memory_worker_loop(), name="memory-write-worker")
    logger.info("Answer persist + MemPalace memory workers started")


async def stop_answer_workers() -> None:
    global _persist_worker_task, _memory_worker_task
    for task in (_persist_worker_task, _memory_worker_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _persist_worker_task = None
    _memory_worker_task = None


def enqueue_answer_persist(job: AnswerPersistJob) -> None:
    key = (job.record.paper_id, job.record.question_index)
    if key in _enqueued_persist:
        return
    _enqueued_persist.add(key)
    if _persist_queue is None:
        asyncio.create_task(_run_persist_job(job))
        return
    _persist_queue.put_nowait(job)


def enqueue_memory_write(job: MemoryWriteJob) -> None:
    key = (job.paper_id, job.question_index)
    if key in _enqueued_memory:
        return
    _enqueued_memory.add(key)
    if _memory_queue is None:
        asyncio.create_task(_run_memory_job(job))
        return
    _memory_queue.put_nowait(job)


async def _persist_worker_loop() -> None:
    assert _persist_queue is not None
    while True:
        job = await _persist_queue.get()
        try:
            await _run_persist_job(job)
        except Exception:
            logger.exception("Answer persist job failed paper=%s", job.paper.paper_id)
        finally:
            _persist_queue.task_done()
            _enqueued_persist.discard((job.record.paper_id, job.record.question_index))


async def _memory_worker_loop() -> None:
    assert _memory_queue is not None
    while True:
        job = await _memory_queue.get()
        try:
            await _run_memory_job(job)
        except Exception:
            logger.exception("Memory write job failed learner=%s", job.learner_id)
        finally:
            _memory_queue.task_done()
            _enqueued_memory.discard((job.paper_id, job.question_index))


async def _run_persist_job(job: AnswerPersistJob) -> None:
    async with SessionLocal() as db:
        profile = await ProfileStore(db).get(job.record.learner_id)
        profile.total_answers += 1
        if job.record.is_correct:
            profile.total_correct += 1
        if job.record.time_spent_ms > 0:
            n = profile.total_answers
            profile.avg_response_ms = (
                (profile.avg_response_ms * (n - 1) + job.record.time_spent_ms) / n if n > 1 else job.record.time_spent_ms
            )
        if not job.skip_record_and_paper:
            await AnswerStore(db).save(job.record)
            await PaperStore(db).save_paper(job.paper)
        await ProfileStore(db).save(profile)
        await WorkflowStore(db).log(
            job.record.learner_id,
            job.paper.session_id,
            job.workflow_category,
            job.workflow_message,
            job.workflow_data,
        )
    if _broadcast_fn and not job.skip_workflow_broadcast:
        await _broadcast_fn(
            {
                "kind": "workflow",
                "category": job.workflow_category,
                "message": job.workflow_message,
                "data": {**job.workflow_data, "module": "situation"},
            }
        )
    if job.trigger_prefetch:
        from swigar_api.routes.papers import schedule_prefetch_next

        schedule_prefetch_next(job.record.learner_id, job.paper.session_id)


def _sync_memory_write(job: MemoryWriteJob) -> None:
    event_id = str(uuid5(NAMESPACE_URL, f"{job.paper_id}:{job.question_index}"))
    memory = LearnerMemoryStore(job.learner_id)
    memory.write_event_verbatim(
        LearningEvent(
            event_id=event_id,
            type=LearningEventType.ON_ANSWER if not job.is_correct else LearningEventType.ON_CORRECT,
            learner_id=job.learner_id,
            session_id=job.session_id,
            payload={
                "paper_id": job.paper_id,
                "question_index": job.question_index,
                "is_correct": job.is_correct,
                "skill_tags": job.skill_tags,
            },
        )
    )


async def _run_memory_job(job: MemoryWriteJob) -> None:
    await asyncio.to_thread(_sync_memory_write, job)
    if _broadcast_fn and _verbose_workflow():
        await _broadcast_fn(
            {
                "kind": "workflow",
                "category": "记忆",
                "message": f"MemPalace 已写入第 {job.question_index + 1} 题作答记录",
                "data": {"module": "memory", "index": job.question_index, "is_correct": job.is_correct},
            }
        )
