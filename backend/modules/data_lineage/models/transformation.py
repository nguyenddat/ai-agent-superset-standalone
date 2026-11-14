from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class LineageTransformation(AuditedModel):
    __tablename__ = "lineage_transformations"
    __table_args__ = (UniqueConstraint("target_table_id", "name"),)

    target_table_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sql_text: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="manual", server_default="manual")
