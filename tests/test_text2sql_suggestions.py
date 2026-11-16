import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.core.database import get_database
from backend.main import app
from backend.modules.conversation.models import Conversation, ConversationTurn, ConversationTurnFeedback
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.metric_management.models import Metric
from backend.modules.model_registry import register_all_models

register_all_models()
URL = "/api/v1/text2sql/suggestions"
START = datetime(2026, 1, 1, tzinfo=UTC)


class SuggestionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.rules: list[dict] = []
        self.rule_calls = 0
        self.clock = 0
        with Session(self.engine) as s:
            connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            other = DatabaseConnection(name=f"o-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            s.add_all([connection, other])
            s.flush()
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            s.add(schema)
            s.flush()
            orders = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE")
            stock = DatabaseTable(schema_id=schema.id, name="stock", table_type="TABLE")
            s.add_all([orders, stock])
            s.flush()
            s.add_all([
                DatabaseColumn(table_id=orders.id, name="ordered_at", data_type="timestamp with time zone",
                               ordinal_position=1, is_nullable=True),
                DatabaseColumn(table_id=stock.id, name="qty", data_type="integer", ordinal_position=1,
                               is_nullable=True),
                Metric(table_id=orders.id, name="revenue", label="Doanh thu", expression="SUM(total)"),
                Metric(table_id=stock.id, name="stock_qty", label="Tồn kho", expression="SUM(qty)"),
                Metric(table_id=orders.id, name="old", label="Cũ", expression="COUNT(*)", is_active=False),
                Metric(table_id=orders.id, name="virtual", label="Ảo", expression="COUNT(*)", source_sql="SELECT 1"),
            ])
            s.commit()
            self.connection_id, self.other_id = connection.id, other.id

        def database():
            with Session(self.engine) as session:
                yield session

        def discovery(service, connection_id):
            self.rule_calls += 1
            return self.rules

        app.dependency_overrides[get_database] = database
        self.addCleanup(app.dependency_overrides.clear)
        patcher = patch.object(ExpertRuleService, "discovery", discovery)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def turn(self, user_id: str, question: str, status: str = "answered", connection_id=None, rating: str | None = None,
             results: list | None = None) -> None:
        self.clock += 1
        with Session(self.engine) as s:
            conversation = Conversation(connection_id=connection_id or self.connection_id, user_id=user_id, title="t")
            s.add(conversation)
            s.flush()
            turn = ConversationTurn(conversation_id=conversation.id, sequence=1, question=question, status=status,
                                    results=results, created_at=START + timedelta(minutes=self.clock))
            s.add(turn)
            s.flush()
            if rating is not None:
                s.add(ConversationTurnFeedback(turn_id=turn.id, user_id=user_id, rating=rating))
            s.commit()

    def get(self, **params) -> list[tuple[str, str]]:
        response = self.client.get(URL, params={"connection_id": str(self.connection_id), **params})
        self.assertEqual(response.status_code, 200, response.text)
        return [(item["question"], item["source"]) for item in response.json()]

    def test_sources_come_in_priority_order_and_duplicates_are_dropped(self) -> None:
        self.turn("alice", "Doanh thu theo vùng?")
        self.turn("alice", "  Số đơn   hôm nay? ")
        self.rules = [
            {"examples": [{"question": "số đơn hôm nay?", "intent": "x"},
                          {"question": "Mưa lớn không?", "intent": "y"}]},
            {"examples": [{"question": "  ", "intent": "z"}]},
        ]
        self.assertEqual(self.get(user_id="alice", limit=20), [
            ("Số đơn hôm nay?", "history"), ("Doanh thu theo vùng?", "history"), ("Mưa lớn không?", "rule_example"),
            ("Doanh thu theo tháng", "metric"), ("Tồn kho là bao nhiêu?", "metric"),
        ])

    def test_history_skips_other_users_failed_turns_downvotes_and_other_connections(self) -> None:
        self.turn("alice", "Câu được thích", rating="up")
        self.turn("alice", "Câu bị chê", rating="down")
        self.turn("alice", "Câu lỗi", status="error")
        self.turn("alice", "Câu cần làm rõ", status="needs_clarification")
        self.turn("alice", "Câu của connection khác", connection_id=self.other_id)
        self.turn("bob", "Câu của bob")
        history = [question for question, source in self.get(user_id="alice", limit=20) if source == "history"]
        self.assertEqual(history, ["Câu được thích"])
        self.assertNotIn("Câu của bob", str(self.get(limit=20)))
        self.assertNotIn("history", [source for _, source in self.get(limit=20)])

    def test_metric_questions_prefer_metrics_used_in_saved_turns(self) -> None:
        stock = {"kind": "metric", "metric": {"name": "stock_qty", "label": "Tồn kho"}, "rows": []}
        self.turn("bob", "Tồn kho?", results=[stock])
        self.turn("carol", "Tồn kho nữa?", results=[stock, {"kind": "dataset", "rows": []}])
        self.turn("carol", "Lỗi", status="error", results=[{"kind": "metric", "metric": {"name": "revenue"}}])
        self.assertEqual(self.get(), [("Tồn kho là bao nhiêu?", "metric"), ("Doanh thu theo tháng", "metric")])

    def test_limit_defaults_to_six_is_capped_and_stops_early(self) -> None:
        for index in range(8):
            self.turn("alice", f"Câu {index}")
        self.assertEqual(len(self.get(user_id="alice")), 6)
        self.assertEqual(self.get(user_id="alice", limit=2), [("Câu 7", "history"), ("Câu 6", "history")])
        self.assertEqual(self.rule_calls, 0)
        for limit in (0, 21):
            response = self.client.get(URL, params={"connection_id": str(self.connection_id), "limit": limit})
            self.assertEqual(response.status_code, 422)

    def test_unknown_connection_is_404(self) -> None:
        response = self.client.get(URL, params={"connection_id": str(uuid4())})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Không tìm thấy connection.")
        self.assertEqual(self.client.get(URL).status_code, 422)


if __name__ == "__main__":
    unittest.main()
