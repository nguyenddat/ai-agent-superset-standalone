from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel, BaseModel


class ExpertRule(AuditedModel):
    __tablename__ = "expert_rules"
    __table_args__ = (UniqueConstraint("connection_id", "normalized_name", name="uq_expert_rule_name"),)

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(255))


class ExpertRuleRevision(BaseModel):
    __tablename__ = "expert_rule_revisions"
    __table_args__ = (
        UniqueConstraint("rule_id", "number", name="uq_expert_rule_revision_number"),
        CheckConstraint("status IN ('draft', 'approved', 'revoked')", name="status_valid"),
    )

    rule_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    exceptions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    examples: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")


class ExpertRuleGlossaryLink(BaseModel):
    __tablename__ = "expert_rule_glossary_links"
    __table_args__ = (UniqueConstraint("revision_id", "term_id", name="uq_expert_rule_glossary_link"),)

    revision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expert_rule_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    glossary_revision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("glossary_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ExpertRuleMetricLink(BaseModel):
    __tablename__ = "expert_rule_metric_links"
    __table_args__ = (UniqueConstraint("revision_id", "metric_id", name="uq_expert_rule_metric_link"),)

    revision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expert_rule_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
