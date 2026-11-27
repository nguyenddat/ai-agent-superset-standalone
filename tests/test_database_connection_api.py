import unittest
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.database_connection.dependencies import get_connection_service, get_metadata_service
from backend.modules.database_connection.services import ConnectionService, MetadataService
from backend.modules.database_connection.services.metadata_service import SourceColumn, SourceSchema, SourceTable

BASE = "/api/v1"
URI = "postgresql+psycopg://reader:secret@db.example.test:5432/source"


class DatabaseConnectionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.key = Fernet.generate_key().decode()
        self.snapshot = [SourceSchema("public", (
            SourceTable("orders", "TABLE", "Customer orders", (
                SourceColumn("id", "INTEGER", 1, False, True, None, None),
            )),
        ))]

        def connection_dependency():
            with Session(self.engine) as session:
                yield ConnectionService(session, encryption_key=self.key, probe=lambda _url: None)

        def metadata_dependency():
            with Session(self.engine) as session:
                yield MetadataService(session, encryption_key=self.key, scanner=lambda _url: self.snapshot)

        app.dependency_overrides[get_connection_service] = connection_dependency
        app.dependency_overrides[get_metadata_service] = metadata_dependency
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_connection_lifecycle_and_metadata_routes(self) -> None:
        self.assertEqual(self.client.get(f"{BASE}/database-connections").json(), [])
        dialects = self.client.get(f"{BASE}/database-connections/dialects")
        self.assertEqual(dialects.status_code, 200)
        self.assertEqual(dialects.json()[0]["dialect"], "postgresql")

        tested = self.client.post(f"{BASE}/database-connections/test", json={
            "dialect": "postgresql", "driver": "psycopg", "uri": URI,
        })
        self.assertEqual(tested.status_code, 200)
        self.assertTrue(tested.json()["ok"])

        created = self.client.post(f"{BASE}/database-connections", json={
            "name": "Primary", "dialect": "postgresql", "driver": "psycopg", "uri": URI,
        })
        self.assertEqual(created.status_code, 201)
        connection_id = created.json()["id"]
        self.assertEqual(set(created.json()), {
            "id", "name", "dialect", "driver", "is_active", "created_at", "updated_at",
            "schema_includes", "schema_excludes", "table_includes", "table_excludes",
        })
        self.assertNotIn("secret", created.text)
        self.assertEqual(self.client.get(f"{BASE}/database-connections/{connection_id}").status_code, 200)
        self.assertEqual(len(self.client.get(f"{BASE}/database-connections").json()), 1)

        updated = self.client.patch(f"{BASE}/database-connections/{connection_id}", json={
            "name": "Renamed", "is_active": False, "uri": URI.replace("source", "source2"),
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Renamed")
        self.assertFalse(updated.json()["is_active"])
        self.assertNotIn("secret", updated.text)
        self.assertEqual(self.client.post(f"{BASE}/database-connections/{connection_id}/sync").status_code, 409)

        self.client.patch(f"{BASE}/database-connections/{connection_id}", json={"is_active": True})
        synced = self.client.post(f"{BASE}/database-connections/{connection_id}/sync")
        self.assertEqual(synced.status_code, 200)
        self.assertEqual(synced.json()["status"], "completed")
        self.assertEqual((synced.json()["schema_count"], synced.json()["table_count"],
                          synced.json()["column_count"]), (1, 1, 1))

        schemas = self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
        self.assertEqual(schemas[0]["name"], "public")
        tables = self.client.get(f"{BASE}/schemas/{schemas[0]['id']}/tables").json()
        self.assertEqual(tables[0]["name"], "orders")
        columns = self.client.get(f"{BASE}/tables/{tables[0]['id']}/columns").json()
        self.assertEqual(columns[0]["name"], "id")
        self.assertTrue(columns[0]["is_primary_key"])

        self.snapshot = [SourceSchema("public", (
            SourceTable("orders", "TABLE", "Updated description", (
                SourceColumn("id", "BIGINT", 1, False, True, None, None),
            )),
        ))]
        self.assertEqual(self.client.post(f"{BASE}/database-connections/{connection_id}/sync").status_code, 200)
        updated_tables = self.client.get(f"{BASE}/schemas/{schemas[0]['id']}/tables").json()
        updated_columns = self.client.get(f"{BASE}/tables/{tables[0]['id']}/columns").json()
        self.assertEqual(updated_tables[0]["id"], tables[0]["id"])
        self.assertEqual(updated_tables[0]["description"], "Updated description")
        self.assertEqual(updated_columns[0]["data_type"], "BIGINT")

        self.snapshot = [
            SourceSchema("public", (
                SourceTable("customers", "TABLE", None, (
                    SourceColumn("id", "INTEGER", 1, False, True, None, None),
                    SourceColumn("email", "TEXT", 2, True, False, None, None),
                )),
            )),
            SourceSchema("staging", (
                SourceTable("raw_orders", "VIEW", None, (
                    SourceColumn("payload", "TEXT", 1, True, False, None, None),
                )),
            )),
        ]
        self.assertEqual(self.client.post(f"{BASE}/database-connections/{connection_id}/sync").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/tables/{tables[0]['id']}/columns").status_code, 404)
        public_tables = self.client.get(f"{BASE}/schemas/{schemas[0]['id']}/tables").json()
        self.assertEqual([t["name"] for t in public_tables], ["customers"])
        customer_columns = self.client.get(f"{BASE}/tables/{public_tables[0]['id']}/columns").json()
        self.assertEqual([c["name"] for c in customer_columns], ["id", "email"])

        self.snapshot = [SourceSchema("public", (
            SourceTable("customers", "TABLE", None, (
                SourceColumn("id", "INTEGER", 1, False, True, None, None),
            )),
        ))]
        self.assertEqual(self.client.post(f"{BASE}/database-connections/{connection_id}/sync").status_code, 200)
        remaining_schemas = self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
        self.assertEqual([s["name"] for s in remaining_schemas], ["public"])
        remaining_columns = self.client.get(f"{BASE}/tables/{public_tables[0]['id']}/columns").json()
        self.assertEqual([c["name"] for c in remaining_columns], ["id"])
        self.snapshot = []
        self.assertEqual(self.client.post(f"{BASE}/database-connections/{connection_id}/sync").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json(), [])
        self.assertEqual(self.client.get(f"{BASE}/schemas/{schemas[0]['id']}/tables").status_code, 404)

        self.assertEqual(self.client.delete(f"{BASE}/database-connections/{connection_id}").status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/database-connections/{connection_id}").status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/schemas/{schemas[0]['id']}/tables").status_code, 404)

    def test_errors_and_cors_use_expected_shape(self) -> None:
        invalid = self.client.post(f"{BASE}/database-connections", json={
            "name": "Invalid", "dialect": "postgresql", "uri": "sqlite:///tmp/source.db",
        })
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(set(invalid.json()), {"detail"})

        self.client.post(f"{BASE}/database-connections", json={
            "name": "Duplicate", "dialect": "postgresql", "uri": URI,
        })
        duplicate = self.client.post(f"{BASE}/database-connections", json={
            "name": "Duplicate", "dialect": "postgresql", "uri": URI,
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(set(duplicate.json()), {"detail"})

        invalid_id = self.client.get(f"{BASE}/database-connections/not-a-uuid")
        self.assertEqual(invalid_id.status_code, 422)
        self.assertEqual(set(invalid_id.json()), {"detail"})
        preflight = self.client.options(f"{BASE}/database-connections", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_scope_filters_metadata_without_deleting_existing_dictionary(self) -> None:
        from backend.modules.business_model.services import BusinessModelService
        from backend.modules.data_dictionary.models import TableDictionary
        from backend.modules.data_dictionary.services import DataDictionaryService
        from backend.modules.database_connection.models import DatabaseTable

        self.snapshot = [
            SourceSchema("public", (
                SourceTable("orders", "TABLE", None, (SourceColumn("id", "INTEGER", 1, False, True, None, None),)),
                SourceTable("tmp_orders", "TABLE", None, (SourceColumn("id", "INTEGER", 1, False, True, None, None),)),
            )),
            SourceSchema("staging", (
                SourceTable("raw_orders", "TABLE", None, (SourceColumn("id", "INTEGER", 1, False, True, None, None),)),
            )),
        ]
        created = self.client.post(f"{BASE}/database-connections", json={
            "name": "Scoped", "dialect": "postgresql", "uri": URI,
        })
        connection_id = created.json()["id"]
        self.client.post(f"{BASE}/database-connections/{connection_id}/sync")
        schemas = self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
        public_id = next(schema["id"] for schema in schemas if schema["name"] == "public")
        tables = self.client.get(f"{BASE}/schemas/{public_id}/tables").json()
        tmp_id = UUID(next(table["id"] for table in tables if table["name"] == "tmp_orders"))
        with Session(self.engine) as session:
            session.add(TableDictionary(table_id=tmp_id, display_name="Bảng tạm cần giữ"))
            session.commit()

        changed = self.client.patch(f"{BASE}/database-connections/{connection_id}", json={
            "schema_excludes": ["staging"], "table_includes": ["orders", "tmp_*"],
            "table_excludes": ["tmp_*"],
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        synced = self.client.post(f"{BASE}/database-connections/{connection_id}/sync")
        self.assertEqual((synced.json()["schema_count"], synced.json()["table_count"]), (1, 1))
        self.assertEqual(
            [
                schema["name"]
                for schema in self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
            ],
            ["public"],
        )
        self.assertEqual(
            [table["name"] for table in self.client.get(f"{BASE}/schemas/{public_id}/tables").json()], ["orders"],
        )
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(DatabaseTable, tmp_id))
            kept = session.query(TableDictionary).filter_by(table_id=tmp_id).one()
            self.assertEqual(kept.display_name, "Bảng tạm cần giữ")
            summary = DataDictionaryService(session).get_connection_summary(UUID(connection_id))
            self.assertEqual(summary["table_count"], 1)
            self.assertEqual(len(BusinessModelService(session).get_model(UUID(connection_id))["tables"]), 1)

        self.client.patch(f"{BASE}/database-connections/{connection_id}", json={
            "schema_excludes": [], "table_includes": [], "table_excludes": [],
        })
        restored = self.client.get(f"{BASE}/schemas/{public_id}/tables").json()
        self.assertEqual(next(table["id"] for table in restored if table["name"] == "tmp_orders"), str(tmp_id))
        self.assertEqual(
            [
                schema["name"]
                for schema in self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
            ],
            ["public", "staging"],
        )
        self.client.patch(f"{BASE}/database-connections/{connection_id}", json={
            "schema_includes": ["public"], "table_includes": ["public.orders"],
        })
        self.assertEqual(
            [table["name"] for table in self.client.get(f"{BASE}/schemas/{public_id}/tables").json()], ["orders"],
        )
        self.assertEqual(
            [
                schema["name"]
                for schema in self.client.get(f"{BASE}/database-connections/{connection_id}/schemas").json()
            ],
            ["public"],
        )
        self.assertEqual(self.client.patch(f"{BASE}/database-connections/{connection_id}", json={
            "schema_includes": None,
        }).status_code, 422)


if __name__ == "__main__":
    unittest.main()
