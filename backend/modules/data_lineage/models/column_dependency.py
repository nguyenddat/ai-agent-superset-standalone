from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class LineageColumnDependency(BaseModel):
    __tablename__ = "lineage_column_dependencies"
    __table_args__ = (
        CheckConstraint("role IN ('value', 'group', 'join', 'filter')", name="role_valid"),
        CheckConstraint("role <> 'value' OR target_column_id IS NOT NULL", name="value_has_target"),
    )

    transformation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lineage_transformations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_column_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_column_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
