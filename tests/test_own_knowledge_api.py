import unittest
from importlib import import_module
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import TECHNICAL_SCHEMA, Base
from backend.core.setting import config
from backend.main import app
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.dependencies import get_expert_rule_service
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.dependencies import get_glossary_service
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.own_knowledge.dependencies import get_own_knowledge_service
from backend.modules.own_knowledge.services import OwnKnowledgeService

BASE = "/api/v1/own-knowledge"
GLOSSARY = "/api/v1/glossary"
RULES = "/api/v1/expert-rules"
AGENT_HEADERS = {"X-Own-Knowledge-Key": "a" * 40}
ADMIN_HEADERS = {"X-Own-Knowledge-Key": "b" * 40}


class OwnKnowledgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent_key = patch.object(config, "own_knowledge_agent_key", SecretStr("a" * 40))
        self.admin_key = patch.object(config, "own_knowledge_admin_key", SecretStr("b" * 40))
        self.agent_key.start()
        self.admin_key.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x")
            session.add(connection)
            session.flush()
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            session.add(schema)
            session.flush()
            table = DatabaseTable(schema_id=schema.id, name="weather", table_type="TABLE")
            session.add(table)
            session.flush()
            column = DatabaseColumn(
                table_id=table.id, name="rain_mm", data_type="numeric", ordinal_position=1, is_nullable=False,
            )
            session.add(column)
            session.commit()
            self.connection_id, self.table_id, self.column_id = connection.id, table.id, column.id

        def service_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield OwnKnowledgeService(session)

        def glossary_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield GlossaryService(session)

        def expert_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield ExpertRuleService(session)

        app.dependency_overrides[get_own_knowledge_service] = service_dependency
        app.dependency_overrides[get_glossary_service] = glossary_dependency
        app.dependency_overrides[get_expert_rule_service] = expert_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.agent_key.stop()
        self.admin_key.stop()

    def push_body(self, kind: str = "glossary", name: str = "Mưa lớn", user_id: str = "alice") -> dict:
        return {
            "user_id": user_id, "connection_id": str(self.connection_id),
            "idempotency_key": f"turn-1-{kind}-{name}",
            "source_session_id": "session-1", "source_question_id": "question-1",
            "question": "Mưa lớn nghĩa là gì?", "missing": [kind],
            "proposals": [{
                "kind": kind, "name": name, "concept": "mưa lớn", "prompt": "Bạn hiểu thế nào là mưa lớn?",
                "options": ["Lượng mưa vượt 50 mm", "Lượng mưa vượt 70 mm"],
                "table_id": str(self.table_id),
            }],
        }

    def confirm(self, body: dict, option_index: int = 0) -> tuple[str, str]:
        pushed = self.client.post(f"{BASE}/clarifications", json=body, headers=AGENT_HEADERS)
        self.assertEqual(pushed.status_code, 201, pushed.text)
        clarification = pushed.json()
        answer = self.client.post(f"{BASE}/clarifications/{clarification['id']}/answer", json={
            "user_id": body["user_id"], "state": "confirmed",
            "answers": [{"proposal_id": clarification["proposals"][0]["id"], "option_index": option_index}],
        }, headers=AGENT_HEADERS)
        self.assertEqual(answer.status_code, 200, answer.text)
        return clarification["id"], answer.json()["entries"][0]["id"]

    def test_agent_push_answer_owner_scope_and_idempotency(self) -> None:
        body = self.push_body()
        self.assertEqual(self.client.post(f"{BASE}/clarifications", json=body).status_code, 401)
        self.assertEqual(self.client.post(f"{BASE}/clarifications", json=body, headers=ADMIN_HEADERS).status_code, 401)
        clarification_id, entry_id = self.confirm(body)
        again = self.client.post(f"{BASE}/clarifications", json=body, headers=AGENT_HEADERS)
        self.assertEqual(again.json()["id"], clarification_id)
        changed = {**body, "question": "Câu hỏi khác"}
        self.assertEqual(self.client.post(f"{BASE}/clarifications", json=changed, headers=AGENT_HEADERS).status_code,
                         409)
        answer_again = self.client.post(f"{BASE}/clarifications/{clarification_id}/answer", json={
            "user_id": "alice", "state": "confirmed",
            "answers": [{"proposal_id": again.json()["proposals"][0]["id"], "option_index": 0}],
        }, headers=AGENT_HEADERS)
        self.assertEqual(answer_again.status_code, 200)
        repeated = {**body, "idempotency_key": "turn-2", "source_question_id": "question-2"}
        _, repeated_entry_id = self.confirm(repeated, option_index=1)
        self.assertEqual(repeated_entry_id, entry_id)
        retry_old = self.client.post(f"{BASE}/clarifications/{clarification_id}/answer", json={
            "user_id": "alice", "state": "confirmed",
            "answers": [{"proposal_id": again.json()["proposals"][0]["id"], "option_index": 0}],
        }, headers=AGENT_HEADERS)
        self.assertEqual([entry["id"] for entry in retry_old.json()["entries"]], [entry_id])
        self.assertEqual(self.client.post(f"{BASE}/clarifications/{clarification_id}/answer", json={
            "user_id": "alice", "state": "dismissed", "answers": [],
        }, headers=AGENT_HEADERS).status_code, 409)
        self.assertEqual(self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "bob",
        }, headers=AGENT_HEADERS).json(), [])
        own = self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "alice",
        }, headers=AGENT_HEADERS)
        self.assertEqual([item["id"] for item in own.json()], [entry_id])
        self.assertEqual(own.json()[0]["definition"], "Lượng mưa vượt 70 mm")
        self.assertEqual(self.client.put(f"{BASE}/agent/entries/{entry_id}", json={
            "user_id": "bob", "expected_version": 1, "name": "Mưa lớn", "definition": "Sai",
        }, headers=AGENT_HEADERS).status_code, 404)

    def test_admin_keep_own_and_promote_glossary_draft(self) -> None:
        _, entry_id = self.confirm(self.push_body())
        self.assertEqual(self.client.get(f"{BASE}/admin/entries", headers=AGENT_HEADERS).status_code, 401)
        review = self.client.post(f"{BASE}/admin/entries/{entry_id}/review", json={
            "expected_version": 1, "action": "keep_own", "reviewer_id": "admin-1", "note": "Ngưỡng cá nhân",
        }, headers=ADMIN_HEADERS)
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["review_status"], "kept_own")
        self.assertTrue(review.json()["active_for_agent"])
        self.assertEqual(self.client.post(f"{BASE}/admin/entries/{entry_id}/review", json={
            "expected_version": 1, "action": "reopen", "reviewer_id": "admin-1",
        }, headers=ADMIN_HEADERS).status_code, 409)
        promoted = self.client.post(f"{BASE}/admin/entries/{entry_id}/promote", json={
            "expected_version": 2, "target_kind": "glossary", "reviewer_id": "admin-1",
            "payload": {
                "canonical_name": "Mưa lớn", "definition": "Lượng mưa ngày vượt 50 mm",
                "links": [{"kind": "table", "id": str(self.table_id)}],
            },
        }, headers=ADMIN_HEADERS)
        self.assertEqual(promoted.status_code, 200, promoted.text)
        target_id = promoted.json()["target"]["id"]
        self.assertEqual(promoted.json()["target"]["current"]["status"], "draft")
        self.assertTrue(promoted.json()["entry"]["active_for_agent"])
        self.assertEqual(self.client.post(f"{GLOSSARY}/{target_id}/approve", json={"expected_revision": 1})
                         .status_code, 200)
        own = self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "alice",
        }, headers=AGENT_HEADERS)
        self.assertEqual(own.json(), [])
        self.assertEqual(self.client.post(f"{GLOSSARY}/{target_id}/revoke", json={"expected_revision": 1})
                         .status_code, 200)
        own_after_revoke = self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "alice",
        }, headers=AGENT_HEADERS)
        self.assertEqual([item["id"] for item in own_after_revoke.json()], [entry_id])

    def test_promote_metric_and_rule_requires_explicit_valid_payload(self) -> None:
        _, metric_entry_id = self.confirm(self.push_body("metric", "Tổng mưa"))
        invalid = self.client.post(f"{BASE}/admin/entries/{metric_entry_id}/promote", json={
            "expected_version": 1, "target_kind": "metric", "reviewer_id": "admin-1",
            "payload": {"name": "rain_total"},
        }, headers=ADMIN_HEADERS)
        self.assertEqual(invalid.status_code, 400)
        promoted_metric = self.client.post(f"{BASE}/admin/entries/{metric_entry_id}/promote", json={
            "expected_version": 1, "target_kind": "metric", "reviewer_id": "admin-1",
            "payload": {"table_id": str(self.table_id), "name": "rain_total", "expression": "SUM(rain_mm)"},
        }, headers=ADMIN_HEADERS)
        self.assertEqual(promoted_metric.status_code, 200, promoted_metric.text)
        self.assertFalse(promoted_metric.json()["entry"]["active_for_agent"])

        glossary = self.client.post(GLOSSARY, json={
            "connection_id": str(self.connection_id), "canonical_name": "Mưa lớn",
            "definition": "Trên 50 mm", "links": [{"kind": "table", "id": str(self.table_id)}],
        })
        self.assertEqual(glossary.status_code, 201, glossary.text)
        term_id = glossary.json()["id"]
        self.assertEqual(self.client.post(f"{GLOSSARY}/{term_id}/approve", json={"expected_revision": 1})
                         .status_code, 200)
        _, rule_entry_id = self.confirm(self.push_body("expert_rule", "Cảnh báo mưa"))
        promoted_rule = self.client.post(f"{BASE}/admin/entries/{rule_entry_id}/promote", json={
            "expected_version": 1, "target_kind": "expert_rule", "reviewer_id": "admin-1",
            "payload": {
                "table_id": str(self.table_id), "name": "Cảnh báo mưa",
                "conditions": [{
                    "column_id": str(self.column_id), "operator": "greater_than", "value_type": "number",
                    "value": 50,
                }],
                "glossary_term_ids": [term_id], "metric_ids": [promoted_metric.json()["target"]["id"]],
            },
        }, headers=ADMIN_HEADERS)
        self.assertEqual(promoted_rule.status_code, 200, promoted_rule.text)
        self.assertTrue(promoted_rule.json()["entry"]["active_for_agent"])
        rule_id = promoted_rule.json()["target"]["id"]
        self.assertEqual(self.client.post(f"{RULES}/{rule_id}/approve", json={"expected_revision": 1}).status_code,
                         200)
        own = self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "alice",
        }, headers=AGENT_HEADERS)
        self.assertEqual(own.json(), [])

    def test_owner_edit_reopens_review_and_owner_delete(self) -> None:
        _, entry_id = self.confirm(self.push_body())
        reviewed = self.client.post(f"{BASE}/admin/entries/{entry_id}/review", json={
            "expected_version": 1, "action": "keep_own", "reviewer_id": "admin-1",
        }, headers=ADMIN_HEADERS)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        edited = self.client.put(f"{BASE}/agent/entries/{entry_id}", json={
            "user_id": "alice", "expected_version": 2, "name": "  Mưa  rất lớn  ",
            "concept": "mưa cực đoan", "definition": "Trên 70 mm",
        }, headers=AGENT_HEADERS)
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["name"], "Mưa rất lớn")
        self.assertEqual(edited.json()["review_status"], "pending")
        self.assertIsNone(edited.json()["reviewed_by"])
        self.assertEqual(edited.json()["version"], 3)
        self.assertEqual(self.client.put(f"{BASE}/agent/entries/{entry_id}", json={
            "user_id": "alice", "expected_version": 2, "name": "Mưa lớn", "definition": "Sai",
        }, headers=AGENT_HEADERS).status_code, 409)
        self.assertEqual(self.client.delete(f"{BASE}/agent/entries/{entry_id}", params={"user_id": "bob"},
                                            headers=AGENT_HEADERS).status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/agent/entries/{entry_id}", params={"user_id": "alice"},
                                            headers=AGENT_HEADERS).status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/admin/entries/{entry_id}", headers=ADMIN_HEADERS).status_code, 404)

    def test_dismissal_and_migration(self) -> None:
        body = self.push_body(user_id="bob")
        pushed = self.client.post(f"{BASE}/clarifications", json=body, headers=AGENT_HEADERS)
        self.assertEqual(pushed.status_code, 201)
        clarification_id = pushed.json()["id"]
        self.assertEqual(self.client.post(f"{BASE}/clarifications/{clarification_id}/answer", json={
            "user_id": "bob", "state": "dismissed", "answers": [],
        }, headers=AGENT_HEADERS).status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/agent/entries", params={
            "connection_id": str(self.connection_id), "user_id": "bob",
        }, headers=AGENT_HEADERS).json(), [])

        migration = import_module(
            "backend.migrations.versions.init_own_knowledge_module.c6a8e2f41d90_create_own_knowledge"
        )
        with self.engine.begin() as connection:
            for table in ("own_knowledge_entries", "own_knowledge_proposals", "own_knowledge_clarifications"):
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
            context = MigrationContext.configure(connection, opts={
                "include_object": lambda obj, name, type_, reflected, compare_to: getattr(obj, "schema", None) != TECHNICAL_SCHEMA
            })
            with Operations.context(context):
                migration.upgrade()
            self.assertTrue({
                "own_knowledge_entries", "own_knowledge_proposals", "own_knowledge_clarifications",
            } <= set(inspect(connection).get_table_names()))
            self.assertEqual(compare_metadata(context, Base.metadata), [])
            with Operations.context(context):
                migration.downgrade()
            self.assertFalse({
                "own_knowledge_entries", "own_knowledge_proposals", "own_knowledge_clarifications",
            } & set(inspect(connection).get_table_names()))


if __name__ == "__main__":
    unittest.main()
