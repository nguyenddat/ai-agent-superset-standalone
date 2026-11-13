from sqlalchemy import Boolean, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class DatabaseConnection(BaseModel):
    __tablename__ = "database_connections"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    dialect: Mapped[str] = mapped_column(String(64), nullable=False)
    driver: Mapped[str | None] = mapped_column(String(64))
    uri_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
