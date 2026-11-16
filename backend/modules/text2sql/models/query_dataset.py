from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import TECHNICAL_SCHEMA, BaseModel

MAX_SELECTED_COLUMNS = 200


class QueryDataset(BaseModel):
    __tablename__ = "text2sql_query_datasets"
    __table_args__ = (
        UniqueConstraint("connection_id", "signature", "root_table_id"),
        {"schema": TECHNICAL_SCHEMA},
    )

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    root_table_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False
    )
    table_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    from_sql: Mapped[str] = mapped_column(Text, nullable=False)
    selected_column_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
