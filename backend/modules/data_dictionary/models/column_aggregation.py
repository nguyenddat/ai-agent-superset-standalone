from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class ColumnAggregation(AuditedModel):
    __tablename__ = "column_aggregations"
    __table_args__ = (UniqueConstraint("column_dictionary_id", "aggregation"),)

    column_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("column_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    aggregation: Mapped[str] = mapped_column(String(16), nullable=False)
