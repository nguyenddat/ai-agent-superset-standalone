from uuid import UUID

from sqlalchemy import ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class BusinessCanvas(AuditedModel):
    __tablename__ = "business_canvases"

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    layout: Mapped[str] = mapped_column(Text, nullable=False)
