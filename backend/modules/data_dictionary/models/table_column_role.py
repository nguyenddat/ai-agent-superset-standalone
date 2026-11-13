from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class TableColumnRole(AuditedModel):
    __tablename__ = "table_column_roles"
    __table_args__ = (
        UniqueConstraint("table_dictionary_id", "role", "qualifier", postgresql_nulls_not_distinct=True),
    )

    table_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    qualifier: Mapped[str | None] = mapped_column(String(32))
    column_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="CASCADE"), nullable=False, index=True
    )
