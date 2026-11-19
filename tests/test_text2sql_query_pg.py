import json
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.core.setting import config
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.metric_management.models import Metric
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.common.errors import (
    Text2SqlInvalidRequest,
    Text2SqlQueryFailed,
    Text2SqlQueryTimeout,
)
from backend.modules.text2sql.query.executor import run_read_only
from backend.modules.text2sql.query.schemas import QueryFilter, QueryPlan, QueryTime
from backend.modules.text2sql.query.service import QueryService

register_all_models()

SERVER_URL = os.environ.get("POSTGRES_TEST_URL")
ROWS = [
    (1, "Bắc", "Nguyễn Văn A", "Gọi 0912 345 678", "079201012345", "100.50", "2026-01-10", "paid"),
    (2, "Bắc", "Trần Thị B", "b@example.com", "079201099999", "200.00", "2026-01-20", "paid"),
    (3, "Nam", "Nguyễn Văn A", "+84 987-654-321", "012345678901", "50.25", "2026-02-05", "refund"),
    (4, "Nam", "Lê C", None, None, None, "2026-02-15", "paid"),
    (5, "Trung", "Phạm D", "", "12345", "10.00", "2026-03-01", "paid"),
    (6, "Trung", "Phạm D", "", "12345", "20.00", "2026-03-02", "paid"),
    (7, "Bắc", "Hoàng E", "x", "", "300.00", "2026-03-20", "paid"),
    (8, "Nam", "Vũ F", "y", "", "5.00", "2026-03-25", "paid"),
]


