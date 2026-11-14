from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class LineageTransformationInput(BaseModel):
    __tablename__ = "lineage_transformation_inputs"
    __table_args__ = (UniqueConstraint("transformation_id", "source_table_id"),)

    transformation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lineage_transformations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_table_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
