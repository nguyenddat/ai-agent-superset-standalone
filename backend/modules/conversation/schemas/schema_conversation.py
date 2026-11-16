from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

TurnStatus = Literal[
    "running", "answered", "needs_clarification", "cannot_answer", "join_ambiguous", "join_not_declared", "error",
]
TurnFlow = Literal["metric", "dataset", "none"]
Rating = Literal["up", "down"]


class ConversationCreate(BaseModel):
    connection_id: UUID
    user_id: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=2000)


class ConversationUpdate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=2000)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class FeedbackIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    rating: Rating
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    rating: Rating
    comment: str | None
    created_at: datetime
    updated_at: datetime


class TurnOut(BaseModel):
    id: UUID
    conversation_id: UUID
    sequence: int
    question: str
    rewritten_question: str | None
    answer: str | None
    flow: TurnFlow | None
    status: TurnStatus
    steps: list[Any] | None
    results: list[Any] | None
    rewrite: dict[str, Any] | None
    assumptions: list[Any] | None
    pii: dict[str, Any] | None
    dataset_id: UUID | None
    retry_of: UUID | None
    continued_from: UUID | None
    clarification_question: str | None
    clarification_options: list[str]
    error_code: str | None
    error: str | None
    duration_ms: int | None
    model: str | None
    feedback: FeedbackOut | None
    created_at: datetime
    updated_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    connection_id: UUID
    user_id: str
    title: str
    is_pinned: bool
    is_archived: bool
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    turn_count: int


class ConversationListItem(ConversationOut):
    last_question: str | None
    last_status: TurnStatus | None


class ConversationDetail(ConversationOut):
    turns: list[TurnOut]
