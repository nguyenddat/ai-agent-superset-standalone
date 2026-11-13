from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class IndicatorAggregation(AuditedModel):
    __tablename__ = "indicator_aggregations"
    __table_args__ = (UniqueConstraint("table_dictionary_id", "source_code"),)

    table_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_code: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(16), nullable=False)
