import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.common.base_model import Base
from backend.core.setting import config
from backend.modules.business_model import models as business_model_models  # noqa: F401
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.metric_management.models import Metric
from backend.modules.text2sql.repositories.qdrant_repository import QdrantRepository
from backend.modules.text2sql.services.catalog_context import (
    load_context,
)
from backend.modules.text2sql.services.index_documents import TOPIC_BUILDERS
from backend.modules.text2sql.services.index_documents import (
    build_document as _document,
)
from backend.modules.text2sql.services.index_documents import (
    referenced_columns as _referenced_columns,
)
from backend.modules.text2sql.services.ingestion_service import IngestionService
from backend.modules.text2sql.services.retrieval_service import RetrievalService
from backend.modules.text2sql.utils.exceptions import Text2SqlRerankUnavailable


class EmbeddingTests(unittest.TestCase):
    def test_openrouter_embedding_reorders_response_by_index(self) -> None:
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"data": [
                {"index": 1, "embedding": [2.0] * 1536},
                {"index": 0, "embedding": [1.0] * 1536},
            ]})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(config, "openrouter_api_key", SimpleNamespace(get_secret_value=lambda: "test-key")):
            vectors = OpenRouterEmbedding(client).embed(["bảng", "metric"])
        self.assertEqual([vector[0] for vector in vectors], [1.0, 2.0])
        self.assertEqual(requests[0].url.path, "/api/v1/embeddings")
        self.assertIn(b"openai/text-embedding-3-small", requests[0].content)


