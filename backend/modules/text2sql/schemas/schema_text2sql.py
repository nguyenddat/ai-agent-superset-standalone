from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..utils.topics import validate_topics

JobStatus = Literal["pending", "running", "succeeded", "failed", "superseded"]
ChatStatus = Literal["answered", "needs_clarification"]


def stripped_question(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Câu hỏi không được để trống.")
    return value


class TopicSelection(BaseModel):
    connection_id: UUID
    topics: list[str] | None = None

    @field_validator("topics")
    @classmethod
    def known_topics(cls, value: list[str] | None) -> list[str] | None:
        return list(validate_topics(value)) if value is not None else None


class SyncIn(TopicSelection):
    pass


class SyncOut(BaseModel):
    connection_id: UUID
    topics: list[str]
    total: int
    indexed: int
    unchanged: int
    deleted: int


class JobEnqueueIn(TopicSelection):
    pass


class JobEnqueueOut(BaseModel):
    connection_id: UUID
    topics: list[str]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    topic: str
    source: str
    status: JobStatus
    attempts: int
    run_after: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    result: dict | None
    created_at: datetime


class RetrieveIn(BaseModel):
    connection_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        return stripped_question(value)


class CandidateOut(BaseModel):
    metric_id: UUID
    table_id: UUID
    name: str
    label: str | None
    description: str | None
    score: float
    matched_topics: list[str]


class RetrieveOut(BaseModel):
    candidates: list[CandidateOut]


class ChatHistoryTurnIn(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    answer: str | None = None


class ChatIn(BaseModel):
    connection_id: UUID
    user_id: str | None = Field(default=None, max_length=200)
    conversation_id: UUID | None = None
    resume_id: UUID | None = None
    question: str = Field(min_length=1, max_length=2000)
    chat_history: list[ChatHistoryTurnIn] = Field(default_factory=list, max_length=50)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        return stripped_question(value)

    @model_validator(mode="after")
    def conversation_needs_user(self) -> ChatIn:
        if self.conversation_id is not None and not (self.user_id or "").strip():
            raise ValueError("Cần user_id khi gửi conversation_id.")
        return self


class KnowledgeHitOut(BaseModel):
    entity_id: UUID
    table_id: UUID | None
    name: str
    display_name: str
    text: str
    score: float


class QuestionKnowledgeOut(BaseModel):
    metrics: list[CandidateOut]
    tables: list[KnowledgeHitOut]
    columns: list[KnowledgeHitOut]
    glossary: list[KnowledgeHitOut]
    expert_rules: list[KnowledgeHitOut]
    own_knowledge: list[KnowledgeHitOut]


class PreprocessedQuestionOut(BaseModel):
    position: int
    question: str
    depends_on: list[int]
    question_type: str
    business_concepts: list[str]
    knowledge: QuestionKnowledgeOut


class PreprocessOut(BaseModel):
    rewritten_question: str
    is_split: bool
    execution_mode: Literal["parallel", "sequential"]
    questions: list[PreprocessedQuestionOut]
    stages: list[list[int]]


FieldKind = Literal["number", "date", "datetime", "text", "boolean", "other"]
TimeUnit = Literal["day", "week", "month", "quarter", "year"]
ExplanationKind = Literal[
    "metric", "source", "period", "filter", "group", "order", "rule", "value_match", "data_range", "scope",
    "assumption", "method", "truncated", "warning",
]
ChartDisplay = Literal["chart", "chart_if_last", "none"]


class FieldOut(BaseModel):
    name: str
    label: str
    type: FieldKind
    unit: str | None = None
    decimals: int | None = None
    percent: bool = False
    additive: bool | None = None
    role: Literal["measure", "dimension"] = "dimension"
    format_hint: Literal["plain"] | None = None
    time_unit: TimeUnit | None = None
    pii: bool = False


class ExplanationOut(BaseModel):
    kind: ExplanationKind
    text: str
    name: str | None = None
    status: Literal["applied", "yielded", "skipped"] | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    values: list[str] | None = None


class AgentStepOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
    result_id: str | None = None
    fields: list[FieldOut] = Field(default_factory=list)
    explanations: list[ExplanationOut] = Field(default_factory=list)
    chart: dict[str, Any] | None = None
    chart_source: Literal["auto", "agent"] | None = None
    chart_types: list[str] = Field(default_factory=list)
    display: ChartDisplay | None = None


class ChartValidateIn(BaseModel):
    chart: dict[str, Any]
    fields: list[FieldOut] = Field(max_length=100)
    rows: list[list[Any]] = Field(default_factory=list, max_length=1000)
    rows_complete: bool = True


class ChartValidateOut(BaseModel):
    chart: dict[str, Any]
    warnings: list[str]
    chart_types: list[str]


class QuestionAnswerOut(BaseModel):
    position: int
    question: str
    answer: str
    exhausted: bool = False
    steps: list[AgentStepOut] = Field(default_factory=list)


class ChatOut(BaseModel):
    answer: str
    status: ChatStatus = "answered"
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    resume_id: UUID | None = None
    resume_expires_at: datetime | None = None
    conversation_id: UUID | None = None
    turn_id: UUID | None = None
    # Câu trả lời cho bước viết lại câu hỏi ở lượt sau: còn nhãn thay thế (bỏ số thứ tự) thay cho giá trị thật;
    # None khi giống answer.
    history_answer: str | None = None
    preprocess: PreprocessOut
    answers: list[QuestionAnswerOut]
