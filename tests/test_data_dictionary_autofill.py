import json
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.data_dictionary import models as data_dictionary_models  # noqa: F401
from backend.modules.data_dictionary.dependencies import (
    get_data_dictionary_autofill_service,
    get_data_dictionary_service,
)
from backend.modules.data_dictionary.services import (
    DataDictionaryAutofillService,
    DataDictionaryService,
    autofill_service,
)
from backend.modules.data_dictionary.services.dictionary_suggester import (
    ColumnSuggestion,
    ColumnSuggestions,
    TableSuggestion,
)
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from tests.service_key import use_service_key

BASE = "/api/v1"


class ProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"provider error {status_code}")
        self.status_code = status_code


class FakeSuggester:
    def __init__(self, columns=None, table=None, ready=True, column_error=None):
        self.columns = columns or {}
        self.table = table
        self.ready = ready
        self.column_error = column_error
        self.table_context = None

    def ensure_ready(self):
        if not self.ready:
            raise RuntimeError("missing key")

    def suggest_column_batches(self, contexts):
        for index, context in enumerate(contexts):
            if self.column_error:
                yield index, self.column_error
                continue
            yield index, ColumnSuggestions(suggestions=[
                ColumnSuggestion(column_name=column["column_name"], **self.columns[column["column_name"]])
                for column in context["columns"]
                if column["column_name"] in self.columns
            ])

    def suggest_table(self, context):
        self.table_context = context
        return self.table


