"""Domain models shared across the Swigar agent platform."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class LearningEventType(str, Enum):
    ON_SESSION_START = "onSessionStart"
    ON_ANSWER = "onAnswer"
    ON_MISTAKE = "onMistake"
    ON_TASK_DONE = "onTaskDone"
    ON_LOW_ENGAGE = "onLowEngage"
    ON_DIALOGUE = "onDialogue"
    ON_PAPER_GENERATED = "onPaperGenerated"
    ON_QUESTION_PRESENTED = "onQuestionPresented"
    ON_CORRECT = "onCorrect"
    ON_PAPER_FINISHED = "onPaperFinished"
    ON_NEED_NEXT_PAPER = "onNeedNextPaper"
    ON_MEMORY_WRITE = "onMemoryWrite"
    ON_AGENT_PLAN_UPDATED = "onAgentPlanUpdated"


class GameContext(BaseModel):
    map_id: str | None = None
    room_id: str | None = None
    npc_id: str | None = None
    quest_id: str | None = None
    level: int | None = None


class LearningEvent(BaseModel):
    type: LearningEventType
    learner_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    game_context: GameContext = Field(default_factory=GameContext)
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str = Field(default_factory=lambda: str(uuid4()))


class SignalType(str, Enum):
    GRAMMAR_WEAKNESS = "grammar_weakness"
    VOCAB_WEAKNESS = "vocab_weakness"
    ENGAGEMENT_DROP = "engagement_drop"
    MASTERY_GAIN = "mastery_gain"
    TASK_STRUGGLE = "task_struggle"


class LearningSignal(BaseModel):
    signal_type: SignalType
    skill_tag: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)
    detail: str = ""


ActionType = Literal[
    "assign_task",
    "npc_dialogue",
    "dungeon_quiz",
    "feedback_reward",
    "hint",
    "difficulty_adjust",
]


class LearningDecision(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    session_id: str | None = None
    action_type: ActionType
    narrative_hook: str
    content: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    memory_refs: list[str] = Field(default_factory=list)
    status: Literal["pending", "acked", "expired"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LearnerState(BaseModel):
    level: int = 1
    xp: int = 0
    streak_days: int = 0
    energy: float = 1.0


class LearningSituation(BaseModel):
    learner_id: str
    learner_state: LearnerState = Field(default_factory=LearnerState)
    recent_events: list[LearningEvent] = Field(default_factory=list)
    dialogue_history: list[dict[str, Any]] = Field(default_factory=list)
    world_state: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GoalCreate(BaseModel):
    learner_id: str
    title: str
    skill_tags: list[str] = Field(default_factory=list)
    target_count: int | None = None
    due_at: datetime | None = None
    set_by: Literal["teacher", "parent", "system"] = "parent"


class GoalRecord(GoalCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed: bool = False


class TraceStep(BaseModel):
    step: str
    phase: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DiagnosisResult(BaseModel):
    weaknesses: list[dict[str, Any]] = Field(default_factory=list)
    root_cause: str = ""
    confidence: float = 0.0


class PlanIntent(BaseModel):
    intent: Literal["review", "new_knowledge", "practice", "reward", "hint"]
    skill_tags: list[str] = Field(default_factory=list)
    difficulty: Literal["easier", "same", "harder"] = "same"
    rationale: str = ""


class LearningReport(BaseModel):
    learner_id: str
    period_start: datetime
    period_end: datetime
    summary: str
    weaknesses: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    events_count: int = 0
    mastery_updates: list[dict[str, Any]] = Field(default_factory=list)


QuestionSource = Literal["database", "generated"]
QuestionOrigin = Literal["normal", "mistake_review", "carry_over"]
PaperStatus = Literal["active", "completed", "queued", "abandoned"]


class QuestionItem(BaseModel):
    id: str
    source: QuestionSource = "database"
    origin: QuestionOrigin = "normal"
    mistake_from_paper_id: str | None = None
    skill_tags: list[str] = Field(default_factory=list)
    knowledge_point: str = ""
    level: int = Field(default=1, ge=1, le=5)
    type: str = "multiple_choice"
    prompt: str
    correct_answer: str
    choices: list[str] = Field(default_factory=list)
    explanation: str = ""
    validation_status: Literal["pending", "passed", "failed"] = "passed"
    generation_meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_bank_dict(cls, q: dict[str, Any]) -> "QuestionItem":
        level = q.get("level") or q.get("difficulty") or 1
        if isinstance(level, str):
            level = {"简单": 1, "easy": 1, "困难": 5, "hard": 5}.get(level.lower(), 2)
        level = max(1, min(5, int(level)))
        return cls(
            id=str(q.get("id", uuid4())),
            source="database" if q.get("source") != "generated" else "generated",
            skill_tags=list(q.get("skill_tags") or []),
            knowledge_point=str(q.get("knowledge_point") or q.get("skill_tags", [""])[0]),
            level=level,
            type=str(q.get("type", "multiple_choice")),
            prompt=str(q.get("prompt", "")),
            correct_answer=str(q.get("correct_answer", "")),
            choices=list(q.get("choices") or []),
            explanation=str(q.get("explanation", "")),
            validation_status="passed",
        )


class RelatedKnowledgeEntry(BaseModel):
    knowledge_point: str
    skill_tags: list[str] = Field(default_factory=list)
    quota: int = 1


class PaperPlan(BaseModel):
    knowledge_point: str
    skill_tags: list[str] = Field(default_factory=list)
    target_level_min: int = 1
    target_level_max: int = 3
    strategy: str = "practice"
    rationale: str = ""
    next_focus: str = ""
    related_knowledge_points: list[RelatedKnowledgeEntry] = Field(default_factory=list)
    knowledge_cluster_id: str | None = None


class ExamPaper(BaseModel):
    paper_id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    session_id: str
    knowledge_point: str = ""
    questions: list[QuestionItem] = Field(default_factory=list)
    strategy: str = ""
    rationale: str = ""
    status: PaperStatus = "active"
    current_index: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    @property
    def total_questions(self) -> int:
        return len(self.questions)


class LearnerProfile(BaseModel):
    learner_id: str
    current_level: int = 2
    weak_points: list[str] = Field(default_factory=list)
    avg_response_ms: float = 0.0
    accuracy_by_kp: dict[str, float] = Field(default_factory=dict)
    difficulty_preference: int = 2
    papers_completed: int = 0
    last_paper_summary: str = ""
    total_answers: int = 0
    total_correct: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def recent_accuracy(self) -> float:
        if self.total_answers == 0:
            return 0.0
        return self.total_correct / self.total_answers


class AnswerRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    learner_id: str
    question_index: int
    question_id: str
    user_answer: str
    is_correct: bool
    time_spent_ms: int = 0
    error_pattern: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SubmitAnswerRequest(BaseModel):
    user_answer: str
    time_spent_ms: int = 0
    question_index: int | None = None


class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: str = ""
    feedback: str = ""
    effect_hint: Literal["boost", "normal", "penalty"] = "normal"
    question_index: int
    paper_finished: bool = False
    next_paper_ready: bool = False
