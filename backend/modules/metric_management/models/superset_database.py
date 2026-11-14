from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class SupersetDatabase(BaseModel):
    __tablename__ = "superset_databases"
    __table_args__ = (UniqueConstraint("source_url", "source_id"),)

    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    backend: Mapped[str | None] = mapped_column(String(64))
    connection_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="SET NULL"),
        index=True,
    )
