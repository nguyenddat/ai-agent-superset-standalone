from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class SupersetUser(BaseModel):
    __tablename__ = "superset_users"
    __table_args__ = (UniqueConstraint("source_url", "source_id"),)

    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
