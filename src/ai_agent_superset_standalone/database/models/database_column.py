"""Columns discovered in source tables and views."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DatabaseColumn(Base):
    __tablename__ = "database_columns"
    __table_args__ = (UniqueConstraint("table_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    default_value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
