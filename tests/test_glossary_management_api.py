import unittest
from importlib import import_module
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.business_model.models import BusinessDomain
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.glossary_management.dependencies import get_glossary_service
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric

BASE = "/api/v1/glossary"


class GlossaryManagementApiTests(unittest.TestCase):
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
            table = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE")
            other_table = DatabaseTable(schema_id=other_schema.id, name="orders", table_type="TABLE")
            session.add_all([table, other_table])
            session.flush()
            column = DatabaseColumn(
                table_id=table.id, name="amount", data_type="numeric", ordinal_position=1, is_nullable=False
            )
            metric = Metric(table_id=table.id, name="revenue", expression="SUM(amount)")
            sales, revenue = BusinessDomain(name="Kinh doanh"), BusinessDomain(name="Doanh số")
            session.add_all([column, metric, sales, revenue])
            session.commit()
            self.sales_id, self.revenue_id = sales.id, revenue.id
            self.connection_id, self.other_id = connection.id, other.id
            self.table_id, self.other_table_id = table.id, other_table.id
            self.column_id, self.metric_id = column.id, metric.id

        def service_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield GlossaryService(session)

        app.dependency_overrides[get_glossary_service] = service_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def body(self) -> dict:
        return {
            "connection_id": str(self.connection_id),
            "canonical_name": "Doanh thu",
            "definition": "Tổng giá trị đơn hàng",
            "synonyms": ["Revenue"], "business_domain_ids": [str(self.sales_id)],
            "links": [
                {"kind": "table", "id": str(self.table_id)},
                {"kind": "column", "id": str(self.column_id)},
                {"kind": "metric", "id": str(self.metric_id)},
            ],
        }

    def test_create_edit_approve_discover_revoke_delete(self) -> None:
        created = self.client.post(BASE, json=self.body())
        self.assertEqual(created.status_code, 201, created.text)
        term_id = created.json()["id"]
        self.assertEqual(created.json()["current"]["status"], "draft")
        duplicate = self.client.post(BASE, json={**self.body(), "canonical_name": " doanh  THU "})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)}).json(),
            {"terms": []},
        )

        approved = self.client.post(f"{BASE}/{term_id}/approve", json={"expected_revision": 1})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["serving"]["definition"], "Tổng giá trị đơn hàng")
        self.assertEqual(len(self.client.get(f"{BASE}/{term_id}/revisions").json()), 1)
        edit = self.client.put(f"{BASE}/{term_id}/draft", json={
            "expected_revision": 1, "definition": "Doanh thu thuần", "synonyms": ["Sales"],
            "business_domain_ids": [str(self.sales_id)], "links": [{"kind": "metric", "id": str(self.metric_id)}],
        })
        self.assertEqual(edit.status_code, 200, edit.text)
        self.assertEqual(edit.json()["current"]["number"], 2)
        self.assertEqual(edit.json()["serving"]["definition"], "Tổng giá trị đơn hàng")
        self.assertEqual(self.client.post(f"{BASE}/{term_id}/approve", json={"expected_revision": 1}).status_code, 409)
        self.assertEqual(self.client.post(f"{BASE}/{term_id}/approve", json={"expected_revision": 2}).status_code, 200)
        discovery = self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)}).json()
        self.assertEqual(discovery["terms"][0]["definition"], "Doanh thu thuần")
        revoked = self.client.post(f"{BASE}/{term_id}/revoke", json={"expected_revision": 2})
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertIsNone(revoked.json()["serving"])
        self.assertEqual(
            self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)}).json(),
            {"terms": []},
        )
        self.assertEqual(self.client.delete(f"{BASE}/{term_id}").status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/{term_id}").status_code, 404)

    def test_scope_and_link_validation(self) -> None:
        body = self.body()
        body["links"] = [{"kind": "table", "id": str(self.other_table_id)}]
        self.assertEqual(self.client.post(BASE, json=body).status_code, 400)
        body["links"] = [{"kind": "metric", "id": str(uuid4())}]
        self.assertEqual(self.client.post(BASE, json=body).status_code, 400)
        body["links"] = []
        body["synonyms"] = ["Doanh thu"]
        self.assertEqual(self.client.post(BASE, json=body).status_code, 400)
        self.assertEqual(self.client.post(BASE, json={**self.body(), "business_domain_ids": [str(uuid4())]}).status_code, 400)
        self.assertEqual(self.client.get(BASE, params={"connection_id": str(self.other_id)}).json(), [])

    def test_metric_can_be_shared_and_discovery_filters_inactive_link(self) -> None:
        first = self.client.post(BASE, json=self.body()).json()
        second_body = {**self.body(), "canonical_name": "Giá trị bán hàng", "synonyms": []}
        second = self.client.post(BASE, json=second_body)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(self.client.post(f"{BASE}/{first['id']}/approve", json={"expected_revision": 1}).status_code,
                         200)
        self.assertEqual(self.client.post(f"{BASE}/{second.json()['id']}/approve", json={"expected_revision": 1})
                         .status_code, 200)
        no_change = self.client.put(f"{BASE}/{first['id']}/draft", json={
            "expected_revision": 1, "definition": first["current"]["definition"],
            "synonyms": first["current"]["synonyms"], "links": first["current"]["links"],
            "business_domain_ids": [str(self.sales_id), str(self.revenue_id), str(self.sales_id)],
        })
        self.assertEqual(no_change.json()["current"]["number"], 1)
        self.assertEqual([domain["name"] for domain in no_change.json()["business_domains"]], ["Doanh số", "Kinh doanh"])
        with Session(self.engine) as session:
            metric = session.get(Metric, self.metric_id)
            metric.is_active = False
            session.commit()
        terms = self.client.get(f"{BASE}/discovery", params={"connection_id": str(self.connection_id)}).json()["terms"]
        self.assertEqual(len(terms), 2)
        self.assertTrue(all(not any(link["kind"] == "metric" for link in term["links"]) for term in terms))

    def test_migration_upgrade_and_downgrade(self) -> None:
        migration = import_module(
            "backend.migrations.versions.init_glossary_management_module.a8e12c7f94b3_create_glossary_management"
        )
        with self.engine.begin() as connection:
            # The API fixture already has referenced tables, but not a recorded Alembic revision.
            for table in (
                "expert_rule_metric_links", "expert_rule_glossary_links", "expert_rule_revisions", "expert_rules",
            ):
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
            for table in ("glossary_links", "glossary_revisions", "glossary_terms"):
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
            self.assertEqual(
                {"glossary_terms", "glossary_revisions", "glossary_links"} - set(inspect(connection).get_table_names()),
                set(),
            )
            with Operations.context(context):
                migration.downgrade()
            self.assertFalse({"glossary_terms", "glossary_revisions", "glossary_links"} &
                             set(inspect(connection).get_table_names()))

    def test_business_domain_migration_round_trip(self) -> None:
        migration = import_module(
            "backend.migrations.versions.init_glossary_management_module.e2a7c4d91f36_glossary_term_business_domains"
        )
        term_id = self.client.post(BASE, json={
            **self.body(), "business_domain_ids": [str(self.sales_id), str(self.revenue_id)],
        }).json()["id"]
        with self.engine.connect() as connection:
            # SQLite batch mode rebuilds glossary_terms; with foreign keys on, that would cascade to its revisions.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.downgrade()
            self.assertNotIn("glossary_term_domains", inspect(connection).get_table_names())
            self.assertEqual(
                connection.exec_driver_sql("SELECT group_name FROM glossary_terms").scalar(), "Doanh số"
            )
            connection.exec_driver_sql("UPDATE glossary_terms SET group_name = ' kinh DOANH '")
            with Operations.context(context):
                migration.upgrade()
            self.assertNotIn("group_name", {column["name"] for column in inspect(connection).get_columns("glossary_terms")})
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        domains = self.client.get(f"{BASE}/{term_id}").json()["business_domains"]
        self.assertEqual([domain["name"] for domain in domains], ["Kinh doanh"])


if __name__ == "__main__":
    unittest.main()
