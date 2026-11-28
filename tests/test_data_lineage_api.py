import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.business_model.models import LineageEdge
from backend.modules.data_dictionary.models import TableDictionary
from backend.modules.data_lineage.dependencies import get_data_lineage_service
from backend.modules.data_lineage.services import DataLineageService
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from tests.service_key import use_service_key

BASE = "/api/v1/data-lineage"


class DataLineageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x", is_active=True)
            other = DatabaseConnection(name="Other", dialect="postgresql", uri_ciphertext="y", is_active=True)
            session.add_all([connection, other])
            session.flush()
            self.connection_id, self.other_id = connection.id, other.id
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            other_schema = DatabaseSchema(connection_id=other.id, name="public")
            session.add_all([schema, other_schema])
            session.flush()
            orders = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE")
            payments = DatabaseTable(schema_id=schema.id, name="payments", table_type="TABLE")
            summary = DatabaseTable(schema_id=schema.id, name="monthly_revenue", table_type="VIEW")
            outside = DatabaseTable(schema_id=other_schema.id, name="outside", table_type="TABLE")
            session.add_all([orders, payments, summary, outside])
            session.flush()
            self.tables = {row.name: row.id for row in (orders, payments, summary, outside)}
            definitions = {
                "orders": ["id", "created_at"],
                "payments": ["order_id", "amount", "status"],
                "monthly_revenue": ["month", "total"],
                "outside": ["id"],
            }
            self.columns: dict[str, UUID] = {}
            for table in (orders, payments, summary, outside):
                for index, name in enumerate(definitions[table.name], start=1):
                    column = DatabaseColumn(
                        table_id=table.id, name=name, data_type="TEXT", ordinal_position=index,
                        is_nullable=True, is_primary_key=False,
                    )
                    session.add(column)
                    session.flush()
                    self.columns[f"{table.name}.{name}"] = column.id
            session.commit()

        def lineage_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield DataLineageService(session)

        app.dependency_overrides[get_data_lineage_service] = lineage_dependency
        self.client = TestClient(app, headers=use_service_key(self), raise_server_exceptions=True)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_preview_confirm_graph_and_scope(self) -> None:
        sql = (
            "SELECT date_trunc('month', o.created_at) AS month, SUM(p.amount) AS total "
            "FROM public.orders o JOIN public.payments p ON p.order_id = o.id "
            "WHERE p.status = 'paid' GROUP BY date_trunc('month', o.created_at)"
        )
        preview = self.client.post(f"{BASE}/connections/{self.connection_id}/preview", json={
            "target_table_id": str(self.tables["monthly_revenue"]), "sql_text": sql,
        })
        self.assertEqual(preview.status_code, 200, preview.text)
        suggestions = preview.json()
        self.assertTrue(suggestions["complete"])
        self.assertEqual(len(suggestions["source_table_ids"]), 2)
        self.assertEqual({item["role"] for item in suggestions["dependencies"]}, {"value", "group", "join", "filter"})
        self.assertIn({
            "source_column_id": str(self.columns["payments.amount"]),
            "target_column_id": str(self.columns["monthly_revenue.total"]), "role": "value",
        }, suggestions["dependencies"])

        body = {
            "target_table_id": str(self.tables["monthly_revenue"]),
            "name": "Revenue by month", "origin": "sql_job", "sql_text": sql,
            "source_table_ids": suggestions["source_table_ids"],
            "dependencies": suggestions["dependencies"],
        }
        created = self.client.post(f"{BASE}/connections/{self.connection_id}/transformations", json=body)
        self.assertEqual(created.status_code, 201, created.text)
        transformation_id = created.json()["id"]
        self.assertEqual(self.client.post(
            f"{BASE}/connections/{self.connection_id}/transformations", json=body
        ).status_code, 409)
        graph = self.client.get(f"{BASE}/connections/{self.connection_id}/graph")
        self.assertEqual(graph.status_code, 200)
        self.assertEqual(len(graph.json()["edges"]), 2)
        self.assertEqual({edge["kind"] for edge in graph.json()["edges"]}, {"transform"})
        self.assertEqual(len(self.client.get(f"{BASE}/connections/{self.connection_id}/transformations").json()), 1)

        with Session(self.engine) as session:
            source = TableDictionary(table_id=self.tables["payments"], display_name="Payments", layout="wide")
            target = TableDictionary(table_id=self.tables["monthly_revenue"], display_name="Revenue", layout="wide")
            session.add_all([source, target])
            session.flush()
            session.add(LineageEdge(
                source_table_dictionary_id=source.id, target_table_dictionary_id=target.id,
                kind="flow", is_manual=True, is_hidden=False,
            ))
            session.commit()
        graph = self.client.get(f"{BASE}/connections/{self.connection_id}/graph").json()
        self.assertEqual({edge["kind"] for edge in graph["edges"]}, {"transform", "flow"})

        with Session(self.engine) as session:
            connection = session.get(DatabaseConnection, self.connection_id)
            connection.table_excludes = ["payments"]
            session.commit()
        self.assertEqual(self.client.get(f"{BASE}/connections/{self.connection_id}/transformations").json(), [])
        self.assertEqual(self.client.get(f"{BASE}/connections/{self.connection_id}/graph").json()["edges"], [])
        with Session(self.engine) as session:
            connection = session.get(DatabaseConnection, self.connection_id)
            connection.table_excludes = []
            session.commit()
        invalid_update = {**body, "source_table_ids": [str(self.tables["outside"])]}
        self.assertEqual(self.client.put(
            f"{BASE}/connections/{self.connection_id}/transformations/{transformation_id}",
            json=invalid_update,
        ).status_code, 422)
        self.assertEqual(len(self.client.get(
            f"{BASE}/connections/{self.connection_id}/transformations/{transformation_id}"
        ).json()["source_table_ids"]), 2)
        updated = self.client.put(
            f"{BASE}/connections/{self.connection_id}/transformations/{transformation_id}",
            json={**body, "name": "Revenue from orders", "source_table_ids": [str(self.tables["orders"])],
                  "dependencies": [item for item in suggestions["dependencies"]
                                   if item["source_column_id"] in {
                                       str(self.columns["orders.id"]), str(self.columns["orders.created_at"]),
                                   }]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Revenue from orders")
        self.assertEqual(updated.json()["source_table_ids"], [str(self.tables["orders"])])
        self.assertEqual(self.client.delete(
            f"{BASE}/connections/{self.connection_id}/transformations/{transformation_id}"
        ).status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/connections/{self.connection_id}/transformations").json(), [])

    def test_rejects_cross_connection_and_ambiguous_sql(self) -> None:
        body = {
            "target_table_id": str(self.tables["monthly_revenue"]), "name": "Invalid",
            "source_table_ids": [str(self.tables["outside"])], "dependencies": [],
        }
        self.assertEqual(
            self.client.post(f"{BASE}/connections/{self.connection_id}/transformations", json=body).status_code, 422,
        )
        body["source_table_ids"] = [str(self.tables["orders"])]
        body["dependencies"] = [{
            "source_column_id": str(self.columns["payments.amount"]),
            "target_column_id": str(self.columns["monthly_revenue.total"]), "role": "value",
        }]
        self.assertEqual(
            self.client.post(f"{BASE}/connections/{self.connection_id}/transformations", json=body).status_code, 422,
        )
        preview = self.client.post(f"{BASE}/connections/{self.connection_id}/preview", json={
            "target_table_id": str(self.tables["monthly_revenue"]),
            "sql_text": "SELECT * FROM public.orders o JOIN public.payments p ON p.order_id = o.id",
        })
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["complete"])
        self.assertTrue(preview.json()["warnings"])
        self.assertEqual(self.client.post(f"{BASE}/connections/{self.connection_id}/preview", json={
            "target_table_id": str(self.tables["monthly_revenue"]), "sql_text": "DROP TABLE orders",
        }).status_code, 422)

    def test_reads_view_definition_with_source_role(self) -> None:
        key = Fernet.generate_key()
        with Session(self.engine) as session:
            connection = session.get(DatabaseConnection, self.connection_id)
            connection.uri_ciphertext = Fernet(key).encrypt(
                b"postgresql+psycopg://reader:secret@example.test/source"
            ).decode()
            session.commit()
        engine = MagicMock()
        source = engine.connect.return_value.__enter__.return_value
        source.scalar.return_value = "SELECT amount AS total FROM public.payments"
        with patch("backend.modules.data_lineage.services.lineage_service.create_engine", return_value=engine), \
             patch("backend.modules.data_lineage.services.lineage_service.config") as settings:
            settings.require_connection_encryption_key.return_value = key.decode()
            response = self.client.get(
                f"{BASE}/connections/{self.connection_id}/tables/{self.tables['monthly_revenue']}/view-sql"
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["sql_text"], "SELECT amount AS total FROM public.payments")
        self.assertEqual(source.scalar.call_args.args[1], {
            "schema_name": "public", "table_name": "monthly_revenue",
        })
        self.assertIn("has_table_privilege(current_user", str(source.scalar.call_args.args[0]))
        engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
