import sqlite3
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import TECHNICAL_SCHEMA, BaseModel

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
SUPERSEDED = "superseded"
FINISHED_STATUSES = (SUCCEEDED, FAILED, SUPERSEDED)

EVENT = "event"
SCHEDULE = "schedule"
MANUAL = "manual"


@event.listens_for(Engine, "connect")
def attach_technical_schema_to_sqlite(dbapi_connection: object, connection_record: object) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        attached = {row[1] for row in dbapi_connection.execute("PRAGMA database_list")}
        if TECHNICAL_SCHEMA not in attached:
            dbapi_connection.execute(f"ATTACH DATABASE ':memory:' AS {TECHNICAL_SCHEMA}")


class IngestionJob(BaseModel):
    __tablename__ = "text2sql_ingestion_jobs"
    __table_args__ = (
        Index(
            "uq_text2sql_ingestion_jobs_pending", "connection_id", "topic", unique=True,
            postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_text2sql_ingestion_jobs_claim", "status", "run_after"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'superseded')", name="status_valid"
        ),
        CheckConstraint("source IN ('event', 'schedule', 'manual')", name="source_valid"),
        {"schema": TECHNICAL_SCHEMA},
    )

    connection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING, server_default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
