import unittest
from datetime import timedelta
from importlib import import_module
from uuid import UUID, uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import TECHNICAL_SCHEMA, Base
from backend.main import app
from backend.modules.conversation.dependencies import get_conversation_service
from backend.modules.conversation.models import Conversation
from backend.modules.conversation.services import ConversationService
from backend.modules.database_connection.models import DatabaseConnection

BASE = "/api/v1/conversations"
TABLES = ("conversation_turn_feedback", "conversation_turns", "conversations")


class ConversationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            first = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x")
            second = DatabaseConnection(name="Sales", dialect="postgresql", uri_ciphertext="y")
            session.add_all([first, second])
            session.commit()
            self.connection_id, self.other_connection_id = first.id, second.id

        def service_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield ConversationService(session)

        app.dependency_overrides[get_conversation_service] = service_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def create(self, user_id: str = "alice", title: str | None = None, connection_id=None) -> dict:
        body = {"connection_id": str(connection_id or self.connection_id), "user_id": user_id}
        if title is not None:
            body["title"] = title
        response = self.client.post(BASE, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def seed_turns(self, conversation_id: str, specs: list[tuple[str, str | None]]) -> list[str]:
        ids = []
        with Session(self.engine, expire_on_commit=False) as session:
            service = ConversationService(session)
            conversation = service.get_owned(UUID(conversation_id), "alice")
            for question, status in specs:
                turn = service.begin_turn(conversation, question)
                if status is not None:
                    service.complete_turn(
                        turn, status=status, flow="dataset", answer="Kết quả",
                        error_code="query_failed" if status == "error" else None,
                        error_message="psycopg: password=secret timeout" if status == "error" else None,
                        results=[{"sql": "SELECT 1", "rows": [[1]], "row_count": 1}],
                    )
                ids.append(str(turn.id))
            session.commit()
        return ids

    def test_create_validation_and_missing_connection(self) -> None:
        created = self.create()
        self.assertEqual((created["title"], created["turn_count"], created["is_pinned"]), ("", 0, False))
        self.assertIsNone(created["last_message_at"])
        self.assertEqual(self.create(title="  Báo   cáo quý  ")["title"], "Báo cáo quý")
        body = {"connection_id": str(self.connection_id), "user_id": "alice"}
        self.assertEqual(self.client.post(BASE, json={**body, "title": "   "}).status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "title": "x" * 201}).status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "title": "x" * 200}).status_code, 201)
        self.assertEqual(self.client.post(BASE, json={**body, "user_id": ""}).status_code, 422)
        missing = self.client.post(BASE, json={**body, "connection_id": str(uuid4())})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "Kết nối dữ liệu không tồn tại.")

    def test_list_filters_order_search_and_pagination(self) -> None:
        old = self.create(title="Doanh thu cũ")
        pinned = self.create(title="Ghim 100%")
        newest = self.create(title="doanh THU mới")
        archived = self.create(title="Doanh thu lưu trữ")
        other_connection = self.create(title="Doanh thu Sales", connection_id=self.other_connection_id)
        self.create(user_id="bob", title="Doanh thu của Bob")
        self.seed_turns(old["id"], [("Câu cũ", "answered")])
        self.seed_turns(newest["id"], [("Câu một", "answered"), ("Câu cuối " + "dài " * 60, None)])
        with Session(self.engine) as session:
            row = session.get(Conversation, UUID(old["id"]))
            row.last_message_at = row.last_message_at - timedelta(days=1)
            session.commit()
        user = {"user_id": "alice"}
        self.assertEqual(self.client.get(BASE).status_code, 422)
        self.assertEqual(self.client.patch(f"{BASE}/{pinned['id']}", json={
            "user_id": "alice", "is_pinned": True,
        }).json()["is_pinned"], True)
        self.assertEqual(self.client.patch(f"{BASE}/{archived['id']}", json={
            "user_id": "alice", "is_archived": True,
        }).json()["is_archived"], True)
        listed = self.client.get(BASE, params=user).json()
        self.assertEqual([item["id"] for item in listed][:3], [pinned["id"], newest["id"], old["id"]])
        self.assertEqual({item["id"] for item in listed}, {
            pinned["id"], newest["id"], old["id"], other_connection["id"],
        })
        newest_item = listed[1]
        self.assertEqual(newest_item["turn_count"], 2)
        self.assertEqual(newest_item["last_status"], "running")
        self.assertTrue(newest_item["last_question"].endswith("…"))
        self.assertLessEqual(len(newest_item["last_question"]), 121)
        scoped = self.client.get(BASE, params={**user, "connection_id": str(self.connection_id)}).json()
        self.assertNotIn(other_connection["id"], {item["id"] for item in scoped})
        self.assertEqual([item["id"] for item in self.client.get(BASE, params={**user, "archived": True}).json()],
                         [archived["id"]])
        found = self.client.get(BASE, params={**user, "q": "  doanh thu "}).json()
        self.assertEqual({item["id"] for item in found}, {newest["id"], old["id"], other_connection["id"]})
        self.assertEqual([item["id"] for item in self.client.get(BASE, params={**user, "q": "100%"}).json()],
                         [pinned["id"]])
        self.assertEqual(self.client.get(BASE, params={**user, "q": "%"}).json()[0]["id"], pinned["id"])
        self.assertEqual(len(self.client.get(BASE, params={**user, "q": "_"}).json()), 0)
        page = self.client.get(BASE, params={**user, "limit": 2, "offset": 1}).json()
        self.assertEqual([item["id"] for item in page], [newest["id"], old["id"]])
        self.assertEqual(self.client.get(BASE, params={**user, "limit": 201}).status_code, 422)
        self.assertEqual(self.client.get(BASE, params={**user, "connection_id": str(uuid4())}).status_code, 404)

    def test_detail_update_delete_and_ownership(self) -> None:
        created = self.create()
        url = f"{BASE}/{created['id']}"
        turn_ids = self.seed_turns(created["id"], [("Câu một", "answered"), ("Câu hai", "error"), ("Ba", None)])
        detail = self.client.get(url, params={"user_id": "alice"}).json()
        self.assertEqual(detail["title"], "Câu một")
        self.assertEqual(detail["turn_count"], 3)
        self.assertEqual([turn["sequence"] for turn in detail["turns"]], [1, 2, 3])
        failed = detail["turns"][1]
        self.assertEqual(failed["error"], "AI Agent không hoàn tất được câu trả lời.")
        self.assertEqual(failed["error_code"], "query_failed")
        self.assertNotIn("error_message", failed)
        self.assertNotIn("secret", self.client.get(url, params={"user_id": "alice"}).text)
        self.assertIsNone(detail["turns"][0]["error"])
        self.assertEqual(detail["turns"][0]["results"][0]["stored_truncated"], False)
        limited = self.client.get(url, params={"user_id": "alice", "turns_limit": 1, "turns_offset": 1}).json()
        self.assertEqual([turn["id"] for turn in limited["turns"]], [turn_ids[1]])
        for method, kwargs in (
            ("get", {"params": {"user_id": "bob"}}),
            ("patch", {"json": {"user_id": "bob", "title": "Đổi"}}),
            ("delete", {"params": {"user_id": "bob"}}),
        ):
            response = getattr(self.client, method)(url, **kwargs)
            self.assertEqual(response.status_code, 404, method)
            self.assertEqual(response.json()["detail"], "Không tìm thấy hội thoại.")
        self.assertEqual(self.client.get(f"{BASE}/{uuid4()}", params={"user_id": "alice"}).status_code, 404)
        updated = self.client.patch(url, json={"user_id": "alice", "title": " Tên   mới ", "is_pinned": True}).json()
        self.assertEqual((updated["title"], updated["is_pinned"], updated["is_archived"]), ("Tên mới", True, False))
        self.assertEqual(self.client.patch(url, json={"user_id": "alice", "title": " "}).status_code, 400)
        self.assertEqual(self.client.patch(url, json={"user_id": "alice", "title": "y" * 201}).status_code, 400)
        self.assertEqual(self.client.patch(url, json={"user_id": "alice"}).json()["title"], "Tên mới")
        self.assertEqual(self.client.delete(url, params={"user_id": "alice"}).status_code, 204)
        self.assertEqual(self.client.get(url, params={"user_id": "alice"}).status_code, 404)
        with Session(self.engine) as session:
            for table in ("conversation_turns", "conversation_turn_feedback"):
                self.assertEqual(session.connection().exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar(), 0)

    def test_turn_routes_and_feedback(self) -> None:
        created = self.create()
        first, second = self.seed_turns(created["id"], [("Một", "answered"), ("Hai", "answered")])
        turns_url = f"{BASE}/{created['id']}/turns"
        alice = {"user_id": "alice"}
        self.assertEqual([turn["id"] for turn in self.client.get(turns_url, params=alice).json()], [first, second])
        self.assertEqual([turn["id"] for turn in self.client.get(
            turns_url, params={**alice, "limit": 1, "offset": 1}).json()], [second])
        self.assertEqual(self.client.get(turns_url, params={"user_id": "bob"}).status_code, 404)
        self.assertEqual(self.client.get(f"{turns_url}/{first}", params=alice).json()["question"], "Một")
        self.assertEqual(self.client.get(f"{turns_url}/{first}", params={"user_id": "bob"}).status_code, 404)
        missing = self.client.get(f"{turns_url}/{uuid4()}", params=alice)
        self.assertEqual((missing.status_code, missing.json()["detail"]), (404, "Không tìm thấy lượt hỏi đáp."))
        other = self.create()
        self.assertEqual(self.client.get(f"{BASE}/{other['id']}/turns/{first}", params=alice).status_code, 404)

        feedback_url = f"{turns_url}/{first}/feedback"
        saved = self.client.put(feedback_url, json={"user_id": "alice", "rating": "up", "comment": " Tốt "})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((saved.json()["rating"], saved.json()["comment"]), ("up", "Tốt"))
        again = self.client.put(feedback_url, json={"user_id": "alice", "rating": "down"}).json()
        self.assertEqual((again["rating"], again["comment"]), ("down", None))
        self.assertEqual(self.client.get(f"{turns_url}/{first}", params=alice).json()["feedback"]["rating"], "down")
        self.assertIsNone(self.client.get(f"{turns_url}/{second}", params=alice).json()["feedback"])
        self.assertEqual(self.client.put(feedback_url, json={"user_id": "alice", "rating": "meh"}).status_code, 422)
        self.assertEqual(self.client.put(feedback_url, json={
            "user_id": "alice", "rating": "up", "comment": "c" * 2001,
        }).status_code, 422)
        self.assertEqual(self.client.put(feedback_url, json={"user_id": "bob", "rating": "up"}).status_code, 404)
        self.assertEqual(self.client.delete(feedback_url, params={"user_id": "bob"}).status_code, 404)
        self.assertEqual(self.client.delete(feedback_url, params=alice).status_code, 204)
        self.assertIsNone(self.client.get(f"{turns_url}/{first}", params=alice).json()["feedback"])
        self.assertEqual(self.client.delete(feedback_url, params=alice).status_code, 204)

        self.client.put(feedback_url, json={"user_id": "alice", "rating": "up"})
        self.assertEqual(self.client.delete(f"{turns_url}/{first}", params={"user_id": "bob"}).status_code, 404)
        self.assertEqual(self.client.delete(f"{turns_url}/{first}", params=alice).status_code, 204)
        self.assertEqual(self.client.get(f"{turns_url}/{first}", params=alice).status_code, 404)
        self.assertEqual(self.client.delete(f"{turns_url}/{first}", params=alice).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/{created['id']}", params=alice).json()["turn_count"], 1)

    def test_migration_matches_models(self) -> None:
        package = "backend.migrations.versions.init_conversation_module"
        migrations = [
            import_module(f"{package}.a4c2e8f61b37_create_conversation"),
            import_module(f"{package}.c5e1d7a3b902_add_turn_continuation"),
        ]
        with self.engine.begin() as connection:
            for table in TABLES:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
            context = MigrationContext.configure(connection, opts={
                "include_object": lambda obj, name, type_, reflected, compare_to:
                    getattr(obj, "schema", None) != TECHNICAL_SCHEMA
            })
            with Operations.context(context):
                for migration in migrations:
                    migration.upgrade()
            self.assertTrue(set(TABLES) <= set(inspect(connection).get_table_names()))
            self.assertEqual(compare_metadata(context, Base.metadata), [])
            columns = {column["name"] for column in inspect(connection).get_columns("conversation_turns")}
            self.assertTrue({"continued_from", "continuation", "clarification_options"} <= columns)
            with Operations.context(context):
                migrations[1].downgrade()
            columns = {column["name"] for column in inspect(connection).get_columns("conversation_turns")}
            self.assertFalse({"continued_from", "continuation", "clarification_question"} & columns)
            with Operations.context(context):
                migrations[0].downgrade()
            self.assertFalse(set(TABLES) & set(inspect(connection).get_table_names()))


if __name__ == "__main__":
    unittest.main()