@unittest.skipUnless(SERVER_URL, "Đặt POSTGRES_TEST_URL tới một PostgreSQL dùng để thử nghiệm (được tạo database tạm).")
class QueryServiceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = create_engine(make_url(SERVER_URL), isolation_level="AUTOCOMMIT")
        cls.database = f"t2s_query_{uuid4().hex[:12]}"
        with cls.admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.source_url = make_url(SERVER_URL).set(database=cls.database)
        source = create_engine(cls.source_url)
        with source.begin() as connection:
            connection.execute(text("""
                CREATE TABLE sales (
                    id integer PRIMARY KEY, region text, customer text, contact text, cccd text,
                    amount numeric(12,2), order_date date, status text)
            """))
            for row in ROWS:
                connection.execute(text(
                    "INSERT INTO sales VALUES (:a, :b, :c, :d, :e, :f, :g, :h)"
                ), dict(zip("abcdefgh", row)) | {"g": date.fromisoformat(row[6]), "f": row[5]})
            connection.execute(text(
                "CREATE VIEW slow_sales AS SELECT 1::numeric AS amount FROM (SELECT pg_sleep(4)) AS s"
            ))
        source.dispose()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{cls.database}" WITH (FORCE)'))
        cls.admin.dispose()

    def setUp(self) -> None:
        self.key = Fernet.generate_key().decode()
        patcher = patch.object(config, "connection_encryption_key", SimpleNamespace(get_secret_value=lambda: self.key))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        ciphertext = Fernet(self.key.encode()).encrypt(self.source_url.render_as_string(hide_password=False).encode())
        self.connection = DatabaseConnection(
            name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext=ciphertext.decode()
        )
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.table = DatabaseTable(schema_id=schema.id, name="sales", table_type="TABLE")
        self.slow = DatabaseTable(schema_id=schema.id, name="slow_sales", table_type="VIEW")
        s.add_all([self.table, self.slow])
        s.flush()
        self.col = {}
        for position, (name, data_type) in enumerate([
            ("id", "integer"), ("region", "text"), ("customer", "text"), ("contact", "text"), ("cccd", "text"),
            ("amount", "numeric(12,2)"), ("order_date", "date"), ("status", "text"),
        ], start=1):
            column = DatabaseColumn(
                table_id=self.table.id, name=name, data_type=data_type, ordinal_position=position, is_nullable=True
            )
            s.add(column)
            self.col[name] = column
        s.add(DatabaseColumn(
            table_id=self.slow.id, name="amount", data_type="numeric", ordinal_position=1, is_nullable=True
        ))
        s.flush()
        s.add_all([
            ColumnDictionary(column_id=self.col["customer"].id, display_name="Khách hàng", contains_pii=True),
            ColumnDictionary(column_id=self.col["contact"].id, display_name="Liên hệ"),
            ColumnDictionary(column_id=self.col["cccd"].id, display_name="Số CCCD"),
            ColumnDictionary(column_id=self.col["region"].id, display_name="Khu vực"),
            TableDictionary(table_id=self.table.id, display_name="Bán hàng"),
        ])
        self.revenue = Metric(
            table_id=self.table.id, name="revenue", label="Doanh thu", expression="SUM(amount)",
            warning_text="Chưa trừ hoàn tiền",
        )
        self.orders = Metric(table_id=self.table.id, name="orders", label="Số đơn", expression="COUNT(*)")
        self.slow_metric = Metric(table_id=self.slow.id, name="slow", expression="SUM(amount)")
        s.add_all([self.revenue, self.orders, self.slow_metric])
        s.flush()
        self.service = QueryService(s)

    def query(self, **plan):
        plan.setdefault("metric_id", self.revenue.id)
        compiled = self.service.prepare(self.connection.id, QueryPlan(**plan))
        return compiled, self.service.execute(compiled, self.service.resolve_source(self.connection.id))

    def source_count(self) -> int:
        engine = create_engine(self.source_url)
        try:
            with engine.connect() as connection:
                return connection.scalar(text("SELECT count(*) FROM sales"))
        finally:
            engine.dispose()

    def test_metric_by_dimension_returns_exact_decimals_sorted_by_metric(self) -> None:
        _, result = self.query(group_by=[self.col["region"].id])
        self.assertEqual(result.rows, [["Bắc", "600.50"], ["Nam", "55.25"], ["Trung", "30.00"]])
        self.assertEqual([column.name for column in result.columns], ["Khu vực", "Doanh thu"])
        self.assertEqual((result.row_count, result.truncated), (3, False))
        self.assertEqual(result.metric.warning_text, "Chưa trừ hoàn tiền")
        self.assertIn("GROUP BY 1", result.sql)

    def test_time_series_uses_half_open_range_and_month_buckets(self) -> None:
        _, result = self.query(time=QueryTime(
            column_id=self.col["order_date"].id, start=date(2026, 1, 1), end=date(2026, 3, 1), granularity="month",
        ))
        self.assertEqual(result.rows, [["2026-01-01", "300.50"], ["2026-02-01", "50.25"]])
        self.assertEqual(result.columns[0].role, "time")

    def test_filters_and_null_semantics(self) -> None:
        _, result = self.query(filters=[
            QueryFilter(column_id=self.col["status"].id, operator="in", value=["paid"]),
            QueryFilter(column_id=self.col["amount"].id, operator="greater_than_or_equal", value=100),
        ])
        self.assertEqual(result.rows, [["600.50"]])
        _, empty = self.query(filters=[QueryFilter(column_id=self.col["region"].id, operator="equals", value="Tây")])
        self.assertEqual(empty.rows, [[None]])
        _, nulls = self.query(
            metric_id=self.orders.id, filters=[QueryFilter(column_id=self.col["amount"].id, operator="is_null")],
        )
        self.assertEqual(nulls.rows, [[1]])

    def test_contains_escapes_wildcards_and_injection_is_inert(self) -> None:
        before = self.source_count()
        for value in ("%", "_", "'; DROP TABLE sales; --"):
            with self.subTest(value):
                _, result = self.query(metric_id=self.orders.id, filters=[
                    QueryFilter(column_id=self.col["region"].id, operator="contains", value=value),
                ])
                self.assertEqual(result.rows, [[0]])
        self.assertEqual(self.source_count(), before)

    def test_group_by_pii_column_returns_placeholders_not_names(self) -> None:
        compiled, result = self.query(group_by=[self.col["customer"].id], limit=100)
        self.assertEqual(compiled.pii_columns, ["Khách hàng"])
        text_result = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        for name in ("Nguyễn", "Trần", "Phạm", "Hoàng", "Vũ", "Lê"):
            self.assertNotIn(name, text_result)
        self.assertEqual({row[0] for row in result.rows}, {f"<PII_{n}>" for n in range(1, 7)})
        self.assertEqual(result.pii.masked_columns, ["Khách hàng"])
        self.assertIn("placeholder", result.pii.warning)

    def test_unflagged_columns_are_still_scanned_for_pii_values(self) -> None:
        _, result = self.query(group_by=[self.col["contact"].id, self.col["cccd"].id], limit=100)
        text_result = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        for raw in ("0912", "987-654", "b@example.com", "079201012345", "012345678901"):
            self.assertNotIn(raw, text_result)
        self.assertIn("<EMAIL_ADDRESS_1>", text_result)
        self.assertIn("<VN_PHONE_NUMBER_1>", text_result)
        self.assertIn("<VN_CITIZEN_ID_1>", text_result)
        self.assertIn("12345", text_result)
        self.assertGreaterEqual(result.pii.detected["VN_PHONE_NUMBER"], 2)

    def test_row_limit_truncates_and_says_so(self) -> None:
        _, result = self.query(group_by=[self.col["id"].id], limit=3)
        self.assertEqual((result.row_count, result.truncated, result.limit), (3, True, 3))
        self.assertEqual(len(result.rows), 3)

    def test_executor_is_read_only_whatever_sql_it_is_given(self) -> None:
        before = self.source_count()
        attacks = (
            "INSERT INTO sales (id) VALUES (999)", "UPDATE sales SET amount = 0", "DELETE FROM sales",
            "TRUNCATE sales", "CREATE TABLE evil (x int)", "DROP TABLE sales", "ALTER TABLE sales ADD COLUMN y int",
            "SELECT 1 INTO TEMP evil_temp",
        )
        for sql in attacks:
            with self.subTest(sql), self.assertRaises(Text2SqlQueryFailed):
                run_read_only(self.source_url, sql, {}, frozenset(), 10, 5)
        self.assertEqual(self.source_count(), before)

    def test_transaction_is_repeatable_read_and_read_only(self) -> None:
        raw = run_read_only(
            self.source_url,
            "SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation'), "
            "current_setting('statement_timeout'), current_setting('application_name')",
            {}, frozenset(), 10, 7,
        )
        self.assertEqual(raw.rows, [("on", "repeatable read", "7s", "superset-ai")])

    def test_scope_token_is_set_for_the_transaction_only(self) -> None:
        from backend.modules.text2sql.query.executor import SCOPE_TOKEN

        sql = "SELECT current_setting('app.copilot_token', true)"
        reset = SCOPE_TOKEN.set("0198-scope")
        try:
            self.assertEqual(run_read_only(self.source_url, sql, {}, frozenset(), 10, 5).rows, [("0198-scope",)])
        finally:
            SCOPE_TOKEN.reset(reset)
        self.assertIn(run_read_only(self.source_url, sql, {}, frozenset(), 10, 5).rows, ([(None,)], [("",)]))

    def test_time_zone_cuts_days_where_the_caller_lives(self) -> None:
        from backend.modules.text2sql.query.executor import TIME_ZONE

        sql = "SELECT date_trunc('day', timestamptz '2026-11-15 18:00+00')::text"
        reset = TIME_ZONE.set("Asia/Ho_Chi_Minh")
        try:
            self.assertEqual(run_read_only(self.source_url, sql, {}, frozenset(), 10, 5).rows, [("2026-11-16 00:00:00+07",)])
        finally:
            TIME_ZONE.reset(reset)
        self.assertEqual(run_read_only(self.source_url, sql, {}, frozenset(), 10, 5).rows, [("2026-11-15 00:00:00+00",)])

    def test_slow_queries_time_out_with_a_helpful_message(self) -> None:
        with patch.object(config, "text2sql_query_timeout_seconds", 1):
            compiled = self.service.prepare(self.connection.id, QueryPlan(metric_id=self.slow_metric.id))
            with self.assertRaises(Text2SqlQueryTimeout) as raised:
                self.service.execute(compiled, self.service.resolve_source(self.connection.id))
        self.assertIn("1 giây", str(raised.exception))

    def test_no_source_connections_are_left_open(self) -> None:
        self.query(group_by=[self.col["region"].id])
        with self.assertRaises(Text2SqlQueryFailed):
            run_read_only(self.source_url, "SELECT * FROM missing_table", {}, frozenset(), 10, 5)
        with self.admin.connect() as connection:
            leftovers = connection.scalar(text(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'superset-ai' AND datname = :name"
            ), {"name": self.database})
        self.assertEqual(leftovers, 0)

    def test_failures_never_leak_the_connection_string_or_sql_error_text(self) -> None:
        broken = make_url(SERVER_URL).set(database="no_such_database_t2s", password="s3cret-pw")
        with self.assertRaises(Text2SqlQueryFailed) as raised:
            run_read_only(broken, "SELECT 1", {}, frozenset(), 10, 5)
        self.assertNotIn("s3cret-pw", str(raised.exception))
        self.assertNotIn("no_such_database_t2s", str(raised.exception))
        with self.assertRaises(Text2SqlQueryFailed) as raised:
            run_read_only(self.source_url, "SELECT 1/0", {}, frozenset(), 10, 5)
        self.assertNotIn("division", str(raised.exception).lower())

    def test_inactive_connection_and_wrong_key_are_refused(self) -> None:
        with patch.object(config, "connection_encryption_key", SimpleNamespace(
            get_secret_value=lambda: Fernet.generate_key().decode()
        )):
            with self.assertRaises(Text2SqlQueryFailed):
                self.service.resolve_source(self.connection.id)
        self.connection.is_active = False
        self.session.flush()
        with self.assertRaises(Text2SqlInvalidRequest):
            self.service.resolve_source(self.connection.id)

if __name__ == "__main__":
    unittest.main()
