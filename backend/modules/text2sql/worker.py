import logging
import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.common.base_exceptions import AppError
from backend.common.base_model import utc_now
from backend.core.database import get_session_factory
from backend.core.setting import config
from backend.modules.model_registry import register_all_models

from .repositories.ingestion_job_repository import IngestionJobRepository
from .repositories.qdrant_repository import QdrantRepository
from .services.ingestion_service import IngestionService
from .utils.topics import DEFAULT_INTERVAL_SECONDS, TOPICS

register_all_models()

logger = logging.getLogger("text2sql.worker")

PURGE_INTERVAL_SECONDS = 3600


def parse_topic_intervals(raw: str) -> dict[str, int]:
    intervals = dict(DEFAULT_INTERVAL_SECONDS)
    for item in filter(None, (part.strip() for part in raw.split(","))):
        topic, separator, seconds = item.partition("=")
        topic = topic.strip()
        if not separator or topic not in TOPICS or not seconds.strip().isdigit() or int(seconds) < 30:
            raise ValueError(f"TEXT2SQL_TOPIC_INTERVALS không hợp lệ ở mục '{item}'.")
        intervals[topic] = int(seconds)
    return intervals


def _error_text(error: Exception) -> str:
    if isinstance(error, AppError):
        return f"{error.code}: {error.message}"
    return type(error).__name__


class IngestionWorker:
    def __init__(
        self, session_factory: sessionmaker[Session], intervals: dict[str, int] | None = None,
        concurrency: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.intervals = intervals or parse_topic_intervals(config.text2sql_topic_intervals)
        self.concurrency = concurrency or config.text2sql_worker_concurrency
        self.stop_event = threading.Event()
        self._next_schedule = {topic: 0.0 for topic in TOPICS}
        self._next_purge = 0.0
        self._running: set[Future] = set()

    def run(self) -> None:
        logger.info("Worker ingestion khởi động, tối đa %d job song song.", self.concurrency)
        with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="ingestion") as executor:
            while not self.stop_event.is_set():
                self._running = {future for future in self._running if not future.done()}
                try:
                    self.tick(executor)
                except Exception:
                    logger.exception("Vòng xử lý hàng đợi ingestion gặp lỗi.")
                self.stop_event.wait(config.text2sql_worker_poll_seconds)
            logger.info("Đang dừng, chờ %d job đang chạy.", len(self._running))

    def tick(self, executor: ThreadPoolExecutor) -> None:
        self.schedule_due_topics()
        self.maintain()
        while len(self._running) < self.concurrency:
            claimed = self.claim()
            if claimed is None:
                break
            self._running.add(executor.submit(self.execute, *claimed))

    def schedule_due_topics(self) -> None:
        now = time.monotonic()
        due = [topic for topic in TOPICS if now >= self._next_schedule[topic]]
        if not due:
            return
        with self.session_factory() as session:
            queue = IngestionJobRepository(session)
            for topic in due:
                queue.enqueue_scheduled(topic, self.intervals[topic])
                self._next_schedule[topic] = now + self.intervals[topic] / 2
            session.commit()

    def maintain(self) -> None:
        with self.session_factory() as session:
            queue = IngestionJobRepository(session)
            recovered = queue.recover_stale(config.text2sql_job_timeout_seconds, config.text2sql_job_max_attempts)
            if recovered:
                logger.warning("Đã đưa %d job quá hạn về hàng đợi.", recovered)
            now = time.monotonic()
            if now >= self._next_purge:
                queue.purge_finished(utc_now() - timedelta(days=config.text2sql_job_retention_days))
                self._next_purge = now + PURGE_INTERVAL_SECONDS
            session.commit()

    def claim(self) -> tuple[UUID, UUID, str] | None:
        with self.session_factory() as session:
            job = IngestionJobRepository(session).claim_next()
            if job is None:
                return None
            claimed = (job.id, job.connection_id, job.topic)
            session.commit()
            return claimed

    def execute(self, job_id: UUID, connection_id: UUID, topic: str) -> None:
        index = QdrantRepository()
        embedding = OpenRouterEmbedding()
        started = time.monotonic()
        try:
            with self.session_factory() as session:
                try:
                    result = IngestionService(session, index, embedding).sync(connection_id, [topic])
                finally:
                    session.rollback()
            outcome: dict[str, object] | None = {
                "total": result.total, "indexed": result.indexed, "unchanged": result.unchanged,
                "deleted": result.deleted, "seconds": round(time.monotonic() - started, 3),
            }
            error: str | None = None
            logger.info("Ingest %s/%s: %s", connection_id, topic, outcome)
        except Exception as exception:
            outcome, error = None, _error_text(exception)
            logger.warning("Ingest %s/%s lỗi: %s", connection_id, topic, error)
        finally:
            index.close()
            embedding.close()
        self.finish(job_id, outcome, error)

    def finish(self, job_id: UUID, outcome: dict[str, object] | None, error: str | None) -> None:
        with self.session_factory() as session:
            queue = IngestionJobRepository(session)
            job = queue.get(job_id)
            if job is None:
                return
            if outcome is not None:
                queue.complete(job, outcome)
            else:
                queue.fail(job, error or "Lỗi không xác định.", config.text2sql_job_max_attempts)
            session.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker = IngestionWorker(get_session_factory())
    for signal_name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, signal_name), lambda *_: worker.stop_event.set())
    worker.run()


if __name__ == "__main__":
    main()
