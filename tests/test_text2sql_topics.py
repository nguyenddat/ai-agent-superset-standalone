import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.core.setting import config
from backend.modules.data_dictionary.models import ColumnDictionary, ColumnSynonym, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric
from backend.modules.model_registry import register_all_models
from backend.modules.own_knowledge.models import OwnKnowledgeEntry
from backend.modules.text2sql.common.errors import (
    Text2SqlConnectionNotFound,
    Text2SqlEntityNotFound,
    Text2SqlInvalidRequest,
    Text2SqlRerankUnavailable,
)
from backend.modules.text2sql.details.service import DetailService
from backend.modules.text2sql.vector_store.retrieve.topic_search import TopicSearchService

register_all_models()


def point(entity_id, text, table_id=None, score=1.0, **payload):
    return {"score": score, "payload": {
        "entity_id": str(entity_id), "table_id": str(table_id) if table_id else None, "text": text,
        "name": payload.pop("name", text), "display_name": payload.pop("display_name", text), **payload,
    }}


class RecordingIndex:
    def __init__(self, points=None):
        self.points = points or []
        self.calls = []

    def search(self, question, vector, connection_id, topic, limit, filters=None):
        self.calls.append({"topic": topic, "limit": limit, "filters": filters, "connection_id": connection_id})
        return list(self.points)


class FakeEmbedding:
    def embed(self, texts):
        return [[0.1] * 4 for _ in texts]


class StaticReranker:
    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.subjects = scores, error, []

    def rerank(self, question, passages, subject="metric"):
        self.subjects.append(subject)
        if self.error is not None:
            raise self.error
        return list(self.scores)


class ConnectionSession:
    def get(self, model, entity_id):
        return SimpleNamespace(id=entity_id)


class MissingConnectionSession:
    def get(self, model, entity_id):
        return None


class TopicSearchTests(unittest.TestCase):
    def service(self, index, session=None):
        return TopicSearchService(session or ConnectionSession(), index, FakeEmbedding())

    def test_searches_the_requested_topic_inside_the_connection(self) -> None:
        connection_id, first, second = uuid4(), uuid4(), uuid4()
        index = RecordingIndex([point(first, "Bảng A", score=0.9), point(second, "Bảng B", score=0.5)])
        outcome = self.service(index).search(connection_id, "table", "câu hỏi", 5)
        self.assertEqual([hit.entity_id for hit in outcome.hits], [first, second])
        self.assertEqual((index.calls[0]["topic"], index.calls[0]["connection_id"]), ("table", str(connection_id)))
        self.assertIsNone(index.calls[0]["filters"])
        self.assertFalse(outcome.reranked)

    def test_k_limits_results_and_the_query_when_not_reranking(self) -> None:
        index = RecordingIndex([point(uuid4(), f"t{n}") for n in range(5)])
        outcome = self.service(index).search(uuid4(), "glossary", "q", 2)
        self.assertEqual(len(outcome.hits), 2)
        self.assertEqual(index.calls[0]["limit"], 2)

    def test_own_knowledge_is_filtered_by_user_and_requires_one(self) -> None:
        index = RecordingIndex([point(uuid4(), "Ngày mưa")])
        self.service(index).search(uuid4(), "own_knowledge", "q", 3, user_id=" alice ")
        self.assertEqual(index.calls[0]["filters"], {"user_id": "alice"})
        for missing in (None, "", "   "):
            with self.subTest(user_id=missing), self.assertRaises(Text2SqlInvalidRequest):
                self.service(index).search(uuid4(), "own_knowledge", "q", 3, user_id=missing)

    def test_unknown_topic_and_missing_connection_are_rejected(self) -> None:
        with self.assertRaises(Text2SqlInvalidRequest):
            self.service(RecordingIndex()).search(uuid4(), "bogus", "q", 3)
        with self.assertRaises(Text2SqlConnectionNotFound):
            self.service(RecordingIndex(), MissingConnectionSession()).search(uuid4(), "table", "q", 3)

    def test_reranker_reorders_by_its_score_and_names_the_topic(self) -> None:
        ids = [uuid4(), uuid4(), uuid4()]
        index = RecordingIndex([point(ids[0], "a"), point(ids[1], "b"), point(ids[2], "c")])
        reranker = StaticReranker(scores=[0.2, 0.9, 0.5])
        outcome = self.service(index).search(uuid4(), "expert_rule", "q", 2, reranker)
        self.assertTrue(outcome.reranked)
        self.assertEqual([hit.entity_id for hit in outcome.hits], [ids[1], ids[2]])
        self.assertEqual(outcome.hits[0].rerank_score, 0.9)
        self.assertEqual(reranker.subjects, ["expert_rule"])

    def test_rerank_pool_is_wider_than_k_but_ties_keep_search_order(self) -> None:
        ids = [uuid4() for _ in range(3)]
        index = RecordingIndex([point(entity, "x") for entity in ids])
        with patch.object(config, "text2sql_rerank_pool", 12):
            outcome = self.service(index).search(uuid4(), "column", "q", 2, StaticReranker(scores=[0.5] * 3))
        self.assertEqual(index.calls[0]["limit"], 12)
        self.assertEqual([hit.entity_id for hit in outcome.hits], ids[:2])

    def test_rerank_failure_falls_back_to_search_order(self) -> None:
        ids = [uuid4(), uuid4()]
        index = RecordingIndex([point(ids[0], "a"), point(ids[1], "b")])
        outcome = self.service(index).search(
            uuid4(), "table", "q", 2, StaticReranker(error=Text2SqlRerankUnavailable())
        )
        self.assertFalse(outcome.reranked)
        self.assertEqual(outcome.rerank_error, "text2sql_rerank_unavailable")
        self.assertEqual([hit.entity_id for hit in outcome.hits], ids)
        self.assertEqual({hit.rerank_score for hit in outcome.hits}, {None})


class DetailServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        self.connection = DatabaseConnection(name=f"main-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        self.other = DatabaseConnection(name=f"other-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add_all([self.connection, self.other])
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        other_schema = DatabaseSchema(connection_id=self.other.id, name="public")
        s.add_all([schema, other_schema])
        s.flush()
        self.table = DatabaseTable(schema_id=schema.id, name="sales", table_type="TABLE")
        self.other_table = DatabaseTable(schema_id=other_schema.id, name="other_sales", table_type="TABLE")
        s.add_all([self.table, self.other_table])
        s.flush()
        self.region = DatabaseColumn(
            table_id=self.table.id, name="region", data_type="TEXT", ordinal_position=1, is_nullable=False
        )
        self.amount = DatabaseColumn(
            table_id=self.table.id, name="amount", data_type="NUMERIC", ordinal_position=2, is_nullable=False
        )
        self.metric = Metric(
            table_id=self.table.id, name="revenue", label="Doanh thu", expression="SUM(amount)",
            description="Tổng tiền", warning_text="Chưa trừ hoàn tiền",
        )
        self.virtual = Metric(
            table_id=self.table.id, name="virtual", expression="COUNT(*)", source_sql="SELECT 1",
        )
        self.inactive = Metric(table_id=self.table.id, name="old", expression="COUNT(*)", is_active=False)
        s.add_all([
            self.region, self.amount, self.metric, self.virtual, self.inactive,
            TableDictionary(table_id=self.table.id, display_name="Bán hàng", description="Giao dịch"),
        ])
        s.flush()
        dictionary = ColumnDictionary(column_id=self.region.id, display_name="Khu vực", unit="vùng")
        s.add(dictionary)
        s.flush()
        s.add(ColumnSynonym(column_dictionary_id=dictionary.id, synonym="miền"))
        s.flush()
        self.details = DetailService(s)

    def approved_term(self, name="Doanh số", links=None):
        service = GlossaryService(self.session)
        term = service.create_term({
            "connection_id": self.connection.id, "canonical_name": name, "group_name": "Bán hàng",
            "definition": "Tổng tiền bán", "synonyms": ["sales"],
            "links": links if links is not None else [
                {"kind": "table", "id": self.table.id}, {"kind": "column", "id": self.amount.id},
                {"kind": "metric", "id": self.metric.id},
            ],
        })
        service.approve(term["id"], 1)
        return term["id"]

    def test_tables_return_full_structured_description_with_columns(self) -> None:
        result = self.details.tables(self.connection.id, [self.table.id])
        self.assertEqual(len(result), 1)
        table = result[0].table
        self.assertEqual((table.display_name, table.table_name, table.schema_name), ("Bán hàng", "sales", "public"))
        self.assertEqual([column.name for column in table.columns], ["region", "amount"])
        region = table.columns[0]
        self.assertEqual((region.display_name, region.unit, region.synonyms), ("Khu vực", "vùng", ["miền"]))

    def test_tables_from_another_connection_are_dropped(self) -> None:
        self.assertEqual(self.details.tables(self.connection.id, [self.other_table.id]), [])
        self.assertEqual(self.details.tables(self.connection.id, [uuid4()]), [])

    def test_columns_return_column_structure_and_its_table(self) -> None:
        result = self.details.columns(self.connection.id, [(self.table.id, self.region.id)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].table.table_name, "sales")
        self.assertEqual((result[0].column.name, result[0].column.synonyms), ("region", ["miền"]))
        self.assertEqual(self.details.columns(self.connection.id, [(self.table.id, uuid4())]), [])
        self.assertEqual(self.details.columns(self.connection.id, [(self.other_table.id, uuid4())]), [])

    def test_metric_detail_includes_expression_and_referenced_columns(self) -> None:
        detail = self.details.metric(self.connection.id, self.metric.id)
        self.assertEqual((detail.expression, detail.warning_text), ("SUM(amount)", "Chưa trừ hoàn tiền"))
        self.assertEqual(detail.table.display_name, "Bán hàng")
        self.assertEqual([column.name for column in detail.referenced_columns], ["amount"])

    def test_metric_detail_hides_inactive_virtual_and_foreign_metrics(self) -> None:
        for metric_id in (self.inactive.id, self.virtual.id, uuid4()):
            with self.subTest(metric_id=metric_id), self.assertRaises(Text2SqlEntityNotFound):
                self.details.metric(self.connection.id, metric_id)
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.metric(self.other.id, self.metric.id)

    def test_glossary_detail_resolves_link_names_and_requires_serving_revision(self) -> None:
        term_id = self.approved_term()
        detail = self.details.glossary_term(self.connection.id, term_id)
        self.assertEqual((detail.name, detail.definition, detail.synonyms), ("Doanh số", "Tổng tiền bán", ["sales"]))
        self.assertEqual(
            sorted((link.kind, link.name) for link in detail.links),
            [("column", "amount"), ("metric", "Doanh thu"), ("table", "Bán hàng")],
        )
        draft = GlossaryService(self.session).create_term({
            "connection_id": self.connection.id, "canonical_name": "Nháp", "group_name": None,
            "definition": "x", "synonyms": [], "links": [],
        })
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.glossary_term(self.connection.id, draft["id"])
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.glossary_term(self.other.id, term_id)

    def test_expert_rule_detail_has_structured_and_readable_conditions(self) -> None:
        term_id = self.approved_term()
        rules = ExpertRuleService(self.session)
        rule = rules.create_rule({
            "connection_id": self.connection.id, "table_id": self.table.id, "name": "Miền Bắc", "group_name": "Vùng",
            "description": "Chỉ miền Bắc",
            "conditions": [{"column_id": self.region.id, "operator": "equals", "value_type": "string",
                            "value": "Bắc"}],
            "exceptions": [{"when": "báo cáo quý", "outcome": "bỏ lọc"}],
            "examples": [{"question": "doanh thu miền Bắc", "intent": "lọc vùng"}],
            "glossary_term_ids": [term_id], "metric_ids": [self.metric.id],
        })
        rules.approve(rule["id"], 1)
        detail = self.details.expert_rule(self.connection.id, rule["id"])
        self.assertEqual(detail.table.table_name, "sales")
        self.assertEqual((detail.conditions[0].column_name, detail.conditions[0].text), ("Khu vực", "Khu vực bằng Bắc"))
        self.assertEqual((detail.exceptions[0].when, detail.examples[0].intent), ("báo cáo quý", "lọc vùng"))
        self.assertEqual([item.name for item in detail.glossary_terms], ["Doanh số"])
        self.assertEqual([item.name for item in detail.metrics], ["Doanh thu"])
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.expert_rule(self.other.id, rule["id"])

    def test_unapproved_expert_rule_is_not_visible(self) -> None:
        term_id = self.approved_term()
        rule = ExpertRuleService(self.session).create_rule({
            "connection_id": self.connection.id, "table_id": self.table.id, "name": "Nháp", "group_name": None,
            "description": None,
            "conditions": [{"column_id": self.region.id, "operator": "equals", "value_type": "string",
                            "value": "Bắc"}],
            "exceptions": [], "examples": [], "glossary_term_ids": [term_id], "metric_ids": [],
        })
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.expert_rule(self.connection.id, rule["id"])

    def test_own_knowledge_detail_is_private_to_its_user(self) -> None:
        entry = OwnKnowledgeEntry(
            connection_id=self.connection.id, user_id="alice", kind="glossary", name="Ngày mưa",
            normalized_name="ngay mua", definition="Ngày mưa trên 1mm", table_id=self.table.id,
        )
        self.session.add(entry)
        self.session.flush()
        detail = self.details.own_entry(self.connection.id, "alice", entry.id)
        self.assertEqual(
            (detail.name, detail.definition, detail.table.table_name), ("Ngày mưa", "Ngày mưa trên 1mm", "sales")
        )
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.own_entry(self.connection.id, "bob", entry.id)
        with self.assertRaises(Text2SqlEntityNotFound):
            self.details.own_entry(self.other.id, "alice", entry.id)
        with self.assertRaises(Text2SqlInvalidRequest):
            self.details.own_entry(self.connection.id, "  ", entry.id)

    def test_unknown_connection_is_reported(self) -> None:
        with self.assertRaises(Text2SqlConnectionNotFound):
            self.details.metric(uuid4(), self.metric.id)


if __name__ == "__main__":
    unittest.main()
