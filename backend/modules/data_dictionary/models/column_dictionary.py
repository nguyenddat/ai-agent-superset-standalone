from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class ColumnDictionary(AuditedModel):
    __tablename__ = "column_dictionaries"

    column_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    business_term: Mapped[str | None] = mapped_column(Text)
    semantic_role: Mapped[str | None] = mapped_column(String(16))
    temporal_kind: Mapped[str | None] = mapped_column(String(16))
    unit: Mapped[str | None] = mapped_column(String(128))
    format: Mapped[str | None] = mapped_column(String(128))
    is_primary_key: Mapped[bool | None] = mapped_column(Boolean)
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    referenced_column_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_columns.id", ondelete="SET NULL"), index=True
    )
    contains_pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
