from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel, BaseModel


class OwnClarification(BaseModel):
    __tablename__ = "own_knowledge_clarifications"
    __table_args__ = (
        UniqueConstraint("connection_id", "user_id", "idempotency_key", name="uq_own_clarification_key"),
        CheckConstraint("status IN ('pending', 'confirmed', 'dismissed')", name="status_valid"),
    )

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_session_id: Mapped[str | None] = mapped_column(String(255))
    source_question_id: Mapped[str | None] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    missing: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    answer_fingerprint: Mapped[str | None] = mapped_column(String(64))
    confirmed_entry_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OwnProposal(BaseModel):
    __tablename__ = "own_knowledge_proposals"
    __table_args__ = (
        UniqueConstraint("clarification_id", "kind", "normalized_name", name="uq_own_proposal_name"),
        CheckConstraint("kind IN ('glossary', 'metric', 'expert_rule')", name="kind_valid"),
    )

    clarification_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("own_knowledge_clarifications.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    concept: Mapped[str | None] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    table_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="SET NULL"), index=True
    )


class OwnKnowledgeEntry(AuditedModel):
    __tablename__ = "own_knowledge_entries"
    __table_args__ = (
        UniqueConstraint("connection_id", "user_id", "kind", "normalized_name", name="uq_own_entry_name"),
        CheckConstraint("kind IN ('glossary', 'metric', 'expert_rule')", name="kind_valid"),
        CheckConstraint("review_status IN ('pending', 'kept_own', 'promoted')", name="review_status_valid"),
    )

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    concept: Mapped[str | None] = mapped_column(String(255))
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    table_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="SET NULL"), index=True
    )
    source_clarification_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("own_knowledge_clarifications.id", ondelete="SET NULL"), index=True
    )
    source_proposal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("own_knowledge_proposals.id", ondelete="SET NULL"), index=True
    )
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_kind: Mapped[str | None] = mapped_column(String(20))
    promoted_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
