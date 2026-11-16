from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel

TURN_STATUSES = (
    "running", "answered", "needs_clarification", "cannot_answer", "join_ambiguous", "join_not_declared", "error",
)
TURN_FLOWS = ("metric", "dataset", "none")
FEEDBACK_RATINGS = ("up", "down")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class Conversation(BaseModel):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_owner_recent", "user_id", "connection_id", "last_message_at"),
    )

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ConversationTurn(BaseModel):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_turn_sequence"),
        CheckConstraint(_in("status", TURN_STATUSES), name="status_valid"),
        CheckConstraint(_in("flow", TURN_FLOWS), name="flow_valid"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    flow: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running", server_default="running")
    steps: Mapped[list[Any] | None] = mapped_column(JSON)
    results: Mapped[list[Any] | None] = mapped_column(JSON)
    rewrite: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assumptions: Mapped[list[Any] | None] = mapped_column(JSON)
    pii: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    dataset_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retry_of: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation_turns.id", ondelete="SET NULL"), index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    clarification_question: Mapped[str | None] = mapped_column(Text)
    clarification_options: Mapped[list[Any] | None] = mapped_column(JSON)
    continued_from: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation_turns.id", ondelete="SET NULL"), index=True
    )
    continuation: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ConversationTurnFeedback(BaseModel):
    __tablename__ = "conversation_turn_feedback"
    __table_args__ = (
        UniqueConstraint("turn_id", "user_id", name="uq_conversation_turn_feedback_user"),
        CheckConstraint(_in("rating", FEEDBACK_RATINGS), name="rating_valid"),
    )

    turn_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
