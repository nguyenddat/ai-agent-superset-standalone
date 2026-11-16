import unittest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
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
    Text2SqlEntityNotFound,
    Text2SqlInvalidRequest,
    Text2SqlMetricNotRunnable,
)
from backend.modules.text2sql.query.compiler import compile_query, type_category
from backend.modules.text2sql.query.expression import compile_metric_expression
from backend.modules.text2sql.query.schemas import QueryFilter, QueryOrder, QueryPlan, QueryTime
from backend.modules.text2sql.vector_store.ingestion.documents.context import load_context

register_all_models()

COLUMNS = {"amount": (uuid4(), "amount"), "region": (uuid4(), "region"), "price": (uuid4(), "Price")}


class ExpressionTests(unittest.TestCase):
    def compile(self, expression: str) -> str:
        return compile_metric_expression(expression, COLUMNS)

    def test_accepts_typical_aggregate_expressions_and_quotes_columns(self) -> None:
        self.assertEqual(self.compile("SUM(amount)"), 'SUM("amount")')
        self.assertEqual(self.compile("count(*)"), "COUNT(*)")
        self.assertEqual(self.compile("COUNT(DISTINCT region)"), 'COUNT(DISTINCT "region")')
        self.assertEqual(self.compile("sum(amount) / nullif(count(*), 0)"), 'SUM("amount") / NULLIF(COUNT(*), 0)')
        self.assertEqual(self.compile("ROUND(AVG(price), 2)"), 'ROUND(CAST(AVG("Price") AS DECIMAL), 2)')
        self.assertIn("CASE WHEN", self.compile("SUM(CASE WHEN region = 'Bắc' THEN amount ELSE 0 END)"))
        self.assertIn("CAST(", self.compile("CAST(SUM(amount) AS DECIMAL)"))

    def test_column_names_are_case_insensitive_but_rendered_exactly(self) -> None:
        self.assertEqual(self.compile("AVG(PRICE)"), 'AVG("Price")')

    def test_string_literals_cannot_break_out_of_the_expression(self) -> None:
        sql = self.compile("SUM(CASE WHEN region = 'x'' OR 1=1 --' THEN amount END)")
        self.assertIn("'x'' OR 1=1 --'", sql)
        self.assertNotIn("DROP", sql)

    def test_rejects_dangerous_or_unsupported_expressions(self) -> None:
        rejected = {
            "function call": "pg_sleep(10)",
            "subquery": "SUM((SELECT 1))",
            "window": "SUM(amount) OVER ()",
            "filter clause": "SUM(amount) FILTER (WHERE amount > 1)",
            "string concat": "SUM(amount) || 'x'",
            "no aggregate": "amount",
            "qualified column": "SUM(t.amount)",
            "schema qualified": "SUM(public.t.amount)",
            "unknown column": "SUM(secret)",
            "star outside count": "SUM(*)",
            "multiple statements": "SUM(amount); DROP TABLE x",
            "comment tail": "SUM(amount) -- ; DROP",
            "bad cast": "CAST(SUM(amount) AS JSON)",
            "syntax error": "SUM(",
            "empty": "",
            "too long": "SUM(amount)" + " + SUM(amount)" * 400,
            "ordered set": "percentile_cont(0.5) WITHIN GROUP (ORDER BY amount)",
        }
        for name, expression in rejected.items():
            with self.subTest(name), self.assertRaises(Text2SqlMetricNotRunnable):
                self.compile(expression)


class CompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        self.connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.table = DatabaseTable(schema_id=schema.id, name="sales", table_type="TABLE")
        self.other_table = DatabaseTable(schema_id=schema.id, name="stock", table_type="TABLE")
        s.add_all([self.table, self.other_table])
        s.flush()
        specs = [
            ("region", "TEXT"), ("customer", "VARCHAR(255)"), ("amount", "NUMERIC(18,2)"), ("order_date", "DATE"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE"), ("is_paid", "BOOLEAN"), ("payload", "JSONB"),
            ("order_id", "UUID"), ("qty", "INTEGER"),
        ]
        self.col = {}
        for position, (name, data_type) in enumerate(specs, start=1):
            column = DatabaseColumn(
                table_id=self.table.id, name=name, data_type=data_type, ordinal_position=position, is_nullable=True
            )
            s.add(column)
            self.col[name] = column
        self.foreign = DatabaseColumn(
            table_id=self.other_table.id, name="stock", data_type="INTEGER", ordinal_position=1, is_nullable=True
        )
        s.add(self.foreign)
        s.flush()
        s.add_all([
            TableDictionary(table_id=self.table.id, display_name="Bán hàng"),
            ColumnDictionary(column_id=self.col["customer"].id, display_name="Khách hàng", contains_pii=True),
            ColumnDictionary(column_id=self.col["region"].id, display_name="Khu vực"),
            ColumnDictionary(column_id=self.col["order_date"].id, display_name="Ngày đặt"),
        ])
        self.revenue = Metric(table_id=self.table.id, name="revenue", label="Doanh thu", expression="SUM(amount)")
        self.virtual = Metric(table_id=self.table.id, name="virt", expression="COUNT(*)", source_sql="SELECT 1")
        self.sleepy = Metric(table_id=self.table.id, name="sleepy", expression="pg_sleep(5)")
        s.add_all([self.revenue, self.virtual, self.sleepy])
        s.flush()
        self.context = load_context(s, self.connection.id)

    def compile(self, **plan):
        plan.setdefault("metric_id", self.revenue.id)
        return compile_query(self.context, self.connection.id, QueryPlan(**plan), 200)

    def test_plain_metric_is_a_single_aggregate_select(self) -> None:
        query = self.compile()
        self.assertEqual(
            query.sql, 'SELECT SUM("amount") AS "metric_value" FROM "public"."sales" LIMIT :p0'
        )
        self.assertEqual(query.parameters, {"p0": 101})
        self.assertEqual([column.spec.role for column in query.columns], ["metric"])
        self.assertEqual(query.limit, 100)

    def test_group_by_defaults_to_metric_descending(self) -> None:
        query = self.compile(group_by=[self.col["region"].id])
        self.assertEqual(
            query.sql,
            'SELECT "region" AS "dim_1", SUM("amount") AS "metric_value" FROM "public"."sales" GROUP BY 1 '
            'ORDER BY "metric_value" DESC NULLS LAST LIMIT :p0',
        )
        self.assertEqual([column.spec.name for column in query.columns], ["Khu vực", "Doanh thu"])
        self.assertEqual(query.pii_columns, [])

    def test_time_series_with_range_buckets_and_orders_by_time(self) -> None:
        query = self.compile(time=QueryTime(
            column_id=self.col["order_date"].id, start=date(2026, 1, 1), end=date(2026, 7, 1), granularity="month",
        ))
        self.assertIn("CAST(date_trunc('month', \"order_date\") AS date) AS \"time_bucket\"", query.sql)
        self.assertIn('WHERE "order_date" >= :p0 AND "order_date" < :p1', query.sql)
        self.assertIn('ORDER BY "time_bucket" ASC NULLS LAST', query.sql)
        self.assertEqual(query.parameters["p0"], date(2026, 1, 1))
        self.assertEqual(query.columns[0].spec.role, "time")

    def test_time_range_without_granularity_does_not_group(self) -> None:
        query = self.compile(time=QueryTime(column_id=self.col["order_date"].id, start=date(2026, 1, 1)))
        self.assertNotIn("GROUP BY", query.sql)
        self.assertNotIn("time_bucket", query.sql)

    def test_timestamp_column_receives_datetimes(self) -> None:
        query = self.compile(time=QueryTime(column_id=self.col["created_at"].id, start=date(2026, 1, 1)))
        self.assertEqual(query.parameters["p0"], datetime(2026, 1, 1))

    def test_filters_are_bound_parameters_never_inlined(self) -> None:
        injection = "x'; DROP TABLE sales; --"
        query = self.compile(filters=[
            QueryFilter(column_id=self.col["region"].id, operator="equals", value=injection),
            QueryFilter(column_id=self.col["amount"].id, operator="greater_than_or_equal", value="10.5"),
            QueryFilter(column_id=self.col["region"].id, operator="in", value=["Bắc", "Nam"]),
            QueryFilter(column_id=self.col["region"].id, operator="contains", value="50%_x"),
            QueryFilter(column_id=self.col["is_paid"].id, operator="equals", value=True),
            QueryFilter(column_id=self.col["region"].id, operator="is_null"),
        ])
        self.assertNotIn("DROP", query.sql)
        self.assertNotIn("Bắc", query.sql)
        self.assertEqual(query.parameters["p0"], injection)
        self.assertEqual(query.parameters["p1"], Decimal("10.5"))
        self.assertEqual(query.parameters["p2"], ["Bắc", "Nam"])
        self.assertEqual(query.parameters["p3"], "%50\\%\\_x%")
        self.assertEqual(query.expanding, frozenset({"p2"}))
        self.assertIn("\"region\" ILIKE :p3 ESCAPE '\\'", query.sql)
        self.assertIn('"region" IS NULL', query.sql)

    def test_rejects_invalid_filters(self) -> None:
        region, amount = self.col["region"].id, self.col["amount"].id
        invalid = {
            "unknown operator type": QueryFilter(column_id=region, operator="greater_than", value="a"),
            "contains on number": QueryFilter(column_id=amount, operator="contains", value="1"),
            "non numeric": QueryFilter(column_id=amount, operator="equals", value="abc"),
            "bool for number": QueryFilter(column_id=amount, operator="equals", value=True),
            "number for text": QueryFilter(column_id=region, operator="equals", value=5),
            "missing value": QueryFilter(column_id=region, operator="equals"),
            "value on is_null": QueryFilter(column_id=region, operator="is_null", value="x"),
            "in not list": QueryFilter(column_id=region, operator="in", value="Bắc"),
            "in too long": QueryFilter(column_id=region, operator="in", value=[str(n) for n in range(51)]),
            "list for equals": QueryFilter(column_id=region, operator="equals", value=["a"]),
            "json column": QueryFilter(column_id=self.col["payload"].id, operator="equals", value="{}"),
            "uuid column": QueryFilter(column_id=self.col["order_id"].id, operator="equals", value="x"),
            "bad date": QueryFilter(column_id=self.col["order_date"].id, operator="equals", value="not-a-date"),
            "other table": QueryFilter(column_id=self.foreign.id, operator="equals", value=1),
            "unknown column": QueryFilter(column_id=uuid4(), operator="equals", value=1),
        }
        for name, filter_ in invalid.items():
            with self.subTest(name), self.assertRaises(Text2SqlInvalidRequest):
                self.compile(filters=[filter_])

    def test_pii_columns_cannot_be_filtered_or_used_as_time(self) -> None:
        with self.assertRaises(Text2SqlInvalidRequest) as raised:
            self.compile(filters=[QueryFilter(column_id=self.col["customer"].id, operator="equals", value="A")])
        self.assertIn("dữ liệu cá nhân", str(raised.exception))

    def test_group_by_pii_column_is_allowed_but_reported_for_consent(self) -> None:
        query = self.compile(group_by=[self.col["customer"].id, self.col["region"].id])
        self.assertEqual(query.pii_columns, ["Khách hàng"])
        self.assertTrue(query.columns[0].spec.contains_pii)
        self.assertFalse(query.columns[1].spec.contains_pii)
        self.assertTrue(query.columns[0].scan)
        self.assertFalse(query.columns[-1].scan)

    def test_rejects_invalid_group_by_and_time(self) -> None:
        invalid = {
            "duplicate": {"group_by": [self.col["region"].id, self.col["region"].id]},
            "json": {"group_by": [self.col["payload"].id]},
            "other table": {"group_by": [self.foreign.id]},
            "time on text": {"time": QueryTime(column_id=self.col["region"].id, granularity="day")},
            "empty time": {"time": QueryTime(column_id=self.col["order_date"].id)},
            "reversed range": {"time": QueryTime(
                column_id=self.col["order_date"].id, start=date(2026, 2, 1), end=date(2026, 1, 1)
            )},
        }
        for name, plan in invalid.items():
            with self.subTest(name), self.assertRaises(Text2SqlInvalidRequest):
                self.compile(**plan)

    def test_order_by_must_reference_the_result(self) -> None:
        region = self.col["region"].id
        query = self.compile(group_by=[region], order_by=[
            QueryOrder(by="metric", direction="asc"), QueryOrder(by=str(region), direction="desc"),
        ])
        self.assertIn('ORDER BY "metric_value" ASC NULLS LAST, "dim_1" DESC NULLS LAST', query.sql)
        for by in ("time", str(self.col["amount"].id), "nonsense"):
            with self.subTest(by), self.assertRaises(Text2SqlInvalidRequest):
                self.compile(group_by=[region], order_by=[QueryOrder(by=by)])

    def test_limit_is_capped_by_server_configuration(self) -> None:
        query = compile_query(self.context, self.connection.id, QueryPlan(metric_id=self.revenue.id, limit=5000), 200)
        self.assertEqual((query.limit, query.parameters["p0"]), (200, 201))

    def test_only_runnable_metrics_compile(self) -> None:
        with self.assertRaises(Text2SqlEntityNotFound):
            self.compile(metric_id=uuid4())
        with self.assertRaises(Text2SqlMetricNotRunnable):
            self.compile(metric_id=self.virtual.id)
        with self.assertRaises(Text2SqlMetricNotRunnable):
            self.compile(metric_id=self.sleepy.id)

    def test_type_categories(self) -> None:
        expected = {
            "INTEGER": "numeric", "bigint": "numeric", "NUMERIC(18,2)": "numeric", "double precision": "numeric",
            "serial": "numeric", "character varying(255)": "text", "TEXT": "text", "boolean": "boolean",
            "DATE": "date", "timestamp without time zone": "timestamp", "timestamp with time zone": "timestamp",
            "uuid": "uuid", "jsonb": "other", "interval": "other", "point": "other", "bytea": "other",
        }
        for data_type, category in expected.items():
            with self.subTest(data_type):
                self.assertEqual(type_category(data_type), category)


if __name__ == "__main__":
    unittest.main()
