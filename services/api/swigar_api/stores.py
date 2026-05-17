"""Persistence stores for situation, goals, decisions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from swigar_core.models import GoalCreate, GoalRecord, LearningDecision, LearningEvent, LearningSituation
from swigar_api.db import DecisionRow, GoalRow, SituationRow, TraceRow, EventLogRow


class SituationStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, learner_id: str) -> LearningSituation:
        row = await self.session.get(SituationRow, learner_id)
        if row and row.data:
            return LearningSituation.model_validate(row.data)
        return LearningSituation(learner_id=learner_id)

    async def save(self, situation: LearningSituation) -> None:
        situation.updated_at = datetime.utcnow()
        row = await self.session.get(SituationRow, situation.learner_id)
        data = situation.model_dump(mode="json")
        if row:
            row.data = data
            row.updated_at = situation.updated_at
        else:
            self.session.add(SituationRow(learner_id=situation.learner_id, data=data, updated_at=situation.updated_at))
        await self.session.commit()


class GoalStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_learner(self, learner_id: str) -> list[GoalRecord]:
        result = await self.session.execute(select(GoalRow).where(GoalRow.learner_id == learner_id))
        rows = result.scalars().all()
        return [
            GoalRecord(
                id=r.id,
                learner_id=r.learner_id,
                title=r.title,
                skill_tags=r.skill_tags or [],
                target_count=r.target_count,
                due_at=r.due_at,
                set_by=r.set_by,
                completed=r.completed,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def create(self, goal: GoalCreate) -> GoalRecord:
        record = GoalRecord(**goal.model_dump())
        self.session.add(
            GoalRow(
                id=record.id,
                learner_id=record.learner_id,
                title=record.title,
                skill_tags=record.skill_tags,
                target_count=record.target_count,
                due_at=record.due_at,
                set_by=record.set_by,
                completed=False,
                created_at=record.created_at,
            )
        )
        await self.session.commit()
        return record


class DecisionStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, decision: LearningDecision) -> LearningDecision:
        self.session.add(
            DecisionRow(
                id=decision.id,
                learner_id=decision.learner_id,
                session_id=decision.session_id,
                data=decision.model_dump(mode="json"),
                status=decision.status,
                created_at=decision.created_at,
            )
        )
        await self.session.commit()
        return decision

    async def get_pending(self, learner_id: str) -> list[LearningDecision]:
        result = await self.session.execute(
            select(DecisionRow).where(DecisionRow.learner_id == learner_id, DecisionRow.status == "pending")
        )
        return [LearningDecision.model_validate(r.data) for r in result.scalars().all()]

    async def ack(self, decision_id: str) -> bool:
        row = await self.session.get(DecisionRow, decision_id)
        if not row:
            return False
        row.status = "acked"
        data = dict(row.data)
        data["status"] = "acked"
        row.data = data
        await self.session.commit()
        return True


class TraceStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(self, learner_id: str | None, session_id: str | None, step: str, phase: str, data: dict) -> None:
        self.session.add(
            TraceRow(learner_id=learner_id, session_id=session_id, step=step, phase=phase, data=data)
        )
        await self.session.commit()

    async def list_session(self, session_id: str) -> list[dict]:
        result = await self.session.execute(
            select(TraceRow).where(TraceRow.session_id == session_id).order_by(TraceRow.created_at)
        )
        return [
            {"step": r.step, "phase": r.phase, "data": r.data, "created_at": r.created_at.isoformat()}
            for r in result.scalars().all()
        ]


class EventLogStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, event: LearningEvent) -> None:
        self.session.add(
            EventLogRow(
                id=event.event_id,
                learner_id=event.learner_id,
                session_id=event.session_id,
                event_type=event.type.value,
                data=event.model_dump(mode="json"),
                created_at=event.timestamp,
            )
        )
        await self.session.commit()