def parse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class DataDictionaryAutofillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine, expire_on_commit=False) as session:
            connection = DatabaseConnection(name="Source", dialect="postgresql", uri_ciphertext="x", is_active=True)
            session.add(connection)
            session.flush()
            schema = DatabaseSchema(connection_id=connection.id, name="public")
            session.add(schema)
            session.flush()
            self.orders = DatabaseTable(schema_id=schema.id, name="orders", table_type="TABLE")
            self.empty = DatabaseTable(schema_id=schema.id, name="empty", table_type="TABLE")
            session.add_all([self.orders, self.empty])
            session.flush()
            self.columns = {
                name: DatabaseColumn(
                    table_id=self.orders.id, name=name, data_type=data_type, ordinal_position=position,
                    is_nullable=name != "id", is_primary_key=name == "id",
                )
                for position, (name, data_type) in enumerate(
                    [("id", "BIGINT"), ("amount", "NUMERIC"), ("status", "VARCHAR(20)"), ("created_at", "TIMESTAMP")],
                    start=1,
                )
            }
            session.add_all(self.columns.values())
            session.commit()

        self.suggester = FakeSuggester(
            columns={
                "id": {"display_name": "Mã đơn hàng"},
                "amount": {"display_name": "Giá trị đơn", "unit": "VND", "business_term": "Doanh thu"},
                "status": {"display_name": "Trạng thái", "description": "Trạng thái xử lý đơn"},
                "created_at": {"display_name": "Thời điểm tạo"},
            },
            table=TableSuggestion(
                display_name="Đơn hàng",
                description="Các đơn hàng đã đặt",
                grain_description="Một đơn hàng",
                created_at_column="created_at",
            ),
        )

        def dictionary_dependency():
            with Session(self.engine) as session:
                yield DataDictionaryService(session)

        def autofill_dependency():
            with Session(self.engine) as session:
                yield DataDictionaryAutofillService(session, self.suggester)

        app.dependency_overrides[get_data_dictionary_service] = dictionary_dependency
        app.dependency_overrides[get_data_dictionary_autofill_service] = autofill_dependency
        self.client = TestClient(app, headers=use_service_key(self), raise_server_exceptions=True)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        autofill_service._running.clear()
        self.engine.dispose()

    def autofill(self, table=None):
        return self.client.post(f"{BASE}/tables/{(table or self.orders).id}/dictionary/autofill")

    def dictionary(self):
        return self.client.get(f"{BASE}/tables/{self.orders.id}/dictionary").json()

    def test_streams_and_saves_suggestions_for_an_unsaved_table(self) -> None:
        response = self.autofill()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = parse_events(response.text)
        self.assertEqual([name for name, _ in events], ["status", "columns", "status", "table", "done"])
        self.assertEqual(events[1][1]["processed"], 4)
        self.assertEqual(
            {column["name"]: column["display_name"] for column in events[1][1]["columns"]},
            {"id": "Mã đơn hàng", "amount": "Giá trị đơn", "status": "Trạng thái", "created_at": "Thời điểm tạo"},
        )
        self.assertEqual(events[-1][1], {"processed": 4, "total": 4, "failed_columns": 0, "table_filled": True})
        self.assertEqual(self.suggester.table_context["columns"][2]["description"], "Trạng thái xử lý đơn")

        saved = self.dictionary()
        self.assertTrue(saved["is_saved"])
        self.assertEqual(saved["display_name"], "Đơn hàng")
        self.assertEqual(saved["grain_description"], "Một đơn hàng")
        self.assertEqual([(r["role"], r["column_name"]) for r in saved["column_roles"]], [("created_at", "created_at")])
        columns = {column["name"]: column for column in saved["columns"]}
        self.assertTrue(all(column["is_saved"] for column in columns.values()))
        self.assertEqual((columns["amount"]["unit"], columns["amount"]["business_term"]), ("VND", "Doanh thu"))
        self.assertEqual(columns["amount"]["semantic_role"], "measure")
        self.assertEqual((columns["created_at"]["temporal_kind"], columns["created_at"]["semantic_role"]),
                         ("timestamp", "time"))
        self.assertEqual(columns["id"]["semantic_role"], "key")

    def test_keeps_values_the_user_already_wrote(self) -> None:
        self.client.put(f"{BASE}/tables/{self.orders.id}/dictionary", json={
            "display_name": "Đơn bán", "description": "Mô tả của người dùng",
        })
        self.client.put(f"{BASE}/tables/{self.orders.id}/dictionary/columns", json={"columns": [
            {"column_id": str(self.columns["amount"].id), "display_name": "Tổng tiền", "unit": "USD"},
        ]})

        self.autofill()

        saved = self.dictionary()
        self.assertEqual((saved["display_name"], saved["description"]), ("Đơn bán", "Mô tả của người dùng"))
        self.assertEqual(saved["grain_description"], "Một đơn hàng")
        amount = next(column for column in saved["columns"] if column["name"] == "amount")
        self.assertEqual((amount["display_name"], amount["unit"], amount["business_term"]),
                         ("Tổng tiền", "USD", "Doanh thu"))

    def test_ignores_unknown_columns_and_reports_missing_ones(self) -> None:
        self.suggester.columns = {"status": {"display_name": "Trạng thái"}, "ghost": {"display_name": "Ma"}}
        self.suggester.table = None
        events = parse_events(self.autofill().text)
        self.assertEqual(events[-1][1]["failed_columns"], 3)
        self.assertFalse(events[-1][1]["table_filled"])
        saved = self.dictionary()
        self.assertFalse(saved["is_saved"])
        self.assertEqual([column["name"] for column in saved["columns"] if column["is_saved"]], ["status"])

    def test_rejected_api_key_ends_the_stream_with_an_error(self) -> None:
        self.suggester.column_error = ProviderError(401)
        events = parse_events(self.autofill().text)
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(events[-1][1]["code"], "dictionary_autofill_unavailable")
        self.assertFalse(self.dictionary()["is_saved"])
        self.suggester.column_error = None
        self.assertEqual(parse_events(self.autofill().text)[-1][0], "done")

    def test_nothing_suggested_is_an_error(self) -> None:
        self.suggester.column_error = ProviderError(500)
        self.suggester.table = None
        events = parse_events(self.autofill().text)
        self.assertEqual(events[-1], ("error", {
            "code": "dictionary_autofill_failed", "message": "Mô hình không trả về gợi ý hợp lệ; thử lại sau.",
        }))

    def test_rejects_requests_before_streaming(self) -> None:
        self.assertEqual(self.autofill(self.empty).status_code, 422)
        autofill_service._running.add(self.orders.id)
        self.assertEqual(self.autofill().status_code, 409)
        autofill_service._running.clear()
        self.suggester.ready = False
        response = self.autofill()
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENROUTER_API_KEY", response.json()["detail"])
        missing = self.client.post(f"{BASE}/tables/01a1d33a-0000-7000-8000-000000000000/dictionary/autofill")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
