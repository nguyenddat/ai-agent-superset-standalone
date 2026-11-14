from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class TableDictionary(AuditedModel):
    __tablename__ = "table_dictionaries"

    table_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    layer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_layers.id", ondelete="SET NULL"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    grain_description: Mapped[str | None] = mapped_column(Text)
    table_kind: Mapped[str | None] = mapped_column(String(32))
    layout: Mapped[str] = mapped_column(String(32), nullable=False, default="wide", server_default="wide")
    indicator_catalog_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="SET NULL"), index=True
    )
    contains_pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
