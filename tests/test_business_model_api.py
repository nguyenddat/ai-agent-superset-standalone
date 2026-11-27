import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.business_model.dependencies import get_business_model_service
from backend.modules.business_model.services import BusinessModelService
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)

BASE = "/api/v1/business-model"


class BusinessModelApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Source", dialect="postgresql", uri_ciphertext="x", is_active=True)
            other = DatabaseConnection(name="Other", dialect="postgresql", uri_ciphertext="y", is_active=True)
            session.add_all([connection, other])
            session.flush()
            self.connection_id, self.other_connection_id = connection.id, other.id
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            other_schema = DatabaseSchema(connection_id=other.id, name="public")
            session.add_all([schema, other_schema])
            session.flush()
            source = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE")
            target = DatabaseTable(schema_id=schema.id, name="customers", table_type="TABLE")
            foreign = DatabaseTable(schema_id=other_schema.id, name="elsewhere", table_type="TABLE")
            session.add_all([source, target, foreign])
            session.flush()
            self.source_id, self.target_id, self.foreign_id = source.id, target.id, foreign.id
            reference = DatabaseColumn(
                table_id=source.id, name="customer_id", data_type="BIGINT", ordinal_position=1,
                is_nullable=False, is_primary_key=False,
            )
            identifier = DatabaseColumn(
                table_id=target.id, name="id", data_type="BIGINT", ordinal_position=1,
                is_nullable=False, is_primary_key=True,
            )
            session.add_all([reference, identifier])
            session.flush()
            session.add(ColumnDictionary(
                column_id=reference.id, display_name="Customer ID", referenced_column_id=identifier.id,
            ))
            session.commit()

        def business_model_dependency():
            with Session(self.engine, expire_on_commit=False) as session:
                yield BusinessModelService(session)

        app.dependency_overrides[get_business_model_service] = business_model_dependency
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_read_is_non_mutating_and_layer_domain_workflow(self) -> None:
        response = self.client.get(f"{BASE}/connections/{self.connection_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["tables"]), 2)
        self.assertEqual(response.json()["lineage_edges"][0]["origin"], "dictionary")
        with Session(self.engine) as session:
            self.assertEqual(session.query(TableDictionary).count(), 0)

        layer = self.client.post(f"{BASE}/layers", json={"name": "Core", "level": 0}).json()
        self.assertEqual(self.client.post(f"{BASE}/layers", json={"name": "core"}).status_code, 409)
        assignment = self.client.put(
            f"{BASE}/tables/{self.source_id}/layer", json={"layer_id": layer["id"]}
        )
        self.assertEqual(assignment.status_code, 200)
        domain = self.client.post(f"{BASE}/domains", json={
            "name": "Bán hàng", "table_ids": [str(self.source_id), str(self.target_id)],
        })
        self.assertEqual(domain.status_code, 201)
        self.assertEqual(len(domain.json()["table_ids"]), 2)
        model = self.client.get(f"{BASE}/connections/{self.connection_id}").json()
        source_table = next(table for table in model["tables"] if table["table_id"] == str(self.source_id))
        self.assertEqual(source_table["layer_id"], layer["id"])
        self.assertEqual(len(model["domains"][0]["table_ids"]), 2)
        self.assertEqual(model["lineage_edges"][0]["origin"], "dictionary")
        self.assertEqual(model["lineage_edges"][0]["kind"], "relation")

        self.assertEqual(self.client.delete(f"{BASE}/layers/{layer['id']}").status_code, 204)
        model = self.client.get(f"{BASE}/connections/{self.connection_id}").json()
        self.assertTrue(all(table["layer_id"] is None for table in model["tables"]))

    def test_canvas_and_lineage_overrides(self) -> None:
        self.client.put(f"{BASE}/tables/{self.source_id}/layer", json={"layer_id": None})
        self.client.put(f"{BASE}/tables/{self.target_id}/layer", json={"layer_id": None})
        canvas = self.client.put(
            f"{BASE}/connections/{self.connection_id}/canvases/business",
            json={"layout": {"tables": {str(self.source_id): [0, 1]}}},
        )
        self.assertEqual(canvas.status_code, 200)
        self.assertIn("tables", self.client.get(f"{BASE}/connections/{self.connection_id}").json()["business_canvas"])

        edge = self.client.put(f"{BASE}/connections/{self.connection_id}/lineage-edges", json={
            "source_table_id": str(self.source_id), "target_table_id": str(self.target_id),
            "kind": "relation", "is_hidden": True,
        })
        self.assertEqual(edge.status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/connections/{self.connection_id}").json()["lineage_edges"], [])
        self.assertEqual(self.client.delete(
            f"{BASE}/connections/{self.connection_id}/lineage-edges/{edge.json()['id']}"
        ).status_code, 204)
        self.assertEqual(len(self.client.get(f"{BASE}/connections/{self.connection_id}").json()["lineage_edges"]), 1)

    def test_rejects_cross_connection_edge_and_invalid_order(self) -> None:
        response = self.client.put(f"{BASE}/connections/{self.connection_id}/lineage-edges", json={
            "source_table_id": str(self.source_id), "target_table_id": str(self.foreign_id), "kind": "flow",
        })
        self.assertEqual(response.status_code, 422)
        layer = self.client.post(f"{BASE}/layers", json={"name": "Core"}).json()
        response = self.client.put(f"{BASE}/layers/order", json={"levels": [[layer["id"], layer["id"]]]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post(f"{BASE}/layers", json={"name": "Bad", "color": "red"}).status_code, 422)

    def test_layer_levels_do_not_change_reference_direction_and_invalid_domain_is_atomic(self) -> None:
        core = self.client.post(f"{BASE}/layers", json={"name": "Core", "level": 0}).json()
        mart = self.client.post(f"{BASE}/layers", json={"name": "Mart", "level": 1}).json()
        self.client.put(f"{BASE}/tables/{self.target_id}/layer", json={"layer_id": core["id"]})
        self.client.put(f"{BASE}/tables/{self.source_id}/layer", json={"layer_id": mart["id"]})
        edge = self.client.get(f"{BASE}/connections/{self.connection_id}").json()["lineage_edges"][0]
        self.assertEqual((edge["kind"], edge["source_table_id"], edge["target_table_id"]), (
            "relation", str(self.source_id), str(self.target_id),
        ))

        order = self.client.put(f"{BASE}/layers/order", json={"levels": [[mart["id"]], [core["id"]]]})
        self.assertEqual(order.status_code, 200)
        edge = self.client.get(f"{BASE}/connections/{self.connection_id}").json()["lineage_edges"][0]
        self.assertEqual(edge["kind"], "relation")

        with Session(self.engine) as session:
            before = session.query(TableDictionary).count()
        response = self.client.post(f"{BASE}/domains", json={
            "name": "Sai", "table_ids": [str(self.foreign_id), str(uuid4())],
        })
        self.assertEqual(response.status_code, 404)
        with Session(self.engine) as session:
            self.assertEqual(session.query(TableDictionary).count(), before)
