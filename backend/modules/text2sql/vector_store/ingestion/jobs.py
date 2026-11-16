from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID, uuid7

from sqlalchemy import Connection, delete, select, text
from sqlalchemy.orm import Session, aliased

from backend.common.base_model import utc_now
from backend.modules.database_connection.models import DatabaseConnection

from ...models.ingestion_job import (
    EVENT,
    FAILED,
    FINISHED_STATUSES,
    PENDING,
    RUNNING,
    SCHEDULE,
    SUCCEEDED,
    SUPERSEDED,
    IngestionJob,
)

MAX_ERROR_LENGTH = 1000
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 900


def _insert(connection: Connection):
    if connection.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif connection.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError(f"Dialect {connection.dialect.name} không được hỗ trợ cho hàng đợi ingestion.")
    return insert(IngestionJob.__table__)


def enqueue_jobs(
    connection: Connection, connection_ids: Sequence[UUID], topics: Sequence[str], source: str,
    run_after: datetime | None = None,
) -> None:
    now = utc_now()
    rows = [
        {
            "id": uuid7(), "connection_id": connection_id, "topic": topic, "source": source, "status": PENDING,
            "attempts": 0, "run_after": run_after or now, "created_at": now, "updated_at": now,
        }
        for connection_id in connection_ids for topic in topics
    ]
    if not rows:
        return
    statement = _insert(connection).values(rows).on_conflict_do_nothing(
        index_elements=["connection_id", "topic"], index_where=text("status = 'pending'")
    )
    connection.execute(statement)


def retry_delay_seconds(attempts: int) -> int:
    return min(RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0), RETRY_MAX_SECONDS)


class IngestionJobQueue:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, connection_ids: Sequence[UUID], topics: Sequence[str], source: str = EVENT) -> None:
        enqueue_jobs(self.session.connection(), connection_ids, topics, source)

    def enqueue_scheduled(self, topic: str, interval_seconds: int, now: datetime | None = None) -> int:
        now = now or utc_now()
        cutoff = now - timedelta(seconds=interval_seconds * 0.9)
        recent = select(IngestionJob.id).where(
            IngestionJob.connection_id == DatabaseConnection.id, IngestionJob.topic == topic,
            IngestionJob.source == SCHEDULE, IngestionJob.created_at >= cutoff,
        ).exists()
        connection_ids = list(self.session.scalars(
            select(DatabaseConnection.id).where(DatabaseConnection.is_active.is_(True), ~recent)
        ))
        self.enqueue(connection_ids, [topic], SCHEDULE)
        return len(connection_ids)

    def get(self, job_id: UUID) -> IngestionJob | None:
        return self.session.get(IngestionJob, job_id)

    def claim_next(self, now: datetime | None = None) -> IngestionJob | None:
        now = now or utc_now()
        running = aliased(IngestionJob)
        busy = select(running.id).where(
            running.status == RUNNING, running.connection_id == IngestionJob.connection_id,
            running.topic == IngestionJob.topic,
        ).exists()
        job = self.session.scalars(
            select(IngestionJob)
            .where(IngestionJob.status == PENDING, IngestionJob.run_after <= now, ~busy)
            .order_by(IngestionJob.run_after, IngestionJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.status = RUNNING
        job.started_at = now
        job.attempts += 1
        self.session.flush()
        return job

    def complete(self, job: IngestionJob, result: dict[str, object], now: datetime | None = None) -> None:
        job.status = SUCCEEDED
        job.finished_at = now or utc_now()
        job.last_error = None
        job.result = result
        self.session.flush()

    def fail(self, job: IngestionJob, error: str, max_attempts: int, now: datetime | None = None) -> None:
        now = now or utc_now()
        job.last_error = error[:MAX_ERROR_LENGTH]
        if job.attempts >= max_attempts:
            job.status = FAILED
            job.finished_at = now
        elif self._has_pending(job):
            job.status = SUPERSEDED
            job.finished_at = now
        else:
            job.status = PENDING
            job.started_at = None
            job.run_after = now + timedelta(seconds=retry_delay_seconds(job.attempts))
        self.session.flush()

    def recover_stale(self, timeout_seconds: int, max_attempts: int, now: datetime | None = None) -> int:
        now = now or utc_now()
        stale = list(self.session.scalars(
            select(IngestionJob).where(
                IngestionJob.status == RUNNING, IngestionJob.started_at < now - timedelta(seconds=timeout_seconds)
            ).with_for_update(skip_locked=True)
        ))
        for job in stale:
            self.fail(job, "Job vượt quá thời gian chạy cho phép.", max_attempts, now)
        return len(stale)

    def purge_finished(self, older_than: datetime) -> int:
        result = self.session.execute(
            delete(IngestionJob).where(
                IngestionJob.status.in_(FINISHED_STATUSES), IngestionJob.finished_at < older_than
            )
        )
        return result.rowcount or 0

    def list_recent(
        self, connection_id: UUID | None = None, status: str | None = None, limit: int = 50
    ) -> list[IngestionJob]:
        statement = select(IngestionJob)
        if connection_id is not None:
            statement = statement.where(IngestionJob.connection_id == connection_id)
        if status is not None:
            statement = statement.where(IngestionJob.status == status)
        return list(self.session.scalars(
            statement.order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc()).limit(limit)
        ))

    def _has_pending(self, job: IngestionJob) -> bool:
        return self.session.scalar(
            select(IngestionJob.id).where(
                IngestionJob.connection_id == job.connection_id, IngestionJob.topic == job.topic,
                IngestionJob.status == PENDING, IngestionJob.id != job.id,
            ).limit(1)
        ) is not None