class CatalogTests(unittest.TestCase):
    def test_catalog_builds_table_column_and_metric_topics(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                connection = DatabaseConnection(name="Weather", dialect="postgresql", uri_ciphertext="x")
                session.add(connection)
                session.flush()
                schema = DatabaseSchema(connection_id=connection.id, name="public")
                session.add(schema)
                session.flush()
                table = DatabaseTable(schema_id=schema.id, name="sales", table_type="TABLE")
                session.add(table)
                session.flush()
                column = DatabaseColumn(
                    table_id=table.id, name="amount", data_type="NUMERIC", ordinal_position=1, is_nullable=False
                )
                session.add_all([
                    column,
                    TableDictionary(table_id=table.id, display_name="Bán hàng", description="Số liệu doanh thu"),
                    Metric(table_id=table.id, name="revenue", label="Doanh thu", expression="SUM(amount)"),
                ])
                session.flush()
                session.add(ColumnDictionary(column_id=column.id, display_name="Số tiền"))
                session.flush()
                context = load_context(session, connection.id)
                documents = [
                    document for topic in ("table", "column", "metric")
                    for document in TOPIC_BUILDERS[topic](session, context)
                ]
            self.assertEqual({document.topic for document in documents}, {"table", "column", "metric"})
            metric_document = next(document for document in documents if document.topic == "metric")
            self.assertEqual(metric_document.payload["column_ids"], [str(column.id)])
            self.assertIn("Doanh thu", metric_document.text)
        finally:
            engine.dispose()

    def test_point_id_stable_and_hash_changes_with_payload(self) -> None:
        entity_id = uuid4()
        connection_id = uuid4()
        first = _document("metric", entity_id, connection_id, uuid4(), "Doanh thu", name="revenue")
        second = _document("metric", entity_id, connection_id, uuid4(), "Doanh thu", name="revenue")
        self.assertEqual(first.point_id, second.point_id)
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_metric_expression_links_to_known_columns(self) -> None:
        amount_id = uuid4()
        self.assertEqual(_referenced_columns("SUM(amount)", {"amount": amount_id}), [str(amount_id)])
        self.assertEqual(_referenced_columns("SUM(missing)", {"amount": amount_id}), [])


class FakeIndex:
    def __init__(self, existing=None, hits=None):
        self.existing = existing or {}
        self.hits = hits or {}
        self.upserted = []
        self.deleted = []

    def ensure_collection(self):
        pass

    def existing_points(self, connection_id, topics):
        return self.existing

    def upsert(self, points):
        self.upserted.extend(points)

    def delete(self, points):
        self.deleted.extend(points)

    def search(self, question, vector, connection_id, topic, limit):
        return self.hits.get(topic, [])


class FakeEmbedding:
    def embed(self, texts):
        return [[0.1] * 1536 for _ in texts]


class FakeScalarRows(list):
    def all(self):
        return list(self)


class FakeSession:
    def __init__(self, metrics=None, columns=None):
        self.metrics = metrics or []
        self.columns = columns or []

    def get(self, model, entity_id):
        return SimpleNamespace(id=entity_id)

    def scalars(self, statement):
        rows = self.columns if statement.column_descriptions[0]["entity"] is DatabaseColumn else self.metrics
        return FakeScalarRows(rows)


class ServiceTests(unittest.TestCase):
    def test_sync_skips_unchanged_and_deletes_stale(self) -> None:
        connection_id = uuid4()
        first = _document("table", uuid4(), connection_id, uuid4(), "Bảng thời tiết")
        second = _document("metric", uuid4(), connection_id, uuid4(), "Nhiệt độ trung bình")
        index = FakeIndex(existing={
            first.point_id: {"content_hash": first.content_hash},
            str(uuid4()): {"content_hash": "old"},
        })
        builders = {"table": lambda session, context: [first], "metric": lambda session, context: [second]}
        with (
            patch("backend.modules.text2sql.services.ingestion_service.load_context", return_value=None),
            patch.dict("backend.modules.text2sql.services.ingestion_service.TOPIC_BUILDERS", builders),
        ):
            result = IngestionService(FakeSession(), index, FakeEmbedding()).sync(connection_id, ["table", "metric"])
        self.assertEqual((result.total, result.indexed, result.unchanged, result.deleted), (2, 1, 1, 1))
        self.assertEqual([point["id"] for point in index.upserted], [second.point_id])
        self.assertEqual(len(index.deleted), 1)

    def test_retrieval_filters_and_ranks_metric_hits(self) -> None:
        connection_id = uuid4()
        table_id = uuid4()
        matching = SimpleNamespace(
            id=uuid4(), table_id=table_id, name="revenue", label="Doanh thu", description=None,
            expression="SUM(amount)",
        )
        other = SimpleNamespace(
            id=uuid4(), table_id=table_id, name="order_count", label="Số đơn", description=None,
            expression="COUNT(*)",
        )
        index = FakeIndex(hits={
            "metric": [
                {"payload": {"entity_id": str(matching.id), "column_ids": []}},
                {"payload": {"entity_id": str(other.id), "column_ids": []}},
            ],
            "table": [{"payload": {"table_id": str(table_id)}}],
        })
        result = RetrievalService(FakeSession([matching, other]), index, FakeEmbedding()).top_metrics(
            connection_id, "doanh thu", 1
        )
        self.assertEqual([candidate.metric_id for candidate in result], [matching.id])
        self.assertEqual(result[0].matched_topics, ["metric", "table"])

    def test_column_hit_recalls_metric_without_direct_metric_hit(self) -> None:
        connection_id = uuid4()
        table_id = uuid4()
        column_id = uuid4()
        metric = SimpleNamespace(
            id=uuid4(), table_id=table_id, name="revenue", label="Doanh thu",
            description=None, expression="SUM(amount)",
        )
        column = SimpleNamespace(id=column_id, table_id=table_id, name="amount")
        index = FakeIndex(hits={"column": [{"payload": {"entity_id": str(column_id)}}]})
        result = RetrievalService(FakeSession([metric], [column]), index, FakeEmbedding()).top_metrics(
            connection_id, "số tiền", 5
        )
        self.assertEqual([candidate.metric_id for candidate in result], [metric.id])
        self.assertEqual(result[0].matched_topics, ["column"])


class FakeReranker:
    def __init__(self, scores=None, error=None):
        self.scores = scores
        self.error = error
        self.received = []
        self.subjects = []

    def rerank(self, question, passages, subject="metric"):
        self.received.append(list(passages))
        self.subjects.append(subject)
        if self.error is not None:
            raise self.error
        return self.scores(passages) if callable(self.scores) else list(self.scores)


class RerankRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection_id = uuid4()
        table_id = uuid4()
        self.metrics = [
            SimpleNamespace(
                id=uuid4(), table_id=table_id, name=name, label=label, description=None, expression="COUNT(*)"
            )
            for name, label in (("order_count", "Số đơn"), ("revenue", "Doanh thu"), ("avg_ticket", "Giá trị đơn"))
        ]
        self.index = FakeIndex(hits={"metric": [
            {"payload": {"entity_id": str(metric.id), "column_ids": []}} for metric in self.metrics
        ]})
        documents = [
            SimpleNamespace(entity_id=str(metric.id), text=f"Metric: {metric.label}") for metric in self.metrics
        ]
        for target, value in (("load_context", None), ("build_metric_documents", documents)):
            patcher = patch(
                f"backend.modules.text2sql.services.retrieval_service.{target}",
                **({"return_value": value} if target == "build_metric_documents" else {"return_value": value}),
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def service(self) -> RetrievalService:
        return RetrievalService(FakeSession(self.metrics), self.index, FakeEmbedding())

    def test_without_reranker_keeps_retrieval_order_and_has_no_rerank_score(self) -> None:
        outcome = self.service().search(self.connection_id, "doanh thu", 3)
        self.assertEqual([candidate.name for candidate in outcome.candidates],
                         ["order_count", "revenue", "avg_ticket"])
        self.assertFalse(outcome.reranked)
        self.assertEqual({candidate.rerank_score for candidate in outcome.candidates}, {None})

    def test_reranker_reorders_candidates_by_its_score(self) -> None:
        reranker = FakeReranker(scores=lambda passages: [1.0 if "Doanh thu" in text else 0.1 for text in passages])
        outcome = self.service().search(self.connection_id, "doanh thu", 3, reranker)
        self.assertTrue(outcome.reranked)
        self.assertEqual(outcome.candidates[0].name, "revenue")
        self.assertEqual(outcome.candidates[0].rerank_score, 1.0)
        self.assertEqual(reranker.received[0][0], "Metric: Số đơn")

    def test_rerank_score_ties_fall_back_to_retrieval_order(self) -> None:
        outcome = self.service().search(self.connection_id, "q", 3, FakeReranker(scores=[0.5, 0.5, 0.5]))
        self.assertEqual([candidate.name for candidate in outcome.candidates],
                         ["order_count", "revenue", "avg_ticket"])

    def test_k_applies_after_reranking(self) -> None:
        reranker = FakeReranker(scores=[0.0, 0.2, 0.9])
        names = [candidate.name for candidate in self.service().top_metrics(self.connection_id, "q", 1, reranker)]
        self.assertEqual(names, ["avg_ticket"])

    def test_pool_is_capped_by_configuration_but_never_below_k(self) -> None:
        reranker = FakeReranker(scores=[0.3, 0.9])
        with patch.object(config, "text2sql_rerank_pool", 2):
            outcome = self.service().search(self.connection_id, "q", 1, reranker)
        self.assertEqual(len(reranker.received[0]), 2)
        self.assertEqual(outcome.candidates[0].name, "revenue")

    def test_reranker_failure_falls_back_to_retrieval_order_with_warning(self) -> None:
        reranker = FakeReranker(error=Text2SqlRerankUnavailable())
        outcome = self.service().search(self.connection_id, "q", 2, reranker)
        self.assertFalse(outcome.reranked)
        self.assertEqual(outcome.rerank_error, "text2sql_rerank_unavailable")
        self.assertEqual([candidate.name for candidate in outcome.candidates], ["order_count", "revenue"])
        self.assertEqual({candidate.rerank_score for candidate in outcome.candidates}, {None})

    def test_no_candidates_means_no_rerank_call(self) -> None:
        reranker = FakeReranker(scores=[])
        self.index.hits = {}
        outcome = self.service().search(self.connection_id, "q", 3, reranker)
        self.assertEqual((outcome.candidates, outcome.reranked, reranker.received), ([], False, []))


class IndexTests(unittest.TestCase):
    def test_hybrid_query_filters_connection_and_topic(self) -> None:
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"result": {"points": []}})

        client = httpx.Client(base_url="http://qdrant:6333", transport=httpx.MockTransport(respond))
        QdrantRepository(client).search("doanh thu", [0.1] * 1536, "connection-id", "metric", 5)
        body = requests[0].content.decode()
        self.assertIn('"rrf"', body)
        self.assertIn('"connection-id"', body)
        self.assertIn('"metric"', body)
        self.assertIn('"text"', body)


if __name__ == "__main__":
    unittest.main()
