import os
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
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
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.common.errors import Text2SqlConnectionNotFound, Text2SqlInvalidRequest
from backend.modules.text2sql.dataset.compiler import compile_dataset_query, normalize_alias
from backend.modules.text2sql.dataset.join_graph import JoinGraph
from backend.modules.text2sql.dataset.schemas import DatasetQueryPlan
from backend.modules.text2sql.dataset.service import DatasetQueryService
from backend.modules.text2sql.query.executor import RawResult, run_read_only
from backend.modules.text2sql.vector_store.ingestion.documents.context import load_context

register_all_models()

SERVER_URL = os.environ.get("POSTGRES_TEST_URL")
LAYOUT: dict[str, list[tuple[str, str, str]]] = {
    "customers": [
        ("id", "integer", "pk"), ("name", "text", ""), ("email", "text", "pii"), ("credit", "numeric", ""),
        ("region", "text", ""), ("born_on", "date", "pii"),
    ],
    "orders": [
        ("id", "integer", "pk"), ("customer_id", "integer", "ref:customers.id"), ("total", "numeric(12,2)", ""),
        ("created_at", "date", ""), ("status", "text", ""),
    ],
    "items": [
        ("id", "integer", "pk"), ("order_id", "integer", "ref:orders.id"), ("product_id", "integer", "ref:products.id"),
        ("qty", "integer", ""),
    ],
    "products": [("id", "integer", "pk"), ("title", "text", ""), ("category", "text", "")],
    "payments": [("order_id", "integer", "ref:orders.id"), ("amount", "numeric", "")],
    "weather": [("day", "date", ""), ("temp", "numeric", "")],
    "vouchers": [("code", "text", "uq"), ("amount", "numeric", "")],
    "voucher_uses": [("id", "integer", "pk"), ("voucher_code", "text", "ref:vouchers.code"), ("qty", "integer", "")],
    "coupons": [("code", "text", "uq!"), ("amount", "numeric", "")],
    "coupon_uses": [("id", "integer", "pk"), ("coupon_code", "text", "ref:coupons.code"), ("qty", "integer", "")],
}


class DatasetCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        self.connection = DatabaseConnection(
            name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext=self.ciphertext(),
        )
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.t: dict[str, DatabaseTable] = {}
        self.c: dict[str, DatabaseColumn] = {}
        dictionaries: dict[str, ColumnDictionary] = {}
        for table_name, columns in LAYOUT.items():
            table = DatabaseTable(schema_id=schema.id, name=table_name, table_type="TABLE")
            s.add(table)
            s.flush()
            self.t[table_name] = table
            s.add(TableDictionary(table_id=table.id, display_name=table_name.title()))
            for position, (name, data_type, flags) in enumerate(columns, start=1):
                column = DatabaseColumn(
                    table_id=table.id, name=name, data_type=data_type, ordinal_position=position,
                    is_nullable=flags != "uq!",
                )
                s.add(column)
                s.flush()
                self.c[f"{table_name}.{name}"] = column
                dictionaries[f"{table_name}.{name}"] = ColumnDictionary(
                    column_id=column.id, display_name=f"{table_name}.{name}", is_primary_key=flags == "pk" or None,
                    is_unique=flags.startswith("uq"), contains_pii=flags == "pii",
                )
                s.add(dictionaries[f"{table_name}.{name}"])
        s.flush()
        for table_name, columns in LAYOUT.items():
            for name, _, flags in columns:
                if flags.startswith("ref:"):
                    dictionaries[f"{table_name}.{name}"].referenced_column_id = self.c[flags[4:]].id
        s.flush()

    def ciphertext(self) -> str:
        return "x"

    def join(self, *tables: str, root: str | None = None):
        graph = JoinGraph(load_context(self.session, self.connection.id))
        plan = graph.plan([self.t[name].id for name in tables], root=self.t[root].id if root else None)
        self.assertEqual(plan.status, "ok", plan.message)
        return plan.options[0]

    def col(self, key: str) -> str:
        return str(self.c[key].id)

    def compile(self, tables: tuple[str, ...], root: str | None = None, max_rows: int = 1000, **plan):
        context = load_context(self.session, self.connection.id)
        return compile_dataset_query(
            context, self.connection.id, self.join(*tables, root=root), DatasetQueryPlan(**plan), max_rows,
        )


