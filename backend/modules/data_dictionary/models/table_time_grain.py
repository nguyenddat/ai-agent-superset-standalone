from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class TableTimeGrain(AuditedModel):
    __tablename__ = "table_time_grains"
    __table_args__ = (
        UniqueConstraint("table_dictionary_id", "row_kind_value", postgresql_nulls_not_distinct=True),
    )

    table_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_kind_value: Mapped[str | None] = mapped_column(String(255))
    label: Mapped[str | None] = mapped_column(String(255))
    time_grain: Mapped[str] = mapped_column(String(16), nullable=False)
