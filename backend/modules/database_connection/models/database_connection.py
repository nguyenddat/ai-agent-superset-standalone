from sqlalchemy import JSON, Boolean, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import BaseModel


class DatabaseConnection(BaseModel):
    __tablename__ = "database_connections"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    dialect: Mapped[str] = mapped_column(String(64), nullable=False)
    driver: Mapped[str | None] = mapped_column(String(64))
    uri_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    schema_includes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    schema_excludes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    table_includes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    table_excludes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
