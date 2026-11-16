import asyncio
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from mcp.client import Client
from mcp.types import ElicitResult
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.mcp_server.server import mcp
from backend.mcp_server.tools import dataset as dataset_tool
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.common.errors import (
    Text2SqlInvalidRequest,
    Text2SqlQueryFailed,
    Text2SqlQueryTimeout,
)
from backend.modules.text2sql.dataset.schemas import DatasetResult
from backend.modules.text2sql.dataset.service import DatasetQueryService
from backend.modules.text2sql.dataset.store import DatasetStore
from backend.modules.text2sql.models import QueryDataset
from backend.modules.text2sql.models.query_dataset import MAX_SELECTED_COLUMNS
from backend.modules.text2sql.query.schemas import PiiReport

register_all_models()

LAYOUT = {
    "customers": [("id", "integer"), ("name", "text"), ("region", "text")],
    "locations": [("id", "integer"), ("city", "text")],
    "orders": [("id", "integer"), ("customer_id", "integer"), ("ship_from", "integer"), ("ship_to", "integer"),
               ("total", "numeric(12,2)")],
    "weather": [("day", "date"), ("temp", "numeric")],
}
RELATIONS = [
    ("orders.customer_id", "customers.id"), ("orders.ship_from", "locations.id"), ("orders.ship_to", "locations.id"),
]


class QueryDatasetToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.build_catalog()
        self.executed: list[tuple] = []

        @contextmanager
        def fake_session():
            yield self.session

        def fake_execute(stored, confirmation):
            self.executed.append((stored, confirmation))
            return DatasetResult(
                columns=[column.spec for column in stored.compiled.columns], rows=[], row_count=0, truncated=False,
                limit=stored.compiled.limit, sql=stored.compiled.sql, parameters={},
                pii=PiiReport(confirmation=confirmation), elapsed_ms=1, warnings=stored.compiled.warnings,
            )

        for patcher in (
            patch.object(dataset_tool, "detail_session", fake_session),
            patch.object(dataset_tool, "run_execute", fake_execute),
            patch.object(DatasetQueryService, "resolve_source", lambda service, connection_id: make_url("sqlite://")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def build_catalog(self) -> None:
        s = self.session
        self.connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.t, self.c, dictionaries = {}, {}, {}
        for table_name, columns in LAYOUT.items():
            table = DatabaseTable(schema_id=schema.id, name=table_name, table_type="TABLE")
            s.add(table)
            s.flush()
            self.t[table_name] = table
            s.add(TableDictionary(table_id=table.id, display_name=table_name.title()))
            for position, (column_name, data_type) in enumerate(columns, start=1):
                column = DatabaseColumn(
                    table_id=table.id, name=column_name, data_type=data_type, ordinal_position=position,
                    is_nullable=True,
                )
                s.add(column)
                s.flush()
                key = f"{table_name}.{column_name}"
                self.c[key] = column
                dictionaries[key] = ColumnDictionary(
                    column_id=column.id, display_name=key, is_primary_key=column_name == "id" or None,
                    contains_pii=key == "customers.name",
                )
                s.add(dictionaries[key])
        s.flush()
        for child, parent in RELATIONS:
            dictionaries[child].referenced_column_id = self.c[parent].id
        s.commit()

    def table_ids(self, *names: str) -> list[str]:
        return [str(self.t[name].id) for name in names]

    def column(self, key: str) -> str:
        return str(self.c[key].id)

    def arguments(self, tables: tuple[str, ...], plan: dict, **extra) -> dict:
        return {"connection_id": str(self.connection.id), "table_ids": self.table_ids(*tables), "plan": plan, **extra}

    def call(self, arguments: dict, answer: ElicitResult | None = None, supports_elicitation: bool = True):
        asked: list[str] = []

        async def elicit(context, params):
            asked.append(params.message)
            return answer

        async def run():
            options = {"elicitation_callback": elicit} if supports_elicitation else {}
            async with Client(mcp, **options) as client:
                return await client.call_tool("query_dataset", arguments)

        return asyncio.run(run()), asked

    def dataset_count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(QueryDataset))

    def revenue_by_region(self) -> dict:
        return {
            "select": [{"column_id": self.column("customers.region")},
                       {"column_id": self.column("orders.total"), "aggregation": "sum", "alias": "revenue"}],
            "group_by": [self.column("customers.region")],
        }

    def test_schema_takes_tables_and_a_plan_but_no_sql(self) -> None:
        async def check():
            async with Client(mcp) as client:
                tool = next(item for item in (await client.list_tools()).tools if item.name == "query_dataset")
                return getattr(tool, "input_schema", None) or tool.inputSchema

        schema = asyncio.run(check())
        self.assertEqual(set(schema["properties"]), {"connection_id", "table_ids", "root_table_id", "edge_ids", "plan"})
        self.assertEqual(sorted(schema["required"]), ["connection_id", "plan", "table_ids"])
        plan = schema["$defs"]["DatasetQueryPlan"]
        self.assertNotIn("from_sql", plan["properties"])
        self.assertIs(plan["additionalProperties"], False)

    def test_not_declared_is_a_structured_answer_asking_for_the_data_dictionary(self) -> None:
        plan = {"select": [{"column_id": self.column("orders.total"), "aggregation": "sum"}]}
        result, asked = self.call(self.arguments(("orders", "weather"), plan))
        self.assertFalse(result.is_error)
        content = result.structured_content
        self.assertEqual(content["status"], "not_declared")
        self.assertIn("data dictionary", content["message"])
        self.assertIn("bổ sung", content["message"])
        self.assertIsNone(content["dataset"])
        self.assertIsNone(content["result"])
        self.assertEqual((self.executed, asked, self.dataset_count()), ([], [], 0))

    def test_ambiguous_returns_options_then_the_chosen_edges_run(self) -> None:
        plan = {"select": [{"column_id": self.column("locations.city")},
                           {"column_id": self.column("orders.total"), "aggregation": "sum"}],
                "group_by": [self.column("locations.city")]}
        arguments = self.arguments(("orders", "locations"), plan, root_table_id=str(self.t["orders"].id))
        result, _ = self.call(arguments)
        content = result.structured_content
        self.assertFalse(result.is_error)
        self.assertEqual(content["status"], "ambiguous")
        self.assertEqual(len(content["options"]), 2)
        self.assertIn("edge_ids", content["message"])
        self.assertEqual((self.executed, self.dataset_count()), ([], 0))

        chosen = content["options"][1]
        result, _ = self.call({**arguments, "edge_ids": chosen["edge_ids"]})
        content = result.structured_content
        self.assertEqual(content["status"], "ok")
        self.assertEqual(content["join"]["signature"], chosen["signature"])
        self.assertTrue(content["dataset"]["created"])
        self.assertEqual(len(self.executed), 1)

    def test_ok_creates_a_dataset_and_the_same_join_reuses_it_adding_only_new_columns(self) -> None:
        first, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
        self.assertFalse(first.is_error, first.content)
        content = first.structured_content
        self.assertEqual(content["status"], "ok")
        self.assertTrue(content["dataset"]["created"])
        expected = [self.column("customers.region"), self.column("orders.total")]
        self.assertEqual(content["dataset"]["selected_column_ids"], expected)
        self.assertEqual(content["dataset"]["added_column_ids"], expected)
        self.assertEqual(content["result"]["pii"]["confirmation"], "not_required")
        self.assertIn("LEFT JOIN", content["result"]["sql"])

        plan = {
            "select": [
                {"column_id": self.column("customers.region")},
                {"expression": "SUM(orders.total) / NULLIF(COUNT(DISTINCT orders.customer_id), 0)", "alias": "avg"},
            ],
            "group_by": [self.column("customers.region")],
        }
        second, _ = self.call(self.arguments(("orders", "customers"), plan))
        content2 = second.structured_content
        self.assertFalse(second.is_error, second.content)
        self.assertFalse(content2["dataset"]["created"])
        self.assertEqual(content2["dataset"]["dataset_id"], content["dataset"]["dataset_id"])
        self.assertEqual(content2["dataset"]["added_column_ids"], [self.column("orders.customer_id")])
        self.assertEqual(content2["dataset"]["selected_column_ids"], [*expected, self.column("orders.customer_id")])
        self.assertEqual(self.dataset_count(), 1)

        third, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
        self.assertEqual(third.structured_content["dataset"]["added_column_ids"], [])

    def test_filters_alone_are_not_recorded_in_the_dataset(self) -> None:
        plan = {**self.revenue_by_region(), "filters": [
            {"column_id": self.column("orders.ship_to"), "operator": "equals", "value": 1, "placement": "join"},
        ]}
        arguments = self.arguments(("customers", "orders"), plan, root_table_id=str(self.t["customers"].id))
        result, _ = self.call(arguments)
        self.assertFalse(result.is_error, result.content)
        self.assertIn("AND (t2.", result.structured_content["result"]["sql"])
        self.assertNotIn(self.column("orders.ship_to"), result.structured_content["dataset"]["selected_column_ids"])

    def test_pii_selection_asks_for_consent(self) -> None:
        plan = {"select": [{"column_id": self.column("customers.name")}, {"column_id": self.column("orders.total")}]}
        arguments = self.arguments(("customers", "orders"), plan)
        result, asked = self.call(arguments, ElicitResult(action="accept", content={"proceed": True}))
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(len(asked), 1)
        self.assertIn("placeholder", asked[0])
        self.assertEqual(self.executed[-1][1], "confirmed")

        result, asked = self.call(arguments, supports_elicitation=False)
        self.assertFalse(result.is_error)
        self.assertEqual((asked, self.executed[-1][1]), ([], "not_supported"))

    def test_declined_consent_cancels_without_storing_anything(self) -> None:
        plan = {"select": [{"column_id": self.column("customers.name")}]}
        for answer in (ElicitResult(action="decline"), ElicitResult(action="accept", content={"proceed": False})):
            with self.subTest(action=answer.action):
                result, _ = self.call(self.arguments(("customers", "orders"), plan), answer)
                self.assertTrue(result.is_error)
                self.assertIn("hủy", result.content[0].text)
        self.assertEqual((self.executed, self.dataset_count()), ([], 0))

    def test_from_sql_is_never_accepted_from_the_client(self) -> None:
        injected = 'FROM "public"."weather" AS t1'
        plan = {**self.revenue_by_region(), "from_sql": injected}
        result, _ = self.call(self.arguments(("customers", "orders"), plan))
        self.assertTrue(result.is_error)
        self.assertEqual((self.executed, self.dataset_count()), ([], 0))

        arguments = {**self.arguments(("customers", "orders"), self.revenue_by_region()), "from_sql": injected,
                     "join": {"from_sql": injected}}
        result, _ = self.call(arguments)
        self.assertFalse(result.is_error, result.content)
        self.assertNotIn("weather", result.structured_content["result"]["sql"])
        self.assertNotIn("weather", self.executed[0][0].compiled.sql)

    def test_business_errors_from_compiling_reach_the_client_and_store_nothing(self) -> None:
        plan = {"select": [{"column_id": self.column("customers.region")},
                           {"column_id": self.column("orders.total"), "aggregation": "sum"}]}
        result, _ = self.call(self.arguments(("customers", "orders"), plan))
        self.assertTrue(result.is_error)
        self.assertIn("group_by", result.content[0].text)
        self.assertEqual(self.dataset_count(), 0)

    def test_runtime_failures_do_not_store_a_dataset(self) -> None:
        def paused(service, connection_id):
            raise Text2SqlInvalidRequest("Connection đang tạm dừng nên chưa thể truy vấn.")

        with patch.object(DatasetQueryService, "resolve_source", paused):
            result, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
        self.assertTrue(result.is_error)
        self.assertIn("tạm dừng", result.content[0].text)
        self.assertEqual((self.executed, self.dataset_count()), ([], 0))

        errors: list[Exception] = []

        def failing(prepared, confirmation):
            raise errors[-1]

        for error in (Text2SqlQueryTimeout(), Text2SqlQueryFailed()):
            errors.append(error)
            with self.subTest(error=type(error).__name__), patch.object(dataset_tool, "run_execute", failing):
                result, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
                self.assertTrue(result.is_error)
                self.assertEqual(self.dataset_count(), 0)

        first, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
        self.assertFalse(first.is_error, first.content)
        plan = {"select": [{"column_id": self.column("orders.customer_id"), "aggregation": "count_distinct"}]}
        with patch.object(dataset_tool, "run_execute", failing):
            failed, _ = self.call(self.arguments(("customers", "orders"), plan))
        self.assertTrue(failed.is_error)
        self.session.expire_all()
        stored = self.session.scalars(select(QueryDataset)).one()
        self.assertNotIn(self.column("orders.customer_id"), stored.selected_column_ids)

    def test_column_limit_only_warns_and_still_runs_the_query(self) -> None:
        first, _ = self.call(self.arguments(("customers", "orders"), self.revenue_by_region()))
        dataset_id = first.structured_content["dataset"]["dataset_id"]
        stored = self.session.scalars(select(QueryDataset)).one()
        stored.selected_column_ids = [*stored.selected_column_ids, *[
            str(uuid4()) for _ in range(MAX_SELECTED_COLUMNS - len(stored.selected_column_ids))
        ]]
        self.session.commit()
        plan = {"select": [{"column_id": self.column("orders.customer_id"), "aggregation": "count_distinct"}]}
        result, _ = self.call(self.arguments(("customers", "orders"), plan))
        self.assertFalse(result.is_error, result.content)
        content = result.structured_content
        self.assertEqual(content["status"], "ok")
        self.assertEqual(content["dataset"]["dataset_id"], dataset_id)
        self.assertEqual(content["dataset"]["added_column_ids"], [])
        self.assertIn(str(MAX_SELECTED_COLUMNS), content["message"])
        self.assertEqual(len(self.executed), 2)
        self.assertEqual(len(DatasetStore(self.session).get(self.connection.id, stored.id).selected_column_ids),
                         MAX_SELECTED_COLUMNS)


if __name__ == "__main__":
    unittest.main()
