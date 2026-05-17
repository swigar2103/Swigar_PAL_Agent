"""SQLAlchemy async database."""

from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Boolean, DateTime, String, Text, JSON, select, text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from swigar_api.config import settings
from swigar_tools.db_url import prepare_postgres_urls


class Base(DeclarativeBase):
    pass


class LearnerRow(Base):
    __tablename__ = "learners"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, default="")
    grade: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GoalRow(Base):
    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    skill_tags: Mapped[dict] = mapped_column(JSON, default=list)
    target_count: Mapped[int | None] = mapped_column(nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    set_by: Mapped[str] = mapped_column(String, default="parent")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SituationRow(Base):
    __tablename__ = "situation_snapshots"
    learner_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TraceRow(Base):
    __tablename__ = "orchestration_traces"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    learner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    step: Mapped[str] = mapped_column(String)
    phase: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EventLogRow(Base):
    __tablename__ = "event_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LearnerSessionRow(Base):
    __tablename__ = "learner_sessions"
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    active_paper_id: Mapped[str | None] = mapped_column(String, nullable=True)
    queued_paper_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExamPaperRow(Base):
    __tablename__ = "exam_papers"
    paper_id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    data: Mapped[dict] = mapped_column(JSON)
    current_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LearnerProfileRow(Base):
    __tablename__ = "learner_profiles"
    learner_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnswerRecordRow(Base):
    __tablename__ = "answer_records"
    __table_args__ = (UniqueConstraint("paper_id", "question_index", name="uq_answer_paper_question"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(String, index=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    question_index: Mapped[int] = mapped_column(default=-1, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LearnerQuestionReserveRow(Base):
    __tablename__ = "learner_question_reserve"
    __table_args__ = (UniqueConstraint("learner_id", "question_id", name="uq_reserve_learner_question"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    question_id: Mapped[str] = mapped_column(String)
    question_payload: Mapped[dict] = mapped_column(JSON)
    source_origin: Mapped[str] = mapped_column(String, default="carry_over")
    knowledge_point: Mapped[str] = mapped_column(String, default="")
    level: Mapped[int] = mapped_column(default=1)
    skill_tags: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowLogRow(Base):
    __tablename__ = "workflow_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String, default="info")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_db_url, _connect_args, _, _ = prepare_postgres_urls(settings.database_url)
if _db_url.startswith("postgresql"):
    import os

    _pg_timeout = float(os.environ.get("SWIGAR_PG_CONNECT_TIMEOUT", "20"))
    _connect_args = {
        **_connect_args,
        "timeout": _pg_timeout,
        "command_timeout": float(os.environ.get("SWIGAR_PG_COMMAND_TIMEOUT", "60")),
    }
engine = create_async_engine(
    _db_url if _db_url.startswith("postgresql") else settings.async_database_url,
    connect_args=_connect_args,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_answer_records)


def _migrate_answer_records(sync_conn) -> None:
    """Add question_index column and backfill from JSON data."""
    from sqlalchemy import inspect

    insp = inspect(sync_conn)
    if "answer_records" not in insp.get_table_names():
        return
    dialect = sync_conn.dialect.name
    cols = {c["name"] for c in insp.get_columns("answer_records")}
    if "question_index" not in cols:
        sync_conn.execute(text("ALTER TABLE answer_records ADD COLUMN question_index INTEGER DEFAULT -1"))
    if dialect == "sqlite":
        sync_conn.execute(
            text(
                "UPDATE answer_records SET question_index = CAST(json_extract(data, '$.question_index') AS INTEGER) "
                "WHERE question_index < 0 AND json_extract(data, '$.question_index') IS NOT NULL"
            )
        )
        try:
            sync_conn.execute(
                text(
                    "DELETE FROM answer_records WHERE rowid NOT IN ("
                    "SELECT MIN(rowid) FROM answer_records WHERE question_index >= 0 "
                    "GROUP BY paper_id, question_index)"
                )
            )
        except Exception:
            pass
    elif dialect.startswith("postgres"):
        sync_conn.execute(
            text(
                "UPDATE answer_records SET question_index = (data->>'question_index')::int "
                "WHERE question_index < 0 AND data->>'question_index' IS NOT NULL"
            )
        )
        try:
            sync_conn.execute(
                text(
                    "DELETE FROM answer_records a USING answer_records b "
                    "WHERE a.ctid < b.ctid AND a.paper_id = b.paper_id "
                    "AND a.question_index = b.question_index AND a.question_index >= 0"
                )
            )
        except Exception:
            pass
    try:
        sync_conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_answer_paper_question "
                "ON answer_records (paper_id, question_index)"
            )
        )
    except Exception:
        pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
