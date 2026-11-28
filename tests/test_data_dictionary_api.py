import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.data_dictionary import models as data_dictionary_models  # noqa: F401
from backend.modules.data_dictionary.dependencies import get_data_dictionary_service
from backend.modules.data_dictionary.services import DataDictionaryService
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from tests.service_key import use_service_key

BASE = "/api/v1"


class DataDictionaryApiTests(unittest.TestCase):
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
            self.connection_id = connection.id
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            other_schema = DatabaseSchema(connection_id=other.id, name="public")
            session.add_all([schema, other_schema])
            session.flush()
            self.orders = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE", description="Đơn")
            self.customers = DatabaseTable(schema_id=schema.id, name="customers", table_type="TABLE")
            self.values = DatabaseTable(schema_id=schema.id, name="metric_values", table_type="TABLE")
            self.catalog = DatabaseTable(schema_id=schema.id, name="metric_catalog", table_type="TABLE")
            self.foreign = DatabaseTable(schema_id=other_schema.id, name="elsewhere", table_type="TABLE")
            session.add_all([self.orders, self.customers, self.values, self.catalog, self.foreign])
            session.flush()

            def column(table, name, data_type, position, is_primary_key=False):
                return DatabaseColumn(
                    table_id=table.id, name=name, data_type=data_type, ordinal_position=position,
                    is_nullable=not is_primary_key, is_primary_key=is_primary_key,
                )

            self.order_id = column(self.orders, "id", "BIGINT", 1, True)
            self.order_customer = column(self.orders, "customer_id", "BIGINT", 2)
            self.order_amount = column(self.orders, "amount", "NUMERIC(12, 2)", 3)
            self.order_date = column(self.orders, "order_date", "DATE", 4)
            self.order_status = column(self.orders, "status", "VARCHAR(20)", 5)
            self.order_created = column(self.orders, "created_at", "TIMESTAMP", 6)
            self.customer_id = column(self.customers, "id", "BIGINT", 1, True)
            self.value_metric = column(self.values, "metric_id", "BIGINT", 1)
            self.value_number = column(self.values, "value_number", "NUMERIC", 2)
            self.catalog_id = column(self.catalog, "metric_id", "BIGINT", 1, True)
            self.catalog_code = column(self.catalog, "code", "VARCHAR(50)", 2)
            self.catalog_name = column(self.catalog, "name", "VARCHAR(100)", 3)
            self.catalog_aggregation = column(self.catalog, "aggregation", "VARCHAR(20)", 4)
            self.foreign_id = column(self.foreign, "id", "BIGINT", 1, True)
            session.add_all([
                self.order_id, self.order_customer, self.order_amount, self.order_date, self.order_status,
                self.order_created, self.customer_id, self.value_metric, self.value_number, self.catalog_id,
                self.catalog_code, self.catalog_name, self.catalog_aggregation, self.foreign_id,
            ])
            session.commit()

        def dictionary_dependency():
            with Session(self.engine) as session:
                yield DataDictionaryService(session)

        app.dependency_overrides[get_data_dictionary_service] = dictionary_dependency
        self.client = TestClient(app, headers=use_service_key(self), raise_server_exceptions=True)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def put_table(self, table, **body):
        return self.client.put(f"{BASE}/tables/{table.id}/dictionary", json={"display_name": table.name, **body})

    def put_columns(self, table, columns):
        return self.client.put(f"{BASE}/tables/{table.id}/dictionary/columns", json={"columns": columns})

    def test_unsaved_dictionary_returns_defaults(self) -> None:
        response = self.client.get(f"{BASE}/tables/{self.orders.id}/dictionary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["is_saved"])
        self.assertEqual((body["display_name"], body["description"], body["layout"]), ("orders", "Đơn", "wide"))
        roles = {column["name"]: column["semantic_role"] for column in body["columns"]}
        self.assertTrue(all(column["semantic_role_is_default"] for column in body["columns"]))
        self.assertEqual(roles, {
            "id": "key", "customer_id": "key", "amount": "measure", "order_date": "time",
            "status": "dimension", "created_at": "time",
        })
        kinds = {column["name"]: column["temporal_kind"] for column in body["columns"]}
        self.assertEqual((kinds["order_date"], kinds["created_at"], kinds["amount"]), ("date", "timestamp", None))
        self.assertEqual(self.client.get(f"{BASE}/tables/{self.order_id.id}/dictionary").status_code, 404)

    def test_save_table_dictionary_with_roles_and_grains(self) -> None:
        response = self.put_table(
            self.orders,
            display_name=" Đơn hàng ",
            grain_description="Một đơn hàng",
            table_kind="base",
            contains_pii=True,
            column_roles=[
                {"role": "time", "column_id": str(self.order_date.id)},
                {"role": "created_at", "column_id": str(self.order_created.id)},
            ],
            time_grains=[{"time_grain": "day", "label": "Theo ngày"}],
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["is_saved"])
        self.assertEqual(body["display_name"], "Đơn hàng")
        self.assertEqual({role["role"]: role["column_name"] for role in body["column_roles"]},
                         {"time": "order_date", "created_at": "created_at"})
        self.assertEqual(body["time_grains"], [{"row_kind_value": None, "label": "Theo ngày", "time_grain": "day"}])

        replaced = self.put_table(self.orders, column_roles=[], time_grains=[]).json()
        self.assertEqual((replaced["column_roles"], replaced["time_grains"], replaced["contains_pii"]), ([], [], False))

    def test_table_dictionary_validation(self) -> None:
        cases = [
            {"table_kind": "fact"},
            {"layout": "matrix"},
            {"column_roles": [{"role": "catalog_key", "column_id": str(self.order_id.id)}]},
            {"column_roles": [{"role": "time", "column_id": str(self.customer_id.id)}]},
            {"column_roles": [{"role": "time", "qualifier": "number", "column_id": str(self.order_date.id)}]},
            {"time_grains": [{"time_grain": "decade"}]},
            {"time_grains": [{"time_grain": "day", "row_kind_value": "daily"}]},
            {"time_grains": [{"time_grain": "day"}, {"time_grain": "hour"}]},
            {"layout": "indicator_values"},
            {"indicator_aggregations": [{"source_code": "SUM", "aggregation": "SUM"}]},
            {"indicator_catalog_table_id": str(self.catalog.id)},
        ]
        for body in cases:
            with self.subTest(body=body):
                response = self.put_table(self.orders, **body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(set(response.json()), {"detail"})
        mixed = self.put_table(
            self.orders,
            column_roles=[{"role": "row_kind", "column_id": str(self.order_status.id)}],
            time_grains=[{"time_grain": "day"}],
        )
        self.assertEqual(mixed.status_code, 422)
        self.assertFalse(self.client.get(f"{BASE}/tables/{self.orders.id}/dictionary").json()["is_saved"])

    def test_indicator_layouts(self) -> None:
        catalog = self.put_table(
            self.catalog,
            layout="indicator_catalog",
            column_roles=[
                {"role": "catalog_key", "column_id": str(self.catalog_id.id)},
                {"role": "catalog_code", "column_id": str(self.catalog_code.id)},
                {"role": "catalog_name", "column_id": str(self.catalog_name.id)},
                {"role": "catalog_aggregation", "column_id": str(self.catalog_aggregation.id)},
            ],
            indicator_aggregations=[{"source_code": "TONG", "aggregation": "SUM"}],
        )
        self.assertEqual(catalog.status_code, 200, catalog.text)
        values_body = {
            "layout": "indicator_values",
            "indicator_catalog_table_id": str(self.catalog.id),
            "column_roles": [
                {"role": "indicator_key", "column_id": str(self.value_metric.id)},
                {"role": "value", "qualifier": "number", "column_id": str(self.value_number.id)},
            ],
        }
        values = self.put_table(self.values, **values_body)
        self.assertEqual(values.status_code, 200, values.text)
        self.assertEqual(values.json()["indicator_catalog"]["table_name"], "metric_catalog")

        self.assertEqual(self.put_table(self.catalog).status_code, 200)
        self.assertIsNone(self.client.get(f"{BASE}/tables/{self.values.id}/dictionary").json()["indicator_catalog"])
        self.assertEqual(self.put_table(self.values, **values_body).status_code, 422)

    def test_save_column_dictionaries(self) -> None:
        response = self.put_columns(self.orders, [
            {
                "column_id": str(self.order_amount.id),
                "display_name": "Tổng tiền",
                "unit": "VND",
                "aggregations": ["SUM", "AVG", "SUM"],
                "synonyms": ["doanh thu", "Doanh Thu", " doanh số ", ""],
            },
            {
                "column_id": str(self.order_customer.id),
                "display_name": "Khách hàng",
                "semantic_role": "key",
                "referenced_column_id": str(self.customer_id.id),
            },
            {"column_id": str(self.order_status.id), "display_name": "Trạng thái", "is_primary_key": False},
        ])
        self.assertEqual(response.status_code, 200, response.text)
        columns = {column["name"]: column for column in response.json()["columns"]}
        self.assertEqual(columns["amount"]["aggregations"], ["SUM", "AVG"])
        self.assertEqual(columns["amount"]["synonyms"], ["doanh thu", "doanh số"])
        self.assertEqual(columns["customer_id"]["referenced_column"]["table_name"], "customers")
        self.assertEqual(columns["customer_id"]["semantic_role"], "key")
        self.assertFalse(columns["customer_id"]["semantic_role_is_default"])
        self.assertTrue(columns["amount"]["semantic_role_is_default"])
        self.assertFalse(columns["id"]["is_saved"])

        updated = self.put_columns(self.orders, [
            {"column_id": str(self.order_amount.id), "display_name": "Tổng tiền", "synonyms": ["doanh thu thuần"]},
        ]).json()
        amount = next(column for column in updated["columns"] if column["name"] == "amount")
        self.assertEqual((amount["aggregations"], amount["synonyms"]), ([], ["doanh thu thuần"]))

    def test_column_dictionary_validation(self) -> None:
        amount = {"column_id": str(self.order_amount.id), "display_name": "x"}
        cases = [
            {"column_id": str(self.customer_id.id), "display_name": "x"},
            {**amount, "semantic_role": "metric"},
            {**amount, "temporal_kind": "time"},
            {"column_id": str(self.order_status.id), "display_name": "x", "aggregations": ["SUM"]},
            {"column_id": str(self.order_customer.id), "display_name": "x", "aggregations": ["SUM"]},
            {**amount, "aggregations": ["MEDIAN"]},
            {**amount, "referenced_column_id": str(self.order_amount.id)},
            {**amount, "referenced_column_id": str(self.foreign_id.id)},
            {**amount, "synonyms": [f"s{i}" for i in range(21)]},
            {**amount, "display_name": " "},
        ]
        for column in cases:
            with self.subTest(column=column):
                response = self.put_columns(self.orders, [column])
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.put_columns(self.orders, [amount, amount]).status_code, 422)

    def test_connection_summary(self) -> None:
        self.put_table(self.orders, display_name="Đơn hàng")
        self.client.put(f"{BASE}/tables/{self.orders.id}/dictionary/columns", json={"columns": [
            {"column_id": str(self.order_id.id), "display_name": "Mã đơn"},
            {"column_id": str(self.order_amount.id), "display_name": "Giá trị"},
        ]})
        self.client.put(f"{BASE}/tables/{self.customers.id}/dictionary/columns", json={"columns": [
            {"column_id": str(self.customer_id.id), "display_name": "Mã khách"},
        ]})

        response = self.client.get(f"{BASE}/database-connections/{self.connection_id}/dictionary-summary")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual((summary["table_count"], summary["described_table_count"]), (4, 1))
        self.assertEqual([schema["schema_name"] for schema in summary["schemas"]], ["public"])
        tables = {table["table_name"]: table for table in summary["schemas"][0]["tables"]}
        self.assertEqual(list(tables), ["customers", "metric_catalog", "metric_values", "orders"])
        self.assertEqual(
            (tables["orders"]["is_saved"], tables["orders"]["display_name"], tables["orders"]["column_count"],
             tables["orders"]["described_column_count"]),
            (True, "Đơn hàng", 6, 2),
        )
        self.assertEqual(
            (tables["customers"]["is_saved"], tables["customers"]["display_name"],
             tables["customers"]["described_column_count"]),
            (False, "customers", 1),
        )
        self.assertEqual((tables["orders"]["layout"], tables["customers"]["layout"]), ("wide", "wide"))
        missing_id = "01a1d33a-0000-7000-8000-000000000000"
        missing = self.client.get(f"{BASE}/database-connections/{missing_id}/dictionary-summary")
        self.assertEqual(missing.status_code, 404)

    def test_connection_stats(self) -> None:
        self.put_table(self.orders, display_name="Đơn hàng")
        self.put_columns(self.orders, [
            {"column_id": str(self.order_id.id), "display_name": "Mã đơn"},
            {
                "column_id": str(self.order_customer.id), "display_name": "Khách",
                "referenced_column_id": str(self.customer_id.id),
            },
        ])
        self.put_columns(self.values, [
            {
                "column_id": str(self.value_metric.id), "display_name": "Chỉ số",
                "referenced_column_id": str(self.catalog_id.id),
            },
        ])
        self.put_columns(self.catalog, [
            {
                "column_id": str(self.catalog_code.id), "display_name": "Mã",
                "referenced_column_id": str(self.catalog_id.id),
            },
        ])

        response = self.client.get(f"{BASE}/database-connections/{self.connection_id}/dictionary-stats?limit=2")
        self.assertEqual(response.status_code, 200)
        stats = response.json()
        self.assertEqual(
            (stats["table_count"], stats["described_table_count"], stats["column_count"],
             stats["described_column_count"]),
            (4, 1, 13, 4),
        )
        self.assertEqual(
            [(schema["schema_name"], schema["table_count"], schema["described_table_count"])
             for schema in stats["schemas"]],
            [("public", 4, 1)],
        )
        self.assertEqual(
            [(table["table_name"], table["column_count"], table["described_column_count"])
             for table in stats["most_columns"]],
            [("orders", 6, 2), ("metric_catalog", 4, 1)],
        )
        self.assertEqual(stats["most_columns"][0]["display_name"], "Đơn hàng")
        self.assertEqual(
            [(table["table_name"], table["referencing_table_count"]) for table in stats["most_referenced"]],
            [("customers", 1), ("metric_catalog", 1)],
        )
        self.assertEqual(
            self.client.get(f"{BASE}/database-connections/{self.connection_id}/dictionary-stats?limit=0").status_code,
            422,
        )
        missing_id = "01a1d33a-0000-7000-8000-000000000000"
        self.assertEqual(self.client.get(f"{BASE}/database-connections/{missing_id}/dictionary-stats").status_code, 404)

    def test_source_column_removal_cleans_dictionary(self) -> None:
        self.put_table(self.orders, column_roles=[{"role": "time", "column_id": str(self.order_date.id)}])
        self.put_columns(self.orders, [
            {"column_id": str(self.order_date.id), "display_name": "Ngày đặt", "synonyms": ["ngày"]},
            {
                "column_id": str(self.order_customer.id),
                "display_name": "Khách",
                "referenced_column_id": str(self.customer_id.id),
            },
        ])
        with Session(self.engine) as session:
            session.delete(session.get(DatabaseColumn, self.order_date.id))
            session.delete(session.get(DatabaseColumn, self.customer_id.id))
            session.commit()
        body = self.client.get(f"{BASE}/tables/{self.orders.id}/dictionary").json()
        self.assertEqual(body["column_roles"], [])
        customer = next(column for column in body["columns"] if column["name"] == "customer_id")
        self.assertTrue(customer["is_saved"])
        self.assertIsNone(customer["referenced_column"])

        with Session(self.engine) as session:
            session.delete(session.get(DatabaseTable, self.orders.id))
            session.commit()
        self.assertEqual(self.client.get(f"{BASE}/tables/{self.orders.id}/dictionary").status_code, 404)


if __name__ == "__main__":
    unittest.main()
