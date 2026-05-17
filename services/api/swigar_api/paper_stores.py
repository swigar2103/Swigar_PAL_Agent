"""Paper, profile, session persistence."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from swigar_core.models import AnswerRecord, ExamPaper, LearnerProfile, QuestionItem
from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer
from swigar_api.db import (
    AnswerRecordRow,
    ExamPaperRow,
    LearnerProfileRow,
    LearnerQuestionReserveRow,
    LearnerSessionRow,
    WorkflowLogRow,
)


def normalize_question_fields(q: QuestionItem) -> None:
    """Map bank letter keys (A/B/C) to choice text for grading."""
    q.choices = normalize_choices(list(q.choices))
    q.correct_answer = normalize_correct_answer(q.correct_answer, q.choices)


class PaperStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_paper(self, paper: ExamPaper) -> ExamPaper:
        data = paper.model_dump(mode="json")
        row = await self.session.get(ExamPaperRow, paper.paper_id)
        if row:
            row.data = data
            row.status = paper.status
            row.current_index = paper.current_index
            row.completed_at = paper.completed_at
        else:
            self.session.add(
                ExamPaperRow(
                    paper_id=paper.paper_id,
                    learner_id=paper.learner_id,
                    session_id=paper.session_id,
                    status=paper.status,
                    data=data,
                    current_index=paper.current_index,
                    created_at=paper.created_at,
                    completed_at=paper.completed_at,
                )
            )
        await self.session.commit()
        return paper

    async def get_paper(self, paper_id: str) -> ExamPaper | None:
        row = await self.session.get(ExamPaperRow, paper_id)
        if not row:
            return None
        paper = ExamPaper.model_validate(row.data)
        for q in paper.questions:
            normalize_question_fields(q)
        return paper

    async def get_active_paper(self, learner_id: str) -> ExamPaper | None:
        result = await self.session.execute(
            select(ExamPaperRow)
            .where(ExamPaperRow.learner_id == learner_id, ExamPaperRow.status == "active")
            .order_by(ExamPaperRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return ExamPaper.model_validate(row.data)

    async def get_queued_paper(self, learner_id: str) -> ExamPaper | None:
        result = await self.session.execute(
            select(ExamPaperRow)
            .where(ExamPaperRow.learner_id == learner_id, ExamPaperRow.status == "queued")
            .order_by(ExamPaperRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return ExamPaper.model_validate(row.data)

    async def abandon_learner_papers(self, learner_id: str, *, include_queued: bool = False) -> int:
        """Mark papers abandoned. By default only active; queued preserved unless include_queued."""
        statuses = ("active", "queued") if include_queued else ("active",)
        result = await self.session.execute(
            select(ExamPaperRow).where(
                ExamPaperRow.learner_id == learner_id,
                ExamPaperRow.status.in_(statuses),
            )
        )
        count = 0
        now = datetime.utcnow()
        for row in result.scalars().all():
            paper = ExamPaper.model_validate(row.data)
            paper.status = "abandoned"
            paper.completed_at = now
            row.data = paper.model_dump(mode="json")
            row.status = "abandoned"
            row.completed_at = now
            count += 1
        if count:
            await self.session.commit()
        return count

    async def abandon_active_papers(self, learner_id: str) -> list[ExamPaper]:
        """Abandon only active papers; return abandoned papers for reserve harvest."""
        result = await self.session.execute(
            select(ExamPaperRow).where(
                ExamPaperRow.learner_id == learner_id,
                ExamPaperRow.status == "active",
            )
        )
        abandoned: list[ExamPaper] = []
        now = datetime.utcnow()
        for row in result.scalars().all():
            paper = ExamPaper.model_validate(row.data)
            paper.status = "abandoned"
            paper.completed_at = now
            row.data = paper.model_dump(mode="json")
            row.status = "abandoned"
            row.completed_at = now
            abandoned.append(paper)
        if abandoned:
            await self.session.commit()
        return abandoned

    async def abandon_stale_queued(self, learner_id: str, max_age_days: int) -> ExamPaper | None:
        """Abandon queued paper older than max_age_days; return it for reserve harvest."""
        queued = await self.get_queued_paper(learner_id)
        if not queued or not queued.created_at:
            return None
        age = datetime.utcnow() - queued.created_at
        if age <= timedelta(days=max_age_days):
            return None
        row = await self.session.get(ExamPaperRow, queued.paper_id)
        if not row:
            return None
        now = datetime.utcnow()
        queued.status = "abandoned"
        queued.completed_at = now
        row.data = queued.model_dump(mode="json")
        row.status = "abandoned"
        row.completed_at = now
        await self.session.commit()
        return queued

    async def list_abandoned_papers(self, learner_id: str, limit: int = 5) -> list[ExamPaper]:
        result = await self.session.execute(
            select(ExamPaperRow)
            .where(ExamPaperRow.learner_id == learner_id, ExamPaperRow.status == "abandoned")
            .order_by(ExamPaperRow.created_at.desc())
            .limit(limit)
        )
        return [ExamPaper.model_validate(r.data) for r in result.scalars().all()]

    async def promote_queued_to_active(self, learner_id: str) -> ExamPaper | None:
        queued = await self.get_queued_paper(learner_id)
        if not queued:
            return None
        active = await self.get_active_paper(learner_id)
        if active:
            active.status = "completed"
            active.completed_at = datetime.utcnow()
            await self.save_paper(active)
        queued.status = "active"
        return await self.save_paper(queued)


class ReserveStore:
    def __init__(self, session: AsyncSession, ttl_days: int = 30):
        self.session = session
        self.ttl_days = ttl_days

    async def prune_expired(self, learner_id: str) -> None:
        now = datetime.utcnow()
        await self.session.execute(
            delete(LearnerQuestionReserveRow).where(
                LearnerQuestionReserveRow.learner_id == learner_id,
                LearnerQuestionReserveRow.expires_at.is_not(None),
                LearnerQuestionReserveRow.expires_at < now,
            )
        )
        await self.session.commit()

    async def count(self, learner_id: str) -> int:
        await self.prune_expired(learner_id)
        result = await self.session.execute(
            select(LearnerQuestionReserveRow).where(
                LearnerQuestionReserveRow.learner_id == learner_id
            )
        )
        return len(list(result.scalars().all()))

    async def upsert_question(
        self,
        learner_id: str,
        question: QuestionItem,
        *,
        source_origin: str = "carry_over",
    ) -> None:
        expires = datetime.utcnow() + timedelta(days=self.ttl_days)
        payload = question.model_dump(mode="json")
        existing = await self.session.execute(
            select(LearnerQuestionReserveRow).where(
                LearnerQuestionReserveRow.learner_id == learner_id,
                LearnerQuestionReserveRow.question_id == question.id,
            )
        )
        row = existing.scalar_one_or_none()
        tags = list(question.skill_tags or [])
        if row:
            row.question_payload = payload
            row.source_origin = source_origin
            row.knowledge_point = question.knowledge_point or ""
            row.level = int(question.level or 1)
            row.skill_tags = tags
            row.expires_at = expires
        else:
            self.session.add(
                LearnerQuestionReserveRow(
                    learner_id=learner_id,
                    question_id=question.id,
                    question_payload=payload,
                    source_origin=source_origin,
                    knowledge_point=question.knowledge_point or "",
                    level=int(question.level or 1),
                    skill_tags=tags,
                    expires_at=expires,
                )
            )
        await self.session.commit()

    async def list_questions(self, learner_id: str, limit: int = 40) -> list[QuestionItem]:
        await self.prune_expired(learner_id)
        result = await self.session.execute(
            select(LearnerQuestionReserveRow)
            .where(LearnerQuestionReserveRow.learner_id == learner_id)
            .order_by(LearnerQuestionReserveRow.created_at.desc())
            .limit(limit)
        )
        out: list[QuestionItem] = []
        for row in result.scalars().all():
            q = QuestionItem.model_validate(row.question_payload)
            normalize_question_fields(q)
            if row.source_origin == "carry_over":
                q.origin = "carry_over"
            out.append(q)
        return out

    async def remove_ids(self, learner_id: str, question_ids: set[str]) -> None:
        if not question_ids:
            return
        await self.session.execute(
            delete(LearnerQuestionReserveRow).where(
                LearnerQuestionReserveRow.learner_id == learner_id,
                LearnerQuestionReserveRow.question_id.in_(question_ids),
            )
        )
        await self.session.commit()

    async def harvest_unanswered_from_paper(
        self,
        learner_id: str,
        paper: ExamPaper,
        answered_indices: set[int],
        *,
        source_origin: str = "carry_over",
    ) -> int:
        n = 0
        for i in range(paper.current_index, len(paper.questions)):
            if i in answered_indices:
                continue
            q = paper.questions[i]
            await self.upsert_question(learner_id, q, source_origin=source_origin)
            n += 1
        return n


class ProfileStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, learner_id: str) -> LearnerProfile:
        row = await self.session.get(LearnerProfileRow, learner_id)
        if row and row.data:
            return LearnerProfile.model_validate(row.data)
        return LearnerProfile(learner_id=learner_id)

    async def save(self, profile: LearnerProfile) -> LearnerProfile:
        profile.updated_at = datetime.utcnow()
        data = profile.model_dump(mode="json")
        row = await self.session.get(LearnerProfileRow, profile.learner_id)
        if row:
            row.data = data
            row.updated_at = profile.updated_at
        else:
            self.session.add(
                LearnerProfileRow(learner_id=profile.learner_id, data=data, updated_at=profile.updated_at)
            )
        await self.session.commit()
        return profile


class SessionStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, learner_id: str, session_id: str | None = None) -> LearnerSessionRow:
        sid = session_id or str(uuid4())
        row = await self.session.get(LearnerSessionRow, sid)
        if row:
            return row
        row = LearnerSessionRow(session_id=sid, learner_id=learner_id)
        self.session.add(row)
        await self.session.commit()
        return row

    async def set_active_paper(self, session_id: str, paper_id: str | None) -> None:
        row = await self.session.get(LearnerSessionRow, session_id)
        if row:
            row.active_paper_id = paper_id
            row.updated_at = datetime.utcnow()
            await self.session.commit()

    async def set_queued_paper(self, session_id: str, paper_id: str | None) -> None:
        row = await self.session.get(LearnerSessionRow, session_id)
        if row:
            row.queued_paper_id = paper_id
            row.updated_at = datetime.utcnow()
            await self.session.commit()


class AnswerStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, record: AnswerRecord) -> bool:
        """Insert answer row. Returns False if (paper_id, question_index) already exists."""
        from sqlalchemy.exc import IntegrityError

        row = AnswerRecordRow(
            id=record.id,
            paper_id=record.paper_id,
            learner_id=record.learner_id,
            question_index=record.question_index,
            data=record.model_dump(mode="json"),
            created_at=record.created_at,
        )
        self.session.add(row)
        try:
            await self.session.commit()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False

    async def list_for_paper(self, paper_id: str) -> list[dict]:
        result = await self.session.execute(
            select(AnswerRecordRow).where(AnswerRecordRow.paper_id == paper_id)
        )
        return [r.data for r in result.scalars().all()]

    async def list_indexed_for_paper(self, paper_id: str) -> dict[int, dict]:
        records = await self.list_for_paper(paper_id)
        indexed: dict[int, dict] = {}
        for r in records:
            idx = int(r.get("question_index", -1))
            if idx >= 0:
                indexed[idx] = r
        return indexed

    async def get_for_paper_index(self, paper_id: str, question_index: int) -> dict | None:
        indexed = await self.list_indexed_for_paper(paper_id)
        return indexed.get(question_index)

    def _exclude_recent_days(self) -> int:
        return max(0, int(os.environ.get("SWIGAR_EXCLUDE_RECENT_DAYS", "14")))

    async def list_recent_correct_ids(
        self, learner_id: str, *, since_days: int | None = None
    ) -> list[str]:
        """Question IDs answered correctly within the lookback window (cross-paper dedupe)."""
        days = self._exclude_recent_days() if since_days is None else max(0, since_days)
        if days <= 0:
            return []
        since = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(AnswerRecordRow)
            .where(
                AnswerRecordRow.learner_id == learner_id,
                AnswerRecordRow.created_at >= since,
            )
            .order_by(AnswerRecordRow.created_at.desc())
        )
        seen: set[str] = set()
        out: list[str] = []
        for row in result.scalars().all():
            data = row.data
            if not data.get("is_correct"):
                continue
            qid = str(data.get("question_id", ""))
            if not qid or qid in seen:
                continue
            seen.add(qid)
            out.append(qid)
        return out

    async def list_recent_seen_ids(
        self, learner_id: str, *, since_days: int | None = None
    ) -> list[str]:
        """All question IDs attempted (right or wrong) in the lookback window."""
        days = self._exclude_recent_days() if since_days is None else max(0, since_days)
        if days <= 0:
            return []
        since = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(AnswerRecordRow)
            .where(
                AnswerRecordRow.learner_id == learner_id,
                AnswerRecordRow.created_at >= since,
            )
            .order_by(AnswerRecordRow.created_at.desc())
        )
        seen: set[str] = set()
        out: list[str] = []
        for row in result.scalars().all():
            qid = str(row.data.get("question_id", ""))
            if not qid or qid in seen:
                continue
            seen.add(qid)
            out.append(qid)
        return out

    async def list_mistake_candidates(self, learner_id: str, limit: int = 30) -> list[dict]:
        """Distinct wrong answers across all papers, most recent first."""
        result = await self.session.execute(
            select(AnswerRecordRow)
            .where(AnswerRecordRow.learner_id == learner_id)
            .order_by(AnswerRecordRow.created_at.desc())
            .limit(limit * 5)
        )
        seen: set[str] = set()
        out: list[dict] = []
        for row in result.scalars().all():
            data = row.data
            if data.get("is_correct"):
                continue
            qid = str(data.get("question_id", ""))
            if not qid or qid in seen:
                continue
            seen.add(qid)
            out.append(
                {
                    "question_id": qid,
                    "paper_id": row.paper_id,
                    "question_index": int(data.get("question_index", 0)),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
            if len(out) >= limit:
                break
        return out

    async def list_unanswered_candidates(self, learner_id: str, limit: int = 20) -> list[dict]:
        """Unanswered question slots from abandoned papers (for next-paper assembly)."""
        papers = await PaperStore(self.session).list_abandoned_papers(learner_id, limit=8)
        answered_by_paper: dict[str, set[int]] = {}
        for paper in papers:
            recs = await self.list_for_paper(paper.paper_id)
            answered_by_paper[paper.paper_id] = {int(r.get("question_index", -1)) for r in recs}

        out: list[dict] = []
        seen: set[str] = set()
        for paper in papers:
            answered = answered_by_paper.get(paper.paper_id, set())
            for i in range(paper.current_index, len(paper.questions)):
                if i in answered:
                    continue
                q = paper.questions[i]
                if q.id in seen:
                    continue
                seen.add(q.id)
                out.append(
                    {
                        "question_id": q.id,
                        "paper_id": paper.paper_id,
                        "question_index": i,
                        "source": "unanswered_carry",
                    }
                )
                if len(out) >= limit:
                    return out
        return out


class WorkflowStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, learner_id: str, session_id: str | None, category: str, message: str, data: dict | None = None) -> None:
        self.session.add(
            WorkflowLogRow(
                learner_id=learner_id,
                session_id=session_id,
                category=category,
                message=message,
                data=data or {},
            )
        )
        await self.session.commit()

    async def recent(
        self,
        learner_id: str,
        limit: int = 30,
        *,
        since: datetime | None = None,
    ) -> list[dict]:
        q = select(WorkflowLogRow).where(WorkflowLogRow.learner_id == learner_id)
        if since is not None:
            q = q.where(WorkflowLogRow.created_at >= since)
        result = await self.session.execute(
            q.order_by(WorkflowLogRow.created_at.desc()).limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            {
                "category": r.category,
                "message": r.message,
                "data": r.data,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
