from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

KnowledgeKind = Literal["glossary", "metric", "expert_rule"]


class ProposalIn(BaseModel):
    kind: KnowledgeKind
    name: str = Field(min_length=1, max_length=255)
    concept: str | None = Field(default=None, max_length=255)
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=1, max_length=10)
    table_id: UUID | None = None


class ClarificationPush(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    connection_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_session_id: str | None = Field(default=None, max_length=255)
    source_question_id: str | None = Field(default=None, max_length=255)
    question: str = Field(min_length=1, max_length=10000)
    missing: list[KnowledgeKind] = Field(min_length=1, max_length=3)
    proposals: list[ProposalIn] = Field(min_length=1, max_length=10)


class ProposalOut(BaseModel):
    id: UUID
    kind: KnowledgeKind
    name: str
    concept: str | None
    prompt: str
    options: list[str]
    table_id: UUID | None


class ClarificationOut(BaseModel):
    id: UUID
    user_id: str
    connection_id: UUID
    idempotency_key: str
    source_session_id: str | None
    source_question_id: str | None
    question: str
    missing: list[KnowledgeKind]
    status: Literal["pending", "confirmed", "dismissed"]
    proposals: list[ProposalOut]
    created_at: datetime
    answered_at: datetime | None


class AnswerChoice(BaseModel):
    proposal_id: UUID
    option_index: int | None = Field(default=None, ge=0, le=9)
    definition: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def exactly_one_answer(self) -> "AnswerChoice":
        if (self.option_index is None) == (self.definition is None):
            raise ValueError("Chọn một phương án hoặc nhập định nghĩa riêng.")
        return self


class ClarificationAnswer(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    state: Literal["confirmed", "dismissed"]
    answers: list[AnswerChoice] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_answers(self) -> "ClarificationAnswer":
        if (self.state == "confirmed") != bool(self.answers):
            raise ValueError("Xác nhận cần câu trả lời; bỏ qua không nhận câu trả lời.")
        return self


class EntryOut(BaseModel):
    id: UUID
    connection_id: UUID
    user_id: str
    kind: KnowledgeKind
    name: str
    concept: str | None
    definition: str
    table_id: UUID | None
    source_clarification_id: UUID | None
    source_proposal_id: UUID | None
    source_question: str | None
    review_status: Literal["pending", "kept_own", "promoted"]
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    promoted_kind: KnowledgeKind | None
    promoted_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    active_for_agent: bool


class EntryUpdate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    concept: str | None = Field(default=None, max_length=255)
    definition: str = Field(min_length=1, max_length=2000)


class AdminReview(BaseModel):
    expected_version: int = Field(ge=1)
    action: Literal["keep_own", "reopen"]
    reviewer_id: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=1000)


class AdminPromote(BaseModel):
    expected_version: int = Field(ge=1)
    target_kind: KnowledgeKind
    payload: dict[str, Any]
    reviewer_id: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=1000)


class AnswerOut(BaseModel):
    clarification: ClarificationOut
    entries: list[EntryOut]


class PromoteOut(BaseModel):
    entry: EntryOut
    target: dict[str, Any]
