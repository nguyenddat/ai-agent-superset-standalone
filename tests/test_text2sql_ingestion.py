import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base, utc_now
from backend.modules.business_model import models as business_model_models  # noqa: F401
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric
from backend.modules.own_knowledge.models import OwnKnowledgeEntry
from backend.modules.text2sql.common.errors import Text2SqlIndexUnavailable
from backend.modules.text2sql.models.ingestion_job import (
    EVENT,
    FAILED,
    MANUAL,
    PENDING,
    RUNNING,
    SCHEDULE,
    SUCCEEDED,
    SUPERSEDED,
    IngestionJob,
)
from backend.modules.text2sql.vector_store.ingestion.documents.context import load_context
from backend.modules.text2sql.vector_store.ingestion.jobs import IngestionJobQueue, retry_delay_seconds
from backend.modules.text2sql.vector_store.ingestion.registry import TOPIC_BUILDERS, TOPICS, validate_topics
from backend.modules.text2sql.vector_store.ingestion.triggers import enqueue_for_changes
from backend.modules.text2sql.worker import IngestionWorker, parse_topic_intervals


def make_engine():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed_catalog(session: Session):
    connection = DatabaseConnection(name=f"Weather {uuid4()}", dialect="postgresql", uri_ciphertext="x")
    session.add(connection)
    session.flush()
    schema = DatabaseSchema(connection_id=connection.id, name="public")
    session.add(schema)
    session.flush()
    table = DatabaseTable(schema_id=schema.id, name="sales", table_type="TABLE")
    session.add(table)
    session.flush()
    column = DatabaseColumn(
        table_id=table.id, name="region", data_type="TEXT", ordinal_position=1, is_nullable=False
    )
    metric = Metric(table_id=table.id, name="revenue", label="Doanh thu", expression="SUM(amount)")
    session.add_all([column, metric, TableDictionary(table_id=table.id, display_name="Bán hàng")])
    session.flush()
    session.add(ColumnDictionary(column_id=column.id, display_name="Khu vực"))
    session.flush()
    return connection, table, column, metric


class TopicDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)

    def build(self, session: Session, connection_id):
        context = load_context(session, connection_id)
        return {topic: TOPIC_BUILDERS[topic](session, context) for topic in TOPICS}

    def test_registry_orders_topics_and_rejects_unknown(self) -> None:
        self.assertEqual(TOPICS, ("table", "column", "metric", "glossary", "expert_rule", "own_knowledge"))
        self.assertEqual(validate_topics(["metric", "table"]), ("table", "metric"))
        with self.assertRaises(ValueError):
            validate_topics(["metric", "unknown"])

    def test_only_approved_glossary_and_rules_are_indexed(self) -> None:
        with Session(self.engine) as session:
            connection, table, column, metric = seed_catalog(session)
            service = GlossaryService(session)
            approved = service.create_term({
                "connection_id": connection.id, "canonical_name": "Doanh số",
                "definition": "Tổng tiền bán được", "synonyms": ["sales"],
                "links": [{"kind": "table", "id": table.id}, {"kind": "metric", "id": metric.id}],
            })
            service.approve(approved["id"], 1)
            service.create_term({
                "connection_id": connection.id, "canonical_name": "Nháp",
                "definition": "Chưa duyệt", "synonyms": [], "links": [],
            })
            rules = ExpertRuleService(session)
            rule = rules.create_rule({
                "connection_id": connection.id, "table_id": table.id, "name": "Miền Bắc",
                "description": "Chỉ tính miền Bắc",
                "conditions": [{"column_id": column.id, "operator": "equals", "value_type": "string",
                                "value": "Bắc"}],
                "exceptions": [{"when": "báo cáo quý", "outcome": "bỏ lọc"}],
                "examples": [{"question": "doanh thu miền Bắc", "intent": "lọc theo vùng"}],
                "glossary_term_ids": [UUID(str(approved["id"]))], "metric_ids": [metric.id],
            })
            rules.approve(rule["id"], 1)
            session.add(OwnKnowledgeEntry(
                connection_id=connection.id, user_id="alice", kind="glossary", name="Ngày mưa",
                normalized_name="ngay mua", definition="Ngày có lượng mưa trên 1mm", table_id=table.id,
            ))
            session.flush()
            documents = self.build(session, connection.id)

        self.assertEqual({topic: len(items) for topic, items in documents.items()}, {
            "table": 1, "column": 1, "metric": 1, "glossary": 1, "expert_rule": 1, "own_knowledge": 1,
        })
        glossary = documents["glossary"][0]
        self.assertIn("Doanh số", glossary.text)
        self.assertIn("Tổng tiền bán được", glossary.text)
        self.assertIn("Bảng Bán hàng", glossary.text)
        self.assertIn("Metric Doanh thu", glossary.text)
        self.assertEqual(glossary.payload["metric_ids"], [str(metric.id)])
        self.assertIsNone(glossary.table_id)
        expert_rule = documents["expert_rule"][0]
        self.assertIn("Khu vực bằng Bắc", expert_rule.text)
        self.assertIn("khi báo cáo quý thì bỏ lọc", expert_rule.text)
        self.assertIn("Thuật ngữ: Doanh số", expert_rule.text)
        self.assertEqual(expert_rule.table_id, str(table.id))
        own = documents["own_knowledge"][0]
        self.assertEqual(own.payload["user_id"], "alice")
        self.assertIn("Ngày có lượng mưa trên 1mm", own.text)

    def test_own_knowledge_promoted_to_serving_term_is_not_indexed(self) -> None:
        with Session(self.engine) as session:
            connection, table, _, _ = seed_catalog(session)
            service = GlossaryService(session)
            term = service.create_term({
                "connection_id": connection.id, "canonical_name": "Ngày mưa",
                "definition": "Ngày có mưa", "synonyms": [], "links": [],
            })
            service.approve(term["id"], 1)
            session.add(OwnKnowledgeEntry(
                connection_id=connection.id, user_id="alice", kind="glossary", name="Ngày mưa",
                normalized_name="ngay mua", definition="Cách hiểu riêng", review_status="promoted",
                promoted_kind="glossary", promoted_id=term["id"],
            ))
            session.flush()
            documents = self.build(session, connection.id)
        self.assertEqual(documents["own_knowledge"], [])
        self.assertEqual(len(documents["glossary"]), 1)


class JobQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.connection, *_ = seed_catalog(self.session)
        self.queue = IngestionJobQueue(self.session)

    def jobs(self, **filters):
        return list(self.session.scalars(select(IngestionJob).filter_by(**filters)))

    def test_enqueue_coalesces_pending_jobs(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric", "glossary"], MANUAL)
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        self.assertEqual(sorted(job.topic for job in self.jobs()), ["glossary", "metric"])
        self.assertEqual({job.source for job in self.jobs(topic="metric")}, {MANUAL})

    def test_claim_runs_one_job_per_key_and_allows_requeue_while_running(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        first = self.queue.claim_next()
        self.assertEqual((first.status, first.attempts), (RUNNING, 1))
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        self.assertEqual(len(self.jobs(status=PENDING)), 1)
        self.assertIsNone(self.queue.claim_next())
        self.queue.complete(first, {"indexed": 1})
        second = self.queue.claim_next()
        self.assertIsNotNone(second)
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(first.status, SUCCEEDED)
        self.assertEqual(first.result, {"indexed": 1})

    def test_claim_respects_run_after(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        job = self.jobs()[0]
        job.run_after = utc_now() + timedelta(minutes=5)
        self.session.flush()
        self.assertIsNone(self.queue.claim_next())

    def test_fail_retries_with_backoff_then_gives_up(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        job = self.queue.claim_next()
        before = utc_now()
        self.queue.fail(job, "text2sql_index_unavailable: x", max_attempts=2)
        self.assertEqual(job.status, PENDING)
        self.assertGreaterEqual(job.run_after.replace(tzinfo=None), before.replace(tzinfo=None))
        job.run_after = utc_now() - timedelta(seconds=1)
        self.session.flush()
        job = self.queue.claim_next()
        self.assertEqual(job.attempts, 2)
        self.queue.fail(job, "again", max_attempts=2)
        self.assertEqual(job.status, FAILED)
        self.assertIsNotNone(job.finished_at)
        self.assertEqual(job.last_error, "again")

    def test_fail_marks_superseded_when_newer_pending_exists(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        job = self.queue.claim_next()
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        self.queue.fail(job, "boom", max_attempts=3)
        self.assertEqual(job.status, SUPERSEDED)
        self.assertEqual(len(self.jobs(status=PENDING)), 1)

    def test_retry_delay_grows_and_is_capped(self) -> None:
        self.assertEqual([retry_delay_seconds(attempt) for attempt in (1, 2, 3)], [30, 60, 120])
        self.assertEqual(retry_delay_seconds(50), 900)

    def test_scheduled_enqueue_skips_recently_scheduled_topics(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        inactive = DatabaseConnection(
            name=f"Off {uuid4()}", dialect="postgresql", uri_ciphertext="x", is_active=False
        )
        self.session.add(inactive)
        self.session.flush()
        self.session.execute(IngestionJob.__table__.delete())
        self.assertEqual(self.queue.enqueue_scheduled("metric", 300), 1)
        self.assertEqual({job.connection_id for job in self.jobs()}, {self.connection.id})
        for job in self.jobs():
            job.status = SUCCEEDED
        self.session.flush()
        self.assertEqual(self.queue.enqueue_scheduled("metric", 300), 0)
        self.assertEqual(self.queue.enqueue_scheduled("glossary", 300), 1)
        self.assertEqual({job.source for job in self.jobs()}, {SCHEDULE})

    def test_recover_stale_and_purge(self) -> None:
        self.session.execute(IngestionJob.__table__.delete())
        self.queue.enqueue([self.connection.id], ["metric"], EVENT)
        job = self.queue.claim_next()
        job.started_at = utc_now() - timedelta(hours=1)
        self.session.flush()
        self.assertEqual(self.queue.recover_stale(timeout_seconds=900, max_attempts=3), 1)
        self.assertEqual(job.status, PENDING)
        job.status = SUCCEEDED
        job.finished_at = utc_now() - timedelta(days=10)
        self.session.flush()
        self.assertEqual(self.queue.purge_finished(utc_now() - timedelta(days=7)), 1)
        self.assertEqual(self.jobs(), [])


class TriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        from sqlalchemy import event
        event.listen(self.session, "after_flush", enqueue_for_changes)
        self.addCleanup(self.session.close)

    def pending(self):
        return sorted(
            (str(job.connection_id), job.topic)
            for job in self.session.scalars(select(IngestionJob).where(IngestionJob.status == PENDING))
        )

    def test_structure_change_queues_every_topic_once(self) -> None:
        connection, *_ = seed_catalog(self.session)
        self.session.commit()
        self.assertEqual(self.pending(), sorted((str(connection.id), topic) for topic in TOPICS))
        self.assertEqual({job.source for job in self.session.scalars(select(IngestionJob))}, {EVENT})

    def test_glossary_change_queues_only_dependent_topics(self) -> None:
        connection, table, _, metric = seed_catalog(self.session)
        self.session.commit()
        self.session.execute(IngestionJob.__table__.update().values(status=SUCCEEDED))
        self.session.commit()
        GlossaryService(self.session).create_term({
            "connection_id": connection.id, "canonical_name": "Doanh số",
            "definition": "Tổng tiền", "synonyms": [], "links": [],
        })
        self.session.commit()
        self.assertEqual(
            self.pending(),
            sorted((str(connection.id), topic) for topic in ("glossary", "expert_rule", "own_knowledge")),
        )

    def test_unmodified_and_unwatched_objects_do_not_queue(self) -> None:
        connection, table, _, metric = seed_catalog(self.session)
        self.session.commit()
        self.session.execute(IngestionJob.__table__.update().values(status=SUCCEEDED))
        self.session.commit()
        metric.label = metric.label
        connection.name = "Renamed"
        self.session.commit()
        self.assertEqual(self.pending(), [])

    def test_metric_edit_and_delete_queue_metric_topics(self) -> None:
        connection, table, _, metric = seed_catalog(self.session)
        self.session.commit()
        self.session.execute(IngestionJob.__table__.update().values(status=SUCCEEDED))
        self.session.commit()
        metric.label = "Doanh thu ròng"
        self.session.commit()
        self.assertEqual(
            self.pending(),
            sorted((str(connection.id), topic) for topic in ("metric", "glossary", "expert_rule", "own_knowledge")),
        )
        self.session.execute(IngestionJob.__table__.update().values(status=SUCCEEDED))
        self.session.commit()
        self.session.delete(metric)
        self.session.commit()
        self.assertIn((str(connection.id), "metric"), self.pending())

    def test_own_knowledge_entry_queues_own_knowledge_only(self) -> None:
        connection, table, _, _ = seed_catalog(self.session)
        self.session.commit()
        self.session.execute(IngestionJob.__table__.update().values(status=SUCCEEDED))
        self.session.commit()
        self.session.add(OwnKnowledgeEntry(
            connection_id=connection.id, user_id="alice", kind="metric", name="Mưa", normalized_name="mua",
            definition="x",
        ))
        self.session.commit()
        self.assertEqual(self.pending(), [(str(connection.id), "own_knowledge")])


class FakeSync:
    calls: list = []
    error: Exception | None = None

    def __init__(self, session, index, embedding) -> None:
        pass

    def sync(self, connection_id, topics):
        FakeSync.calls.append((connection_id, tuple(topics)))
        if FakeSync.error is not None:
            raise FakeSync.error
        return SimpleNamespace(total=3, indexed=2, unchanged=1, deleted=0)


class FakeClient:
    def close(self) -> None:
        pass


class WorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.factory() as session:
            self.connection, *_ = seed_catalog(session)
            session.execute(IngestionJob.__table__.delete())
            IngestionJobQueue(session).enqueue([self.connection.id], ["metric"], EVENT)
            session.commit()
        FakeSync.calls, FakeSync.error = [], None
        patches = [
            patch("backend.modules.text2sql.worker.IngestionService", FakeSync),
            patch("backend.modules.text2sql.worker.QdrantDbService", FakeClient),
            patch("backend.modules.text2sql.worker.OpenRouterEmbedding", FakeClient),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.worker = IngestionWorker(self.factory, intervals={topic: 300 for topic in TOPICS}, concurrency=2)

    def only_job(self) -> IngestionJob:
        with self.factory() as session:
            return session.scalars(select(IngestionJob)).one()

    def test_claim_execute_and_finish_records_result(self) -> None:
        claimed = self.worker.claim()
        self.assertEqual(claimed[1:], (self.connection.id, "metric"))
        self.assertIsNone(self.worker.claim())
        self.worker.execute(*claimed)
        job = self.only_job()
        self.assertEqual(job.status, SUCCEEDED)
        self.assertEqual((job.result["indexed"], job.result["unchanged"]), (2, 1))
        self.assertEqual(FakeSync.calls, [(self.connection.id, ("metric",))])

    def test_failed_sync_is_retried_without_leaking_details(self) -> None:
        FakeSync.error = Text2SqlIndexUnavailable()
        self.worker.execute(*self.worker.claim())
        job = self.only_job()
        self.assertEqual((job.status, job.attempts), (PENDING, 1))
        self.assertTrue(job.last_error.startswith("text2sql_index_unavailable"))
        FakeSync.error = RuntimeError("password=secret")
        with self.factory() as session:
            session.scalars(select(IngestionJob)).one().run_after = utc_now() - timedelta(seconds=1)
            session.commit()
        self.worker.execute(*self.worker.claim())
        self.assertEqual(self.only_job().last_error, "RuntimeError")

    def test_schedule_creates_jobs_for_each_topic_once(self) -> None:
        self.worker.schedule_due_topics()
        self.worker.schedule_due_topics()
        with self.factory() as session:
            scheduled = [job.topic for job in session.scalars(select(IngestionJob)) if job.source == SCHEDULE]
        self.assertEqual(sorted(scheduled), sorted(topic for topic in TOPICS if topic != "metric"))

    def test_topic_interval_parsing(self) -> None:
        self.assertEqual(parse_topic_intervals("")["metric"], 300)
        self.assertEqual(parse_topic_intervals("metric=60, own_knowledge=45")["own_knowledge"], 45)
        for bad in ("metric", "metric=abc", "unknown=60", "metric=5"):
            with self.assertRaises(ValueError):
                parse_topic_intervals(bad)


if __name__ == "__main__":
    unittest.main()
