from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class DataLayer(AuditedModel):
    __tablename__ = "data_layers"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
