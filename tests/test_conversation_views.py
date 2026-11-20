import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.conversation.dependencies import get_conversation_service
from backend.modules.conversation.repositories.conversation_repository import ConversationRepository
from backend.modules.conversation.services import ConversationService, normalize_results
from backend.modules.database_connection.models import DatabaseConnection

BASE = "/api/v1/conversations"
FIELDS = [
    {"name": "thanh_pho", "label": "Thành phố", "type": "text"},
    {"name": "luong_mua", "label": "Lượng mưa", "type": "number", "unit": "mm", "role": "measure",
     "additive": True},
]
ROWS = [["Hue", 12.5], ["Vinh", 3], ["Ha Noi", 1]]
STORED = {
    "position": 1, "result_id": "1-1", "sql": "SELECT 1", "columns": ["thanh_pho", "luong_mua"], "rows": ROWS,
    "row_count": 3, "fields": FIELDS, "chart": {"version": 1, "type": "bar"}, "chart_source": "auto",
    "chart_types": ["bar", "table"], "display": "chart_if_last",
}
LEGACY = {"sql": "SELECT 1", "columns": ["thanh_pho", "luong_mua"], "rows": ROWS, "row_count": 3}
BAR = {"type": "bar_horizontal", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "luong_mua"}]}}


class ConversationViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x")
            session.add(connection)
            session.commit()
            self.connection_id = connection.id

        def service_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield ConversationService(session)

        app.dependency_overrides[get_conversation_service] = service_dependency
        self.client = TestClient(app)
        created = self.client.post(BASE, json={"connection_id": str(self.connection_id), "user_id": "alice"})
        self.conversation_id = created.json()["id"]

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def seed(self, results: list, max_rows: int | None = None) -> str:
        with Session(self.engine, expire_on_commit=False) as session:
            service = ConversationService(session)
            if max_rows is not None:
                service.max_stored_rows = max_rows
            conversation = service.get_owned(UUID(self.conversation_id), "alice")
            turn = service.begin_turn(conversation, "Mưa theo thành phố")
            service.complete_turn(turn, status="answered", flow="dataset", answer="Huế mưa nhiều nhất.",
                                  results=results)
            session.commit()
            return str(turn.id)

    def url(self, turn_id: str, result_id: str = "1-1") -> str:
        return f"{BASE}/{self.conversation_id}/turns/{turn_id}/views/{result_id}"

    def turn(self, turn_id: str) -> dict:
        return self.client.get(f"{BASE}/{self.conversation_id}/turns/{turn_id}", params={"user_id": "alice"}).json()

    def test_put_saves_view_and_turn_returns_it(self) -> None:
        turn_id = self.seed([STORED])
        saved = self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": BAR})
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertEqual((body["result_id"], body["chart"]["type"], body["warnings"]), ("1-1", "bar_horizontal", []))
        self.assertEqual(body["chart"]["encoding"]["y"][0]["aggregate"], "none")
        views = self.turn(turn_id)["views"]
        self.assertEqual(views["1-1"]["chart"], body["chart"])
        self.assertEqual(views["1-1"]["updated_at"], body["updated_at"])

    def test_invalid_chart_is_400_with_messages(self) -> None:
        turn_id = self.seed([STORED])
        spec = {"type": "bar", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "tong"}]}}
        response = self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": spec})
        self.assertEqual(response.status_code, 400)
        self.assertIn("không có cột 'tong'", response.text)
        self.assertIsNone(self.turn(turn_id)["views"])

    def test_missing_result_other_user_and_bad_id(self) -> None:
        turn_id = self.seed([STORED])
        missing = self.client.put(self.url(turn_id, "1-9"), json={"user_id": "alice", "chart": BAR})
        self.assertEqual(missing.status_code, 404)
        other = self.client.put(self.url(turn_id), json={"user_id": "bob", "chart": BAR})
        self.assertEqual(other.status_code, 404)
        self.assertEqual(self.client.put(self.url(turn_id, "abc"), json={"user_id": "alice", "chart": BAR})
                         .status_code, 422)
        self.assertEqual(self.client.delete(self.url(turn_id), params={"user_id": "bob"}).status_code, 404)

    def test_delete_view(self) -> None:
        turn_id = self.seed([STORED])
        self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": BAR})
        self.assertEqual(self.client.delete(self.url(turn_id), params={"user_id": "alice"}).status_code, 204)
        self.assertEqual(self.turn(turn_id)["views"], {})
        self.assertEqual(self.client.delete(self.url(turn_id), params={"user_id": "alice"}).status_code, 204)

    def test_two_views_are_both_kept(self) -> None:
        second = {**STORED, "result_id": "1-2"}
        turn_id = self.seed([STORED, second])
        self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": BAR})
        self.client.put(self.url(turn_id, "1-2"), json={"user_id": "alice", "chart": {"type": "table"}})
        self.assertEqual(set(self.turn(turn_id)["views"]), {"1-1", "1-2"})

    def test_legacy_results_get_ids_fields_and_types(self) -> None:
        turn_id = self.seed([LEGACY, {"kind": "column_values", "rows": [["Hue"]]}, LEGACY])
        results = self.turn(turn_id)["results"]
        self.assertEqual([item.get("result_id") for item in results], ["1-1", None, "1-2"])
        first = results[0]
        self.assertEqual([field["type"] for field in first["fields"]], ["text", "number"])
        self.assertEqual((first["chart"], first["chart_source"], first["display"]), (None, None, "none"))
        self.assertIn("bar", first["chart_types"])
        self.assertEqual(first["chart_types"][-1], "table")
        saved = self.client.put(self.url(turn_id, "1-2"), json={"user_id": "alice", "chart": BAR})
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_stored_truncated_turns_data_rules_into_warnings(self) -> None:
        turn_id = self.seed([STORED], max_rows=2)
        self.assertTrue(self.turn(turn_id)["results"][0]["stored_truncated"])
        spec = {"type": "histogram", "encoding": {"x": {"field": "luong_mua"}}}
        saved = self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": spec})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(any("histogram: cần ít nhất 10" in item for item in saved.json()["warnings"]))

    def test_put_locks_the_conversation(self) -> None:
        turn_id = self.seed([STORED])
        original = ConversationRepository.conversation
        calls = []

        def spy(repository, conversation_id, lock=False):
            calls.append(lock)
            return original(repository, conversation_id, lock)

        with patch.object(ConversationRepository, "conversation", spy):
            self.client.put(self.url(turn_id), json={"user_id": "alice", "chart": BAR})
        self.assertIn(True, calls)

    def test_normalize_keeps_new_results_and_counts_per_position(self) -> None:
        found = normalize_results([STORED, {**LEGACY, "position": 2}, {**LEGACY, "position": 1}])
        self.assertEqual([item["result_id"] for item in found], ["1-1", "2-1", "1-2"])
        self.assertIs(found[0], STORED)
        self.assertIsNone(normalize_results(None))


if __name__ == "__main__":
    unittest.main()