class DatasetCompilerTests(DatasetCatalog):
    def test_raw_rows_use_aliased_quoted_columns_and_bound_values(self) -> None:
        compiled = self.compile(
            ("orders",), select=[{"column_id": self.col("orders.id")}, {"column_id": self.col("orders.total")}],
            filters=[{"column_id": self.col("orders.status"), "operator": "equals", "value": "paid"}], limit=5,
        )
        self.assertFalse(compiled.grouped)
        self.assertEqual(
            compiled.sql,
            'SELECT t1."id" AS "orders_id", t1."total" AS "orders_total" FROM "public"."orders" AS t1 '
            'WHERE (t1."status" = :p0) LIMIT :p1',
        )
        self.assertEqual(compiled.parameters, {"p0": "paid", "p1": 6})
        self.assertEqual(compiled.limit, 5)

    def test_limit_is_capped_by_max_rows(self) -> None:
        compiled = self.compile(("orders",), max_rows=20, select=[{"column_id": self.col("orders.id")}], limit=500)
        self.assertEqual(compiled.limit, 20)
        self.assertEqual(compiled.parameters["p0"], 21)

    def test_where_filter_on_joined_table_goes_to_where(self) -> None:
        compiled = self.compile(
            ("customers", "orders"), root="customers",
            select=[{"column_id": self.col("customers.name")},
                    {"column_id": self.col("orders.id"), "aggregation": "count", "alias": "so_don"}],
            group_by=[self.col("customers.name")],
            filters=[{"column_id": self.col("orders.created_at"), "operator": "greater_than_or_equal",
                      "value": "2026-01-01"}],
        )
        self.assertIn('LEFT JOIN "public"."orders" AS t2 ON t2."customer_id" = t1."id" WHERE (t2."created_at" >= :p0)',
                      compiled.sql)
        self.assertIn('COUNT("_v1") AS "so_don"', compiled.sql)
        self.assertEqual(compiled.parameters["p0"], date(2026, 1, 1))

    def test_join_placement_moves_the_condition_into_on(self) -> None:
        compiled = self.compile(
            ("customers", "orders"), root="customers",
            select=[{"column_id": self.col("customers.name")},
                    {"column_id": self.col("orders.id"), "aggregation": "count", "alias": "so_don"}],
            group_by=[self.col("customers.name")],
            filters=[{"column_id": self.col("orders.created_at"), "operator": "greater_than_or_equal",
                      "value": "2026-01-01", "placement": "join"}],
        )
        self.assertIn('ON t2."customer_id" = t1."id" AND (t2."created_at" >= :p0)', compiled.sql)
        self.assertNotIn("WHERE", compiled.sql)

    def test_join_placement_is_rejected_for_root_columns(self) -> None:
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "bảng gốc"):
            self.compile(
                ("customers", "orders"), root="customers", select=[{"column_id": self.col("customers.name")}],
                filters=[{"column_id": self.col("customers.region"), "operator": "equals", "value": "Bắc",
                          "placement": "join"}],
            )

    def test_columns_outside_the_join_are_rejected(self) -> None:
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "không thuộc các bảng"):
            self.compile(("orders",), select=[{"column_id": self.col("weather.temp")}])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "không thuộc các bảng"):
            self.compile(("orders",), select=[{"column_id": self.col("orders.id")}],
                         filters=[{"column_id": self.col("customers.region"), "operator": "equals", "value": "x"}])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "không nằm trong phương án nối"):
            self.compile(("orders",), select=[{"expression": "SUM(customers.credit)"}])

    def test_unsafe_expressions_are_rejected(self) -> None:
        bad = [
            "SUM(pg_sleep(1))", "SUM(orders.total); DROP TABLE orders", "(SELECT 1)",
            "SUM((SELECT max(total) FROM orders))", "SUM(orders.*)", "SUM(total)", "SUM(public.orders.total)",
            "SUM(CAST(orders.total AS bytea))", "SUM(SUM(orders.total))", "orders.total + SUM(orders.total)",
            "COUNT(customers.email)", "SUM(orders.nope)", "COUNT(DISTINCT orders.id, orders.status)",
            "SUM(orders.total) OVER ()", "version()", "",
        ]
        for expression in bad:
            with self.subTest(expression=expression), self.assertRaises(Text2SqlInvalidRequest):
                self.compile(("customers", "orders"), root="orders", select=[{"expression": expression}])

    def test_expression_literals_are_bound_and_columns_are_quoted(self) -> None:
        compiled = self.compile(
            ("orders",), select=[{
                "expression": "SUM(CASE WHEN orders.status = 'x''; DROP TABLE orders; --' THEN orders.total * 1.5 "
                              "ELSE 0 END)",
                "alias": "Doanh thu",
            }],
        )
        self.assertNotIn("DROP", compiled.sql)
        self.assertNotIn("'", compiled.sql)
        self.assertIn('CASE WHEN t1."status" = :p1 THEN t1."total" * :p2 ELSE :p0 END AS "_v1"', compiled.sql)
        self.assertEqual(compiled.parameters["p1"], "x'; DROP TABLE orders; --")
        self.assertEqual(compiled.parameters["p2"], Decimal("1.5"))
        self.assertEqual(compiled.parameters["p0"], 0)
        self.assertEqual(compiled.columns[0].alias, "doanh_thu")

    def test_row_expressions_are_allowed_only_without_grouping(self) -> None:
        compiled = self.compile(("orders",), select=[{"expression": "orders.total * 2", "alias": "gap_doi"}])
        self.assertIn('t1."total" * :p0 AS "gap_doi"', compiled.sql)
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "không có hàm tổng hợp"):
            self.compile(("orders",), select=[{"expression": "orders.total * 2"}, {"expression": "COUNT(*)"}])

    def test_ambiguous_table_names_in_expressions_are_rejected(self) -> None:
        s = self.session
        archive = DatabaseSchema(connection_id=self.connection.id, name="archive")
        s.add(archive)
        s.flush()
        old = DatabaseTable(schema_id=archive.id, name="orders", table_type="TABLE")
        s.add(old)
        s.flush()
        old_id, ref = (
            DatabaseColumn(table_id=old.id, name=name, data_type="integer", ordinal_position=position, is_nullable=True)
            for position, name in ((1, "id"), (2, "customer_id"))
        )
        s.add_all([old_id, ref])
        s.flush()
        s.add_all([
            ColumnDictionary(column_id=old_id.id, display_name="id", is_primary_key=True),
            ColumnDictionary(column_id=ref.id, display_name="c", referenced_column_id=self.c["customers.id"].id),
        ])
        s.flush()
        self.t["old_orders"] = old
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "mơ hồ"):
            self.compile(("orders", "old_orders", "customers"), root="customers",
                         select=[{"expression": "COUNT(orders.id)"}])

    def test_pii_rules(self) -> None:
        compiled = self.compile(("customers",), select=[{"column_id": self.col("customers.email")}])
        self.assertEqual(compiled.pii_columns, ["customers_email"])
        self.assertTrue(compiled.columns[0].spec.contains_pii)
        counted = self.compile(("customers",), select=[
            {"column_id": self.col("customers.email"), "aggregation": "count_distinct"},
            {"column_id": self.col("customers.born_on"), "aggregation": "min"},
        ])
        self.assertEqual(counted.pii_columns, ["min_customers_born_on"])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "dữ liệu cá nhân"):
            self.compile(("customers",), select=[{"column_id": self.col("customers.name")}],
                         filters=[{"column_id": self.col("customers.email"), "operator": "equals", "value": "a@b.c"}])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "dữ liệu cá nhân"):
            self.compile(("customers",), select=[{"expression": "COUNT(*)"}],
                         time={"column_id": self.col("customers.born_on"), "granularity": "year"})

    def test_plain_columns_must_be_grouped_when_aggregating(self) -> None:
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "group_by"):
            self.compile(("orders",), select=[{"column_id": self.col("orders.status")}, {"expression": "COUNT(*)"}])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "trùng"):
            self.compile(("orders",), select=[{"expression": "COUNT(*)"}],
                         group_by=[self.col("orders.status"), self.col("orders.status")])

    def test_group_by_columns_not_selected_are_still_returned(self) -> None:
        compiled = self.compile(("orders",), select=[{"expression": "COUNT(*)", "alias": "so_don"}],
                                group_by=[self.col("orders.status")])
        self.assertEqual([column.alias for column in compiled.columns], ["orders_status", "so_don"])
        self.assertIn('GROUP BY "_g1" ORDER BY "so_don" DESC NULLS LAST', compiled.sql)

    def test_user_aliases_are_normalized_and_deduplicated(self) -> None:
        self.assertEqual(normalize_alias('x"; DROP TABLE t; --'), "x_drop_table_t")
        self.assertEqual(normalize_alias("Số đơn hàng"), "so_don_hang")
        compiled = self.compile(("orders",), select=[
            {"column_id": self.col("orders.id"), "alias": 'a" FROM pg_user --'},
            {"column_id": self.col("orders.total"), "alias": "a_from_pg_user"},
            {"column_id": self.col("orders.status"), "alias": "time_bucket"},
            {"column_id": self.col("orders.created_at"), "alias": "\"\"\""},
        ])
        self.assertEqual([column.alias for column in compiled.columns],
                         ["a_from_pg_user", "a_from_pg_user_2", "time_bucket_2", "orders_created_at"])
        self.assertNotIn("pg_user --", compiled.sql)

    def test_sum_of_the_one_side_is_deduplicated_when_a_join_multiplies_rows(self) -> None:
        compiled = self.compile(("orders", "items"), root="orders", select=[
            {"column_id": self.col("orders.total"), "aggregation": "sum", "alias": "doanh_thu"},
            {"column_id": self.col("items.qty"), "aggregation": "sum", "alias": "so_luong"},
            {"expression": "COUNT(*)", "alias": "so_don"},
        ])
        self.assertIn(
            'CASE WHEN t1."id" IS NOT NULL THEN ROW_NUMBER() OVER (PARTITION BY t1."id") END AS "_r1"', compiled.sql,
        )
        self.assertIn('SUM(CASE WHEN "_r1" = 1 THEN "_v1" END) AS "doanh_thu"', compiled.sql)
        self.assertIn('SUM("_v2") AS "so_luong"', compiled.sql)
        self.assertIn('COUNT(CASE WHEN "_r1" = 1 THEN 1 END) AS "so_don"', compiled.sql)
        self.assertTrue(any("khử trùng lặp" in warning for warning in compiled.warnings))

    def test_dedup_keys_follow_the_path_from_the_root(self) -> None:
        compiled = self.compile(("customers", "orders", "items", "products"), root="customers", select=[
            {"column_id": self.col("orders.total"), "aggregation": "sum"},
            {"column_id": self.col("orders.total"), "aggregation": "max"},
            {"column_id": self.col("orders.id"), "aggregation": "count_distinct"},
        ], group_by=[self.col("products.category")])
        self.assertIn('PARTITION BY t4."category", t1."id", t2."id"', compiled.sql)
        self.assertIn('MAX("_v2")', compiled.sql)
        self.assertIn('COUNT(DISTINCT "_v3")', compiled.sql)
        self.assertEqual(compiled.sql.count("ROW_NUMBER"), 1)

    def test_fan_out_without_primary_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "khóa chính"):
            self.compile(("payments", "orders", "items"), root="payments",
                         select=[{"column_id": self.col("payments.amount"), "aggregation": "sum"}])
        compiled = self.compile(("payments", "orders", "items"), root="payments",
                                select=[{"column_id": self.col("payments.amount"), "aggregation": "max"}])
        self.assertNotIn("ROW_NUMBER", compiled.sql)

    def test_many_to_one_sums_warn_about_the_root_grain(self) -> None:
        compiled = self.compile(("orders", "customers"), root="orders",
                                select=[{"column_id": self.col("customers.credit"), "aggregation": "sum"}])
        self.assertNotIn("ROW_NUMBER", compiled.sql)
        self.assertTrue(any("mỗi dòng của bảng gốc" in warning for warning in compiled.warnings))

    def test_nullable_unique_column_is_not_a_dedup_key(self) -> None:
        for aggregate in ({"column_id": self.col("vouchers.amount"), "aggregation": "sum"}, {"expression": "COUNT(*)"}):
            with self.subTest(aggregate=aggregate), self.assertRaisesRegex(Text2SqlInvalidRequest, "khóa chính"):
                self.compile(("vouchers", "voucher_uses"), root="vouchers", select=[aggregate])
        compiled = self.compile(("coupons", "coupon_uses"), root="coupons",
                                select=[{"column_id": self.col("coupons.amount"), "aggregation": "sum"}])
        self.assertIn('ROW_NUMBER() OVER (PARTITION BY t1."code")', compiled.sql)

    def test_aggregate_mixing_an_ancestor_with_a_fanned_out_table_is_rejected(self) -> None:
        for expression in ("SUM(CASE WHEN items.qty >= 1 THEN orders.total END)", "COUNT(orders.id + items.qty)",
                           "AVG(items.qty * customers.credit)"):
            with self.subTest(expression=expression), self.assertRaisesRegex(Text2SqlInvalidRequest, "bảng gốc"):
                self.compile(("orders", "items", "customers"), root="orders", select=[{"expression": expression}])
        compiled = self.compile(("orders", "items"), root="orders", select=[
            {"expression": "MAX(CASE WHEN items.qty >= 1 THEN orders.total END)"},
            {"expression": "COUNT(DISTINCT CASE WHEN items.qty >= 1 THEN orders.id END)"},
        ])
        self.assertNotIn("ROW_NUMBER", compiled.sql)
        compiled = self.compile(("items", "orders"), root="items",
                                select=[{"expression": "SUM(CASE WHEN items.qty >= 1 THEN orders.total END)"}])
        self.assertNotIn("ROW_NUMBER", compiled.sql)

    def test_aggregate_crossing_two_fanned_out_branches_is_rejected(self) -> None:
        for expression in ("SUM(items.qty + payments.amount)", "MAX(items.qty + payments.amount)",
                           "COUNT(DISTINCT items.qty + payments.amount)"):
            with self.subTest(expression=expression), self.assertRaisesRegex(Text2SqlInvalidRequest, "nhân chéo"):
                self.compile(("orders", "items", "payments"), root="orders", select=[{"expression": expression}])
        compiled = self.compile(("orders", "items", "payments"), root="orders",
                                select=[{"expression": "SUM(items.qty)"}, {"expression": "MAX(payments.amount)"}])
        self.assertIn("ROW_NUMBER", compiled.sql)

    def test_time_bucket_and_range(self) -> None:
        compiled = self.compile(("orders",), select=[{"column_id": self.col("orders.total"), "aggregation": "sum"}],
                                time={"column_id": self.col("orders.created_at"), "granularity": "month",
                                      "start": "2026-01-01", "end": "2026-04-01"})
        self.assertIn('''CAST(date_trunc('month', t1."created_at") AS date) AS "_g0"''', compiled.sql)
        self.assertIn('(t1."created_at" >= :p0) AND (t1."created_at" < :p1)', compiled.sql)
        self.assertIn('ORDER BY "time_bucket" ASC NULLS LAST', compiled.sql)
        self.assertEqual(compiled.columns[0].spec.role, "time")
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "start"):
            self.compile(("orders",), select=[{"expression": "COUNT(*)"}],
                         time={"column_id": self.col("orders.created_at"), "start": "2026-02-01", "end": "2026-01-01"})

    def test_order_by_accepts_alias_or_column_id_only(self) -> None:
        compiled = self.compile(("orders",), select=[
            {"column_id": self.col("orders.status")}, {"expression": "COUNT(*)", "alias": "so_don"},
        ], group_by=[self.col("orders.status")], order_by=[
            {"by": "so_don", "direction": "asc"}, {"by": self.col("orders.status")},
        ])
        self.assertIn('ORDER BY "so_don" ASC NULLS LAST, "orders_status" DESC NULLS LAST', compiled.sql)
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "order_by"):
            self.compile(("orders",), select=[{"column_id": self.col("orders.id")}],
                         order_by=[{"by": "1; DROP TABLE orders"}])

    def test_select_item_needs_exactly_one_source(self) -> None:
        for item in ({}, {"column_id": self.col("orders.id"), "expression": "COUNT(*)"},
                     {"expression": "COUNT(*)", "aggregation": "sum"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                DatasetQueryPlan(select=[item])
        with self.assertRaises(ValueError):
            DatasetQueryPlan(select=[{"expression": "COUNT(*)"}], filters=[], unknown=1)

    def test_tampered_join_option_is_rejected(self) -> None:
        option = self.join("customers", "orders", root="customers")
        context = load_context(self.session, self.connection.id)
        plan = DatasetQueryPlan(select=[{"column_id": self.col("customers.name")}])
        broken = option.model_copy(update={"steps": [option.steps[0].model_copy(update={"alias": "t2; DROP"})]})
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "plan_join"):
            compile_dataset_query(context, self.connection.id, broken, plan, 100)


class FakeMasker:
    def mask(self, columns, rows):
        return rows, SimpleNamespace(masked_columns=[], detected={})


class DatasetServiceTests(DatasetCatalog):
    def test_prepare_and_execute_with_a_runner(self) -> None:
        calls = []

        def runner(url, sql, parameters, expanding, max_rows, timeout):
            calls.append((sql, parameters, max_rows))
            return RawResult(columns=["orders_status", "so_don"], rows=[("paid", 3), ("refund", 1), ("x", 1)],
                             elapsed_ms=4)

        service = DatasetQueryService(self.session, runner=runner, masker=FakeMasker())
        compiled = service.prepare(self.connection.id, self.join("orders"), DatasetQueryPlan(
            select=[{"column_id": self.col("orders.status")}, {"expression": "COUNT(*)", "alias": "so_don"}],
            group_by=[self.col("orders.status")], limit=2,
        ))
        result = service.execute(compiled, make_url("postgresql+psycopg://u@h/d"))
        self.assertEqual(calls[0][2], 3)
        self.assertEqual(result.rows, [["paid", 3], ["refund", 1]])
        self.assertTrue(result.truncated)
        self.assertEqual(result.parameters, {"p0": 3})

    def test_unknown_connection(self) -> None:
        service = DatasetQueryService(self.session, masker=FakeMasker())
        with self.assertRaises(Text2SqlConnectionNotFound):
            service.prepare(uuid4(), self.join("orders"), DatasetQueryPlan(select=[{"expression": "COUNT(*)"}]))


SOURCE_DDL = [
    "CREATE TABLE customers (id integer PRIMARY KEY, name text, email text, credit numeric, region text, born_on date)",
    "CREATE TABLE products (id integer PRIMARY KEY, title text, category text)",
    "CREATE TABLE orders (id integer PRIMARY KEY, customer_id integer REFERENCES customers, total numeric(12,2), "
    "created_at date, status text)",
    "CREATE TABLE items (id integer PRIMARY KEY, order_id integer REFERENCES orders, "
    "product_id integer REFERENCES products, qty integer)",
    "CREATE TABLE payments (order_id integer, amount numeric)",
    "CREATE TABLE weather (day date, temp numeric)",
    "INSERT INTO customers VALUES (1, 'An', 'an@example.com', 100, 'Bắc', '1990-01-01'), "
    "(2, 'Bình', 'binh@example.com', 200, 'Nam', '1991-01-01'), (3, 'Chi', 'chi@example.com', 300, 'Bắc', NULL)",
    "INSERT INTO products VALUES (1, 'Táo', 'fruit'), (2, 'Bút', 'office')",
    "INSERT INTO orders VALUES (10, 1, 100, '2026-01-05', 'paid'), (11, 1, 50, '2025-12-20', 'paid'), "
    "(12, 2, 70, '2026-02-10', 'refund'), (13, 2, 30, '2026-02-15', 'paid')",
    "INSERT INTO items VALUES (100, 10, 1, 2), (101, 10, 2, 1), (102, 10, 1, 3), (103, 12, 2, 1)",
    "INSERT INTO payments VALUES (10, 5), (10, 6), (12, 7)",
    "CREATE TABLE vouchers (code text UNIQUE, amount numeric)",
    "CREATE TABLE voucher_uses (id integer PRIMARY KEY, voucher_code text, qty integer)",
    "CREATE TABLE coupons (code text NOT NULL UNIQUE, amount numeric)",
    "CREATE TABLE coupon_uses (id integer PRIMARY KEY, coupon_code text, qty integer)",
    "INSERT INTO vouchers VALUES ('A', 10), (NULL, 5), (NULL, 7)",
    "INSERT INTO voucher_uses VALUES (1, 'A', 1), (2, 'A', 2)",
    "INSERT INTO coupons VALUES ('A', 10), ('B', 5), ('C', 7)",
    "INSERT INTO coupon_uses VALUES (1, 'A', 1), (2, 'A', 2)",
]


@unittest.skipUnless(SERVER_URL, "Đặt POSTGRES_TEST_URL tới một PostgreSQL dùng để thử nghiệm (được tạo database tạm).")
class DatasetPostgresTests(DatasetCatalog):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = create_engine(make_url(SERVER_URL), isolation_level="AUTOCOMMIT")
        cls.database = f"t2s_dataset_{uuid4().hex[:12]}"
        with cls.admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{cls.database}"'))
        cls.source_url = make_url(SERVER_URL).set(database=cls.database)
        source = create_engine(cls.source_url)
        with source.begin() as connection:
            for statement in SOURCE_DDL:
                connection.execute(text(statement))
        source.dispose()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{cls.database}" WITH (FORCE)'))
        cls.admin.dispose()

    def run_plan(self, tables: tuple[str, ...], root: str | None = None, **plan) -> list[tuple]:
        compiled = self.compile(tables, root=root, **plan)
        raw = run_read_only(self.source_url, compiled.sql, compiled.parameters, compiled.expanding,
                            compiled.limit + 1, 10)
        return raw.rows

    def naive(self, sql: str) -> list[tuple]:
        return run_read_only(self.source_url, sql, {}, frozenset(), 100, 10).rows

    def test_sum_of_the_one_side_is_not_double_counted(self) -> None:
        self.assertEqual(self.naive(
            "SELECT SUM(o.total) FROM orders o LEFT JOIN items i ON i.order_id = o.id"
        ), [(Decimal("450.00"),)])
        rows = self.run_plan(("orders", "items"), root="orders", select=[
            {"column_id": self.col("orders.total"), "aggregation": "sum"},
            {"column_id": self.col("items.qty"), "aggregation": "sum"},
            {"expression": "COUNT(*)"},
            {"expression": "AVG(orders.total)"},
        ])
        self.assertEqual(rows, [(Decimal("250.00"), 7, 4, Decimal("62.5"))])

    def test_grouped_dedup_and_literals(self) -> None:
        rows = self.run_plan(("orders", "items"), root="orders", select=[
            {"column_id": self.col("orders.status")},
            {"expression": "SUM(CASE WHEN orders.status = 'paid' THEN orders.total ELSE 0 END)", "alias": "paid"},
            {"column_id": self.col("orders.total"), "aggregation": "sum", "alias": "total"},
        ], group_by=[self.col("orders.status")], order_by=[{"by": "total"}])
        self.assertEqual(rows, [("paid", Decimal("180.00"), Decimal("180.00")),
                                ("refund", Decimal("0"), Decimal("70.00"))])

    def test_one_side_sum_with_customer_root(self) -> None:
        rows = self.run_plan(("customers", "orders"), root="customers", select=[
            {"column_id": self.col("customers.region")},
            {"column_id": self.col("customers.credit"), "aggregation": "sum", "alias": "credit"},
            {"column_id": self.col("orders.total"), "aggregation": "sum", "alias": "spent"},
        ], group_by=[self.col("customers.region")], order_by=[{"by": "customers_region", "direction": "asc"}])
        self.assertEqual(rows, [("Bắc", Decimal("400"), Decimal("150.00")), ("Nam", Decimal("200"), Decimal("100.00"))])

    def test_group_by_a_far_dimension_counts_each_order_once(self) -> None:
        rows = self.run_plan(("customers", "orders", "items", "products"), root="customers", select=[
            {"column_id": self.col("products.category")},
            {"column_id": self.col("orders.total"), "aggregation": "sum", "alias": "total"},
        ], group_by=[self.col("products.category")], order_by=[{"by": "products_category", "direction": "asc"}])
        self.assertEqual(rows, [("fruit", Decimal("100.00")), ("office", Decimal("170.00")),
                                (None, Decimal("80.00"))])

    def test_join_placement_keeps_unmatched_root_rows(self) -> None:
        common = dict(
            select=[{"column_id": self.col("customers.name")},
                    {"column_id": self.col("orders.id"), "aggregation": "count", "alias": "so_don"}],
            group_by=[self.col("customers.name")], order_by=[{"by": "customers_name", "direction": "asc"}],
        )
        condition = {"column_id": self.col("orders.created_at"), "operator": "greater_than_or_equal",
                     "value": "2026-01-01"}
        kept = self.run_plan(("customers", "orders"), root="customers",
                             filters=[condition | {"placement": "join"}], **common)
        dropped = self.run_plan(("customers", "orders"), root="customers", filters=[condition], **common)
        self.assertEqual(kept, [("An", 1), ("Bình", 2), ("Chi", 0)])
        self.assertEqual(dropped, [("An", 1), ("Bình", 2)])

    def test_left_join_keeps_unmatched_rows_in_raw_mode(self) -> None:
        rows = self.run_plan(("customers", "orders"), root="customers", select=[
            {"column_id": self.col("customers.name")}, {"column_id": self.col("orders.id")},
        ], order_by=[{"by": "orders_id", "direction": "asc"}])
        self.assertEqual(rows, [("An", 10), ("An", 11), ("Bình", 12), ("Bình", 13), ("Chi", None)])

    def test_time_buckets_with_fan_out(self) -> None:
        rows = self.run_plan(("orders", "items"), root="orders", select=[
            {"column_id": self.col("orders.total"), "aggregation": "sum"},
        ], time={"column_id": self.col("orders.created_at"), "granularity": "month", "end": "2026-03-01"})
        self.assertEqual(rows, [(date(2025, 12, 1), Decimal("50.00")), (date(2026, 1, 1), Decimal("100.00")),
                                (date(2026, 2, 1), Decimal("100.00"))])

    def test_nullable_unique_key_is_rejected_instead_of_undercounting(self) -> None:
        self.assertEqual(self.naive("SELECT SUM(amount), COUNT(*) FROM vouchers"), [(Decimal("22"), 3)])
        for aggregate in ({"column_id": self.col("vouchers.amount"), "aggregation": "sum"}, {"expression": "COUNT(*)"}):
            with self.subTest(aggregate=aggregate), self.assertRaisesRegex(Text2SqlInvalidRequest, "NOT NULL"):
                self.run_plan(("vouchers", "voucher_uses"), root="vouchers", select=[aggregate])
        rows = self.run_plan(("coupons", "coupon_uses"), root="coupons", select=[
            {"column_id": self.col("coupons.amount"), "aggregation": "sum"}, {"expression": "COUNT(*)"},
            {"column_id": self.col("coupon_uses.qty"), "aggregation": "sum"},
        ])
        self.assertEqual(rows, [(Decimal("22"), 3, 3)])

    def test_ancestor_value_conditioned_on_a_fanned_out_table_is_rejected(self) -> None:
        self.assertEqual(self.naive(
            "SELECT SUM(CASE WHEN i.qty >= 1 THEN o.total END) FROM orders o LEFT JOIN items i ON i.order_id = o.id"
        ), [(Decimal("370.00"),)])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "bảng gốc"):
            self.run_plan(("orders", "items"), root="orders",
                          select=[{"expression": "SUM(CASE WHEN items.qty >= 1 THEN orders.total END)"}])
        rows = self.run_plan(("orders", "items"), root="orders", select=[
            {"expression": "MAX(CASE WHEN items.qty >= 1 THEN orders.total END)"},
            {"expression": "COUNT(DISTINCT CASE WHEN items.qty >= 1 THEN orders.id END)"},
        ])
        self.assertEqual(rows, [(Decimal("100.00"), 2)])

    def test_aggregate_across_two_fanned_out_branches_is_rejected(self) -> None:
        self.assertEqual(self.naive(
            "SELECT SUM(i.qty + p.amount) FROM orders o LEFT JOIN items i ON i.order_id = o.id "
            "LEFT JOIN payments p ON p.order_id = o.id"
        ), [(Decimal("53"),)])
        with self.assertRaisesRegex(Text2SqlInvalidRequest, "nhân chéo"):
            self.run_plan(("orders", "items", "payments"), root="orders",
                          select=[{"expression": "SUM(items.qty + payments.amount)"}])
        rows = self.run_plan(("orders", "items", "payments"), root="orders", select=[
            {"expression": "SUM(items.qty)"}, {"expression": "MAX(payments.amount)"},
            {"column_id": self.col("orders.total"), "aggregation": "sum"},
        ])
        self.assertEqual(rows, [(7, Decimal("7"), Decimal("250.00"))])

    def test_service_masks_pii_columns(self) -> None:
        service = DatasetQueryService(self.session)
        compiled = service.prepare(self.connection.id, self.join("customers"), DatasetQueryPlan(
            select=[{"column_id": self.col("customers.name")}, {"column_id": self.col("customers.email")}],
            order_by=[{"by": "customers_name", "direction": "asc"}],
        ))
        result = service.execute(compiled, self.source_url)
        self.assertEqual(result.row_count, 3)
        self.assertEqual(result.rows[0][0], "An")
        self.assertNotIn("an@example.com", str(result.rows))
        self.assertIn("customers_email", result.pii.masked_columns)


if __name__ == "__main__":
    unittest.main()
