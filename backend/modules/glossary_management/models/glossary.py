from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel, BaseModel


class GlossaryTerm(AuditedModel):
    __tablename__ = "glossary_terms"
    __table_args__ = (UniqueConstraint("connection_id", "normalized_name", name="uq_glossary_term_name"),)

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(255))


class GlossaryRevision(BaseModel):
    __tablename__ = "glossary_revisions"
    __table_args__ = (
        UniqueConstraint("term_id", "number", name="uq_glossary_revision_number"),
        CheckConstraint("status IN ('draft', 'approved', 'revoked')", name="status_valid"),
    )

    term_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    synonyms: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")


class GlossaryLink(BaseModel):
    __tablename__ = "glossary_links"
    __table_args__ = (
        CheckConstraint("kind IN ('table', 'column', 'metric')", name="kind_valid"),
        CheckConstraint(
            "(kind = 'table' AND table_id IS NOT NULL AND column_id IS NULL AND metric_id IS NULL) OR "
            "(kind = 'column' AND table_id IS NULL AND column_id IS NOT NULL AND metric_id IS NULL) OR "
            "(kind = 'metric' AND table_id IS NULL AND column_id IS NULL AND metric_id IS NOT NULL)",
            name="target_valid",
        ),
        UniqueConstraint("revision_id", "table_id", name="uq_glossary_link_table"),
        UniqueConstraint("revision_id", "column_id", name="uq_glossary_link_column"),
        UniqueConstraint("revision_id", "metric_id", name="uq_glossary_link_metric"),
    )

    revision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("glossary_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    table_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), index=True
    )
    column_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="CASCADE"), index=True
    )
    metric_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("metrics.id", ondelete="CASCADE"), index=True
    )
