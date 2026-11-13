from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class DatabaseTable(BaseModel):
    __tablename__ = "database_tables"
    __table_args__ = (UniqueConstraint("schema_id", "name"),)

    schema_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_schemas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
