import unittest
from importlib import import_module
from unittest.mock import patch

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.database_connection.models import (
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.metric_management.dependencies import get_metric_service
from backend.modules.metric_management.services import MetricService
from backend.modules.metric_management.services.superset_client import (
    SupersetClient,
    SupersetSnapshot,
)
from backend.modules.metric_management.utils.exceptions import (
    InvalidMetricError,
    SupersetUnavailableError,
)

BASE = "/api/v1/metrics"


class MetricManagementApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(
                name="Warehouse", dialect="postgresql", uri_ciphertext="x"
            )
            session.add(connection)
            session.flush()
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            session.add(schema)
            session.flush()
            table = DatabaseTable(
                schema_id=schema.id, name="orders", table_type="TABLE"
            )
            session.add(table)
            session.commit()
            self.connection_id, self.table_id = connection.id, table.id

        def service_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield MetricService(session)

        app.dependency_overrides[get_metric_service] = service_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_manual_crud_and_duplicate_name(self) -> None:
        body = {
            "table_id": str(self.table_id),
            "name": "revenue",
            "expression": "SUM(amount)",
            "label": "Doanh thu",
        }
        created = self.client.post(BASE, json=body)
        self.assertEqual(created.status_code, 201, created.text)
        metric_id = created.json()["id"]
        self.assertEqual(created.json()["origin"], "manual")
        self.assertEqual(self.client.post(BASE, json=body).status_code, 409)
        listed = self.client.get(
            BASE, params={"connection_id": str(self.connection_id)}
        )
        self.assertEqual([row["id"] for row in listed.json()], [metric_id])
        changed = self.client.patch(
            f"{BASE}/{metric_id}", json={"expression": "COUNT(*)"}
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["expression"], "COUNT(*)")
        self.assertEqual(
            self.client.patch(f"{BASE}/{metric_id}", json={"name": None}).status_code,
            400,
        )
        self.assertEqual(self.client.delete(f"{BASE}/{metric_id}").status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/{metric_id}").status_code, 404)

    def test_sync_idempotence_link_and_deactivation(self) -> None:
        snapshot = SupersetSnapshot(
            users=[
                {
                    "id": 7,
                    "username": "analyst",
                    "first_name": "A",
                    "last_name": "B",
                    "email": "a@b.test",
                }
            ],
            databases=[
                {"id": 2, "database_name": "Warehouse", "backend": "postgresql"}
            ],
            datasets=[
                {
                    "id": 5,
                    "database": {"id": 2},
                    "created_by": {"id": 7},
                    "schema": "public",
                    "table_name": "orders",
                    "sql": None,
                    "metrics": [
                        {
                            "id": 11,
                            "metric_name": "revenue",
                            "expression": "SUM(amount)",
                            "verbose_name": "Doanh thu",
                            "description": "Từ Superset",
                            "created_by": {"id": 7},
                        }
                    ],
                }
            ],
        )
        with Session(self.engine) as session:
            service = MetricService(session)
            self.assertEqual(
                service.sync_superset("http://superset", snapshot)["metrics"], 1
            )
            session.commit()
            self.assertEqual(
                service.sync_superset("http://superset", snapshot)["metrics"], 1
            )
            session.commit()

        users = self.client.get(f"{BASE}/superset/users").json()
        databases = self.client.get(f"{BASE}/superset/databases").json()
        self.assertEqual(len(users), 1)
        self.assertEqual(len(databases), 1)
        metric = self.client.get(BASE).json()[0]
        self.assertEqual(metric["source_user_id"], users[0]["id"])
        self.assertEqual(metric["source_dataset_owner_id"], users[0]["id"])
        self.assertIsNone(metric["table_id"])
        linked = self.client.put(
            f"{BASE}/superset/databases/{databases[0]['id']}/link",
            json={"connection_id": str(self.connection_id)},
        )
        self.assertEqual(linked.status_code, 200, linked.text)
        metric = self.client.get(BASE).json()[0]
        self.assertEqual(metric["table_id"], str(self.table_id))
        self.assertEqual(
            self.client.patch(f"{BASE}/{metric['id']}", json={"name": "x"}).status_code,
            409,
        )
        self.assertEqual(self.client.delete(f"{BASE}/{metric['id']}").status_code, 409)

        with Session(self.engine) as session:
            service = MetricService(session)
            empty = SupersetSnapshot(
                snapshot.users,
                snapshot.databases,
                [{**snapshot.datasets[0], "metrics": []}],
            )
            self.assertEqual(
                service.sync_superset("http://superset", empty)["deactivated"], 1
            )
            session.commit()
        self.assertFalse(self.client.get(f"{BASE}/{metric['id']}").json()["is_active"])

    def test_failed_sync_does_not_modify_existing_metrics(self) -> None:
        with Session(self.engine) as session:
            service = MetricService(session)
            service.create_metric(
                {
                    "table_id": self.table_id,
                    "name": "revenue",
                    "expression": "SUM(amount)",
                }
            )
            session.commit()
            bad = SupersetSnapshot(
                [],
                [{"id": 2, "database_name": "Warehouse"}],
                [
                    {
                        "id": 5,
                        "database": 2,
                        "table_name": "orders",
                        "metrics": [{"id": 11, "metric_name": "bad"}],
                    }
                ],
            )
            with self.assertRaises(InvalidMetricError):
                service.sync_superset("http://superset", bad)
            session.rollback()
        self.assertEqual(len(self.client.get(BASE).json()), 1)
        self.assertEqual(self.client.get(f"{BASE}/superset/databases").json(), [])

    def test_sync_endpoint_requires_configuration(self) -> None:
        with patch(
            "backend.modules.metric_management.routes.router_metric.config"
        ) as config:
            config.superset_url = None
            self.assertEqual(self.client.post(f"{BASE}/superset/sync").status_code, 400)

    def test_sync_endpoint_commits_snapshot(self) -> None:
        snapshot = SupersetSnapshot(
            users=[{"id": 7, "username": "analyst"}],
            databases=[
                {"id": 2, "database_name": "Warehouse", "backend": "postgresql"}
            ],
            datasets=[
                {
                    "id": 5,
                    "database": 2,
                    "table_name": "orders",
                    "schema": "public",
                    "metrics": [
                        {
                            "id": 11,
                            "metric_name": "count_orders",
                            "expression": "COUNT(*)",
                        }
                    ],
                }
            ],
        )
        with (
            patch(
                "backend.modules.metric_management.routes.router_metric.config"
            ) as config,
            patch.object(SupersetClient, "fetch_snapshot", return_value=snapshot),
        ):
            config.superset_url = "http://superset"
            config.superset_username = "admin"
            config.superset_password.get_secret_value.return_value = "secret"
            response = self.client.post(f"{BASE}/superset/sync")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {"users": 1, "databases": 1, "metrics": 1, "deactivated": 0},
        )
        self.assertEqual(len(self.client.get(BASE).json()), 1)

    def test_superset_client_reads_all_pages_and_dataset_details(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            if request.url.path.endswith("/security/login"):
                return httpx.Response(200, json={"access_token": "test-token"})
            self.assertEqual(request.headers.get("authorization"), "Bearer test-token")
            if request.url.path.endswith("/security/users/"):
                return httpx.Response(
                    200, json={"count": 1, "result": [{"id": 7, "username": "analyst"}]}
                )
            if request.url.path.endswith("/database/"):
                return httpx.Response(
                    200,
                    json={
                        "count": 1,
                        "result": [{"id": 2, "database_name": "Warehouse"}],
                    },
                )
            if request.url.path.endswith("/dataset/"):
                return httpx.Response(200, json={"count": 1, "result": [{"id": 5}]})
            if request.url.path.endswith("/dataset/5"):
                return httpx.Response(
                    200, json={"result": {"id": 5, "metrics": [{"id": 11}]}}
                )
            raise AssertionError(request.url.path)

        original_client = httpx.Client
        with patch(
            "backend.modules.metric_management.services.superset_client.httpx.Client",
            side_effect=lambda **kwargs: original_client(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        ):
            snapshot = SupersetClient(
                "http://superset/", "admin", "secret"
            ).fetch_snapshot()
        self.assertEqual(snapshot.datasets[0]["metrics"][0]["id"], 11)
        self.assertEqual(len(paths), 5)

    def test_superset_client_fails_closed_on_incomplete_snapshot(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/security/login"):
                return httpx.Response(200, json={"access_token": "token"})
            return httpx.Response(403)

        original_client = httpx.Client
        with (
            patch(
                "backend.modules.metric_management.services.superset_client.httpx.Client",
                side_effect=lambda **kwargs: original_client(
                    transport=httpx.MockTransport(handler), **kwargs
                ),
            ),
            self.assertRaises(SupersetUnavailableError),
        ):
            SupersetClient("http://superset", "admin", "secret").fetch_snapshot()

    def test_migration_upgrade_and_downgrade(self) -> None:
        migration = import_module(
            "backend.migrations.versions.init_metric_management_module.f6c1a2d937e4_create_metric_management"
        )
        with self.engine.begin() as connection:
            for table in ("metrics", "superset_databases", "superset_users"):
                Base.metadata.tables[table].drop(connection)
            operations = Operations(MigrationContext.configure(connection))
            with patch.object(migration, "op", operations):
                migration.upgrade()
                self.assertTrue(
                    {"metrics", "superset_databases", "superset_users"}
                    <= set(inspect(connection).get_table_names())
                )
                migration.downgrade()
                self.assertFalse(
                    {"metrics", "superset_databases", "superset_users"}
                    & set(inspect(connection).get_table_names())
                )
