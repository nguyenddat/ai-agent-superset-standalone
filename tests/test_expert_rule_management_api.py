import unittest
from importlib import import_module
from uuid import uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import TECHNICAL_SCHEMA, Base
from backend.main import app
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.dependencies import get_expert_rule_service
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.dependencies import get_glossary_service
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric

BASE = "/api/v1/expert-rules"
GLOSSARY = "/api/v1/glossary"


class ExpertRuleManagementApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x")
            other = DatabaseConnection(name="Other", dialect="postgresql", uri_ciphertext="y")
            session.add_all([connection, other])
            session.flush()
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            other_schema = DatabaseSchema(connection_id=other.id, name="public")
            session.add_all([schema, other_schema])
            session.flush()
            table = DatabaseTable(schema_id=schema.id, name="weather", table_type="TABLE")
            other_table = DatabaseTable(schema_id=other_schema.id, name="weather", table_type="TABLE")
            session.add_all([table, other_table])
            session.flush()
            column = DatabaseColumn(
                table_id=table.id, name="rain_mm", data_type="numeric", ordinal_position=1, is_nullable=False,
            )
            other_column = DatabaseColumn(
                table_id=other_table.id, name="rain_mm", data_type="numeric", ordinal_position=1, is_nullable=False,
            )
            metric = Metric(table_id=table.id, name="rain_total", expression="SUM(rain_mm)")
            session.add_all([column, other_column, metric])
            session.commit()
            self.connection_id, self.other_id = connection.id, other.id
            self.table_id, self.other_table_id = table.id, other_table.id
            self.column_id, self.other_column_id, self.metric_id = column.id, other_column.id, metric.id

        def expert_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield ExpertRuleService(session)

        def glossary_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield GlossaryService(session)

        app.dependency_overrides[get_expert_rule_service] = expert_dependency
        app.dependency_overrides[get_glossary_service] = glossary_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def create_glossary(self, name: str = "Mưa lớn") -> str:
        created = self.client.post(GLOSSARY, json={
            "connection_id": str(self.connection_id), "canonical_name": name,
            "definition": "Lượng mưa vượt ngưỡng", "synonyms": [],
            "links": [
                {"kind": "table", "id": str(self.table_id)},
                {"kind": "metric", "id": str(self.metric_id)},
            ],
        })
        self.assertEqual(created.status_code, 201, created.text)
        term_id = created.json()["id"]
        approved = self.client.post(f"{GLOSSARY}/{term_id}/approve", json={"expected_revision": 1})
        self.assertEqual(approved.status_code, 200, approved.text)
        return term_id

    def body(self, term_ids: list[str]) -> dict:
        return {
            "connection_id": str(self.connection_id), "table_id": str(self.table_id),
            "name": "Cảnh báo mưa lớn", "group_name": "Thời tiết", "description": "Xác định ngày mưa lớn",
            "conditions": [{
                "column_id": str(self.column_id), "operator": "greater_than",
                "value_type": "number", "value": 50,
            }],
            "exceptions": [{"when": "Vùng núi", "outcome": "Ngưỡng 70 mm"}],
            "examples": [{"question": "Hôm nay mưa lớn không?", "intent": "Mưa > 50 mm"}],
            "glossary_term_ids": term_ids, "metric_ids": [str(self.metric_id)],
        }

    def test_lifecycle_and_many_to_many_links(self) -> None:
        first = self.create_glossary()
        second = self.create_glossary("Lượng mưa")
        body = self.body([first, second])
        created = self.client.post(BASE, json=body)
        self.assertEqual(created.status_code, 201, created.text)
        rule_id = created.json()["id"]
        self.assertEqual(set(created.json()["current"]["glossary_term_ids"]), {first, second})
        self.assertEqual(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                         .json(), {"rules": []})
        self.assertEqual(self.client.post(BASE, json=body).status_code, 409)
        approved = self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 1})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(len(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                             .json()["rules"]), 1)
        edit = self.client.put(f"{BASE}/{rule_id}/draft", json={
            **{k: v for k, v in body.items() if k not in ("connection_id", "table_id", "name")},
            "expected_revision": 1, "description": "Ngưỡng cập nhật",
        })
        self.assertEqual(edit.status_code, 200, edit.text)
        self.assertEqual(edit.json()["current"]["number"], 2)
        self.assertEqual(edit.json()["serving"]["description"], "Xác định ngày mưa lớn")
        self.assertEqual(self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 1}).status_code, 409)
        self.assertEqual(self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 2}).status_code, 200)
        self.assertEqual(len(self.client.get(f"{BASE}/{rule_id}/revisions").json()), 2)
        revoked = self.client.post(f"{BASE}/{rule_id}/revoke", json={"expected_revision": 2})
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertIsNone(revoked.json()["serving"])
        self.assertEqual(self.client.delete(f"{BASE}/{rule_id}").status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/{rule_id}").status_code, 404)

    def test_validation_and_stale_dependencies(self) -> None:
        term_id = self.create_glossary()
        body = self.body([term_id])
        bad = self.client.post(BASE, json={**body, "conditions": [{
            "column_id": str(self.other_column_id), "operator": "equals", "value_type": "number", "value": 1,
        }]})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "table_id": str(self.other_table_id)}).status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "glossary_term_ids": [str(uuid4())]}).status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "metric_ids": [str(uuid4())]}).status_code, 400)
        duplicate_terms = self.client.post(BASE, json={**body, "glossary_term_ids": [term_id, term_id]})
        self.assertEqual(duplicate_terms.status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**body, "conditions": [{
            "column_id": str(self.column_id), "operator": "greater_than", "value_type": "string", "value": "50",
        }]}).status_code, 422)
        created = self.client.post(BASE, json=body)
        self.assertEqual(created.status_code, 201, created.text)
        rule_id = created.json()["id"]
        self.assertEqual(self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 1}).status_code, 200)
        self.assertEqual(len(self.client.get(f"{BASE}/options", params={"connection_id": str(self.connection_id)})
                             .json()["tables"][0]["glossary_terms"]), 1)
        changed = self.client.put(f"{GLOSSARY}/{term_id}/draft", json={
            "expected_revision": 1, "definition": "Định nghĩa mới", "synonyms": [],
            "links": [{"kind": "table", "id": str(self.table_id)}],
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(len(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                             .json()["rules"]), 1)
        self.assertEqual(self.client.post(f"{GLOSSARY}/{term_id}/approve", json={"expected_revision": 2}).status_code,
                         200)
        self.assertEqual(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                         .json(), {"rules": []})
        refresh_body = {
            **{key: value for key, value in body.items() if key not in ("connection_id", "table_id", "name")},
            "expected_revision": 1,
        }
        refreshed = self.client.put(f"{BASE}/{rule_id}/draft", json=refresh_body)
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()["current"]["number"], 2)
        self.assertEqual(self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 2}).status_code, 200)
        with Session(self.engine) as session:
            metric = session.get(Metric, self.metric_id)
            metric.expression = "AVG(rain_mm)"
            session.commit()
        self.assertEqual(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                         .json(), {"rules": []})
        refreshed_metric = self.client.put(f"{BASE}/{rule_id}/draft", json={**refresh_body, "expected_revision": 2})
        self.assertEqual(refreshed_metric.json()["current"]["number"], 3)
        self.assertEqual(self.client.post(f"{BASE}/{rule_id}/approve", json={"expected_revision": 3}).status_code, 200)
        self.assertEqual(len(self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)})
                             .json()["rules"]), 1)

    def test_migration_upgrade_and_downgrade(self) -> None:
        migration = import_module(
            "backend.migrations.versions.init_expert_rule_management_module."
            "b9f4d7a2c183_create_expert_rule_management"
        )
        tables = (
            "expert_rule_metric_links", "expert_rule_glossary_links", "expert_rule_revisions", "expert_rules",
        )
        with self.engine.begin() as connection:
            for table in tables:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
            context = MigrationContext.configure(connection, opts={
                "include_object": lambda obj, name, type_, reflected, compare_to: getattr(obj, "schema", None) != TECHNICAL_SCHEMA
            })
            with Operations.context(context):
                migration.upgrade()
            self.assertTrue(set(tables) <= set(inspect(connection).get_table_names()))
            self.assertEqual(compare_metadata(context, Base.metadata), [])
            with Operations.context(context):
                migration.downgrade()
            self.assertFalse(set(tables) & set(inspect(connection).get_table_names()))


if __name__ == "__main__":
    unittest.main()
