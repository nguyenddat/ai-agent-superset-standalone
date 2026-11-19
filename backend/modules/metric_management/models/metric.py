from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel, Base


class Metric(AuditedModel):
    __tablename__ = "metrics"
    __table_args__ = (
        CheckConstraint("origin IN ('manual', 'superset')", name="origin_valid"),
        UniqueConstraint(
            "source_url", "source_metric_id", name="uq_metrics_source_metric"
        ),
    )

    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="manual"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(String(128))
    currency: Mapped[str | None] = mapped_column(String(16))
    metric_type: Mapped[str | None] = mapped_column(String(64))
    warning_text: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    table_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("database_tables.id", ondelete="SET NULL"),
        index=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_metric_id: Mapped[int | None] = mapped_column(Integer)
    source_dataset_id: Mapped[int | None] = mapped_column(Integer)
    source_database_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("superset_databases.id", ondelete="SET NULL"),
        index=True,
    )
    source_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("superset_users.id", ondelete="SET NULL"),
        index=True,
    )
    source_dataset_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("superset_users.id", ondelete="SET NULL"),
        index=True,
    )
    source_schema: Mapped[str | None] = mapped_column(String(255))
    source_table: Mapped[str | None] = mapped_column(String(255))
    source_sql: Mapped[str | None] = mapped_column(Text)


metric_domains = Table(
    "metric_domains",
    Base.metadata,
    Column(
        "metric_id",
        Uuid(as_uuid=True),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "domain_id",
        Uuid(as_uuid=True),
        ForeignKey("business_domains.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)
