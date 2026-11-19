import asyncio
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from mcp import StdioServerParameters
from mcp.client import Client
from mcp.types import ElicitResult

from backend.mcp_server.server import mcp
from backend.mcp_server.tools import column, common, expert_rule, glossary, metric, own_knowledge, table
from backend.mcp_server.tools import query as query_tool
from backend.modules.data_dictionary.schemas.schema_data_dictionary import ColumnDictionaryOut, TableDictionaryOut
from backend.modules.text2sql.common.errors import Text2SqlConnectionNotFound, Text2SqlInvalidRequest
from backend.modules.text2sql.details import schemas as details
from backend.modules.text2sql.query.schemas import PiiReport, QueryMetricInfo, QueryResult, ResultColumn
from backend.modules.text2sql.vector_store.retrieve.topic_search import TopicHit, TopicSearchOutcome

CONNECTION_ID = "00000000-0000-0000-0000-000000000001"
ENTITY_ID = "00000000-0000-0000-0000-000000000002"
TOOLS = {
    "search_tables", "search_columns", "search_metrics", "get_metric", "search_glossary_terms", "get_glossary_term",
    "search_expert_rules", "get_expert_rule", "search_own_knowledge", "get_own_knowledge", "query_metric",
    "ask_data", "find_fields", "plan_join", "query_dataset",
}
TABLE_REF = details.TableRef(
    table_id=UUID(ENTITY_ID), schema_name="public", table_name="sales", display_name="Bán hàng"
)


def metric_detail():
    return details.MetricDetail(
        metric_id=UUID(ENTITY_ID), name="revenue", label="Doanh thu", description=None, expression="SUM(amount)",
        format=None, currency=None, metric_type=None, warning_text=None, origin="manual", table=TABLE_REF,
        referenced_columns=[],
    )


def glossary_detail():
    return details.GlossaryTermDetail(
        term_id=UUID(ENTITY_ID), name="Doanh số", business_domains=[], revision_number=1, definition="x", synonyms=[],
        links=[],
    )


def rule_detail():
    return details.ExpertRuleDetail(
        rule_id=UUID(ENTITY_ID), name="Quy tắc", business_domains=[], table=None, description=None, conditions=[],
        exceptions=[], examples=[], glossary_terms=[], metrics=[],
    )


def own_detail():
    return details.OwnKnowledgeDetail(
        entry_id=UUID(ENTITY_ID), name="Ngày mưa", kind="glossary", concept=None, definition="x", table=None,
        review_status="pending", version=1, updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def table_dictionary(table_id: UUID, columns=()):
    return TableDictionaryOut(
        table_id=table_id, connection_id=UUID(CONNECTION_ID), schema_name="public", table_name="sales",
        table_type="TABLE", is_saved=True, display_name="Bán hàng", description="Giao dịch", grain_description=None,
        table_kind=None, layout="wide", indicator_catalog=None, contains_pii=False, updated_at=None,
        column_roles=[], time_grains=[], indicator_aggregations=[], columns=list(columns),
    )


def column_dictionary(column_id: UUID):
    return ColumnDictionaryOut(
        column_id=column_id, name="region", data_type="TEXT", ordinal_position=1, is_nullable=False,
        source_is_primary_key=False, default_value=None, is_saved=True, display_name="Khu vực", description=None,
        business_term=None, semantic_role="dimension", semantic_role_is_default=False, temporal_kind=None, unit=None,
        format=None, is_primary_key=None, is_unique=False, referenced_column=None, contains_pii=False,
        aggregations=[], synonyms=["miền"], updated_at=None,
    )


def call(tool: str, arguments: dict):
    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


class ListingTests(unittest.TestCase):
    def test_in_memory_handshake_lists_every_tool_and_no_resources(self) -> None:
        async def check() -> None:
            async with Client(mcp) as client:
                self.assertEqual({tool.name for tool in (await client.list_tools()).tools}, TOOLS)
                self.assertEqual((await client.list_resources()).resources, [])

        asyncio.run(check())

    def test_stdio_handshake_lists_every_tool(self) -> None:
        async def check() -> None:
            process = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp_server"])
            async with Client(process) as client:
                self.assertEqual({tool.name for tool in (await client.list_tools()).tools}, TOOLS)

        asyncio.run(check())

    def schemas(self) -> dict[str, dict]:
        async def check() -> dict:
            async with Client(mcp) as client:
                return {
                    tool.name: getattr(tool, "input_schema", None) or tool.inputSchema
                    for tool in (await client.list_tools()).tools
                }

        return asyncio.run(check())

    def test_search_tools_take_an_optional_rerank_defaulting_to_false(self) -> None:
        schemas = self.schemas()
        for name in sorted(tool for tool in TOOLS if tool.startswith("search_")):
            with self.subTest(name):
                properties = schemas[name]["properties"]
                self.assertEqual(properties["rerank"]["type"], "boolean")
                self.assertIs(properties["rerank"]["default"], False)
                self.assertNotIn("rerank", schemas[name]["required"])
                self.assertIn("question", schemas[name]["required"])

    def test_detail_tools_have_no_search_parameters(self) -> None:
        schemas = self.schemas()
        for name in sorted(tool for tool in TOOLS if tool.startswith("get_")):
            with self.subTest(name):
                self.assertTrue({"rerank", "question", "k"}.isdisjoint(schemas[name]["properties"]))
                self.assertIn("connection_id", schemas[name]["required"])
        self.assertEqual(sorted(schemas["get_metric"]["required"]), ["connection_id", "metric_id"])
        self.assertEqual(sorted(schemas["get_own_knowledge"]["required"]), ["connection_id", "entry_id", "user_id"])

    def test_server_exposes_fifteen_tools(self) -> None:
        self.assertEqual(len(TOOLS), 15)

    def test_own_knowledge_search_requires_a_user(self) -> None:
        schemas = self.schemas()
        self.assertIn("user_id", schemas["search_own_knowledge"]["required"])
        self.assertNotIn("user_id", schemas["ask_data"]["required"])
        self.assertIn("user_id", schemas["ask_data"]["properties"])
        for name in TOOLS - {"search_own_knowledge", "get_own_knowledge", "ask_data"}:
            self.assertNotIn("user_id", schemas[name]["properties"])

    def test_result_counts_are_bounded_per_tool(self) -> None:
        schemas = self.schemas()
        limits = {name: (props["properties"]["k"]["default"], props["properties"]["k"]["maximum"])
                  for name, props in schemas.items() if "k" in props["properties"]}
        self.assertEqual(limits["search_tables"], (3, 5))
        self.assertEqual(limits["search_columns"], (5, 10))
        for name in ("search_metrics", "search_glossary_terms", "search_expert_rules", "search_own_knowledge"):
            self.assertEqual(limits[name], (5, 10))


class ToolCallTests(unittest.TestCase):
    def topic_result(self, topic):
        def fake(called_topic, connection_id, question, k, rerank, user_id=None):
            calls.append((called_topic, str(connection_id), question, k, rerank, user_id))
            return common.SearchOut(hits=[], reranked=rerank, rerank_warning=None, match="none")

        calls = []
        return fake, calls

    def test_topic_search_tools_pass_their_topic_and_arguments(self) -> None:
        cases = (
            ("search_glossary_terms", glossary, "glossary", {}),
            ("search_expert_rules", expert_rule, "expert_rule", {}),
            ("search_own_knowledge", own_knowledge, "own_knowledge", {"user_id": "alice"}),
        )
        for tool, module, topic, extra in cases:
            with self.subTest(tool):
                fake, calls = self.topic_result(topic)
                arguments = {"connection_id": CONNECTION_ID, "question": "  hỏi gì đó  ", **extra}
                with patch.object(module, "search_topic", fake):
                    default = call(tool, arguments)
                    enabled = call(tool, {**arguments, "k": 2, "rerank": True})
                self.assertFalse(default.is_error)
                self.assertEqual(calls[0], (topic, CONNECTION_ID, "hỏi gì đó", 5, False, extra.get("user_id")))
                self.assertEqual(calls[1], (topic, CONNECTION_ID, "hỏi gì đó", 2, True, extra.get("user_id")))
                self.assertTrue(enabled.structured_content["reranked"])

    def test_metric_search_keeps_its_arguments(self) -> None:
        seen = []

        def fake(connection_id, question, k, rerank):
            seen.append((str(connection_id), question, k, rerank))
            return metric.SearchMetricsOut(candidates=[], reranked=rerank, rerank_warning=None)

        with patch.object(metric, "run_search", fake):
            call("search_metrics", {"connection_id": CONNECTION_ID, "question": " x "})
            call("search_metrics", {"connection_id": CONNECTION_ID, "question": "x", "k": 3, "rerank": True})
        self.assertEqual(seen, [(CONNECTION_ID, "x", 5, False), (CONNECTION_ID, "x", 3, True)])

    def test_detail_tools_call_their_reader_and_return_structured_content(self) -> None:
        cases = (
            ("get_metric", metric, "run_get_metric", {"metric_id": ENTITY_ID}, metric_detail(), "expression"),
            ("get_glossary_term", glossary, "run_get_glossary_term", {"term_id": ENTITY_ID}, glossary_detail(),
             "definition"),
            ("get_expert_rule", expert_rule, "run_get_expert_rule", {"rule_id": ENTITY_ID}, rule_detail(), "name"),
            ("get_own_knowledge", own_knowledge, "run_get_own_knowledge",
             {"user_id": "alice", "entry_id": ENTITY_ID}, own_detail(), "definition"),
        )
        for tool, module, reader, extra, result, field in cases:
            with self.subTest(tool):
                seen = []

                def fake(*args, _seen=seen, _result=result):
                    _seen.append(args)
                    return _result

                with patch.object(module, reader, fake):
                    response = call(tool, {"connection_id": CONNECTION_ID, **extra})
                self.assertFalse(response.is_error)
                self.assertEqual(str(seen[0][0]), CONNECTION_ID)
                self.assertIn(field, response.structured_content)

    def test_table_search_returns_full_descriptions_in_hit_order_and_drops_missing(self) -> None:
        first, second, gone = uuid4(), uuid4(), uuid4()
        hits = [
            TopicHit(entity_id=gone, table_id=gone, name="gone", display_name="gone", text="", score=0.9),
            TopicHit(entity_id=second, table_id=second, name="b", display_name="b", text="", score=0.8,
                     rerank_score=0.7),
            TopicHit(entity_id=first, table_id=first, name="a", display_name="a", text="", score=0.6),
        ]
        service = SimpleNamespace(search=lambda *args: TopicSearchOutcome(hits=hits, reranked=True))
        detail_service = SimpleNamespace(tables=lambda connection_id, ids: [
            details.TableDescription(table=table_dictionary(item)) for item in ids if item != gone
        ])

        @contextmanager
        def fake_session(rerank):
            yield object(), service, None

        with patch.object(table, "search_session", fake_session), \
                patch.object(table, "DetailService", lambda session: detail_service):
            result = table.run_search_tables(UUID(CONNECTION_ID), "q", 3, True)
        self.assertEqual([item.table_id for item in result.hits], [second, first])
        self.assertEqual([item.rerank_score for item in result.hits], [0.7, None])
        self.assertEqual(result.hits[0].description, "Giao dịch")
        self.assertIn(result.match, {"ok", "unverified"})
        self.assertTrue(result.reranked)

    def test_match_signal_reports_none_weak_ok_and_unverified(self) -> None:
        self.assertEqual(common.match_signal([], True)[0], "none")
        self.assertEqual(common.match_signal([0.05, 0.01], True)[0], "weak")
        self.assertEqual(common.match_signal([0.8, 0.1], True), ("ok", None))
        self.assertEqual(common.match_signal([None, None], False)[0], "unverified")
        self.assertIsNotNone(common.match_signal([], False)[1])

    def test_compact_table_drops_empty_and_bookkeeping_fields(self) -> None:
        item = table_dictionary(uuid4())
        compact = table.compact_table(item, 0.5, None)
        dumped = compact.model_dump(exclude_none=True)
        for dropped in ("updated_at", "is_saved", "column_roles", "time_grains", "layout"):
            self.assertNotIn(dropped, dumped)
        for column_item in dumped["columns"]:
            for dropped in ("ordinal_position", "is_nullable", "default_value", "aggregations", "updated_at"):
                self.assertNotIn(dropped, column_item)
            self.assertNotIn("synonyms", column_item) if not item.columns[0].synonyms else None

    def test_column_search_returns_column_structure_with_its_table(self) -> None:
        table_id, column_id = uuid4(), uuid4()
        hits = [TopicHit(entity_id=column_id, table_id=table_id, name="region", display_name="Khu vực", text="",
                         score=0.5)]
        outcome = TopicSearchOutcome(hits=hits, rerank_error="text2sql_rerank_unavailable")
        service = SimpleNamespace(search=lambda *args: outcome)
        seen = []

        def columns(connection_id, refs):
            seen.append(list(refs))
            return [details.ColumnDescription(table=TABLE_REF, column=column_dictionary(column_id))]

        @contextmanager
        def fake_session(rerank):
            yield object(), service, None

        with patch.object(column, "search_session", fake_session), \
                patch.object(column, "DetailService", lambda session: SimpleNamespace(columns=columns)):
            result = column.run_search_columns(UUID(CONNECTION_ID), "q", 5, True)
        self.assertEqual(seen, [[(table_id, column_id)]])
        self.assertEqual(result.hits[0].description.column.synonyms, ["miền"])
        self.assertEqual(result.hits[0].description.table.table_name, "sales")
        self.assertFalse(result.reranked)
        self.assertIn("text2sql_rerank_unavailable", result.rerank_warning)


class ToolErrorTests(unittest.TestCase):
    def patched(self, error: Exception):
        def fail(*args, **kwargs):
            raise error

        return patch.object(metric, "run_search", fail)

    def test_business_errors_reach_the_client_with_their_message(self) -> None:
        with self.patched(Text2SqlConnectionNotFound()):
            result = call("search_metrics", {"connection_id": CONNECTION_ID, "question": "x"})
        self.assertTrue(result.is_error)
        self.assertIn(Text2SqlConnectionNotFound.message, result.content[0].text)

    def test_unexpected_errors_do_not_leak_details(self) -> None:
        with self.patched(RuntimeError("password=secret host=db.internal")):
            result = call("search_metrics", {"connection_id": CONNECTION_ID, "question": "x"})
        self.assertTrue(result.is_error)
        self.assertNotIn("secret", result.content[0].text)
        self.assertNotIn("db.internal", result.content[0].text)

    def test_invalid_arguments_are_rejected_before_any_work(self) -> None:
        invalid = (
            ("search_metrics", {"connection_id": "not-a-uuid", "question": "x"}),
            ("search_metrics", {"connection_id": CONNECTION_ID, "question": "   "}),
            ("search_metrics", {"connection_id": CONNECTION_ID, "question": "x", "k": 11}),
            ("search_tables", {"connection_id": CONNECTION_ID, "question": "x", "k": 6}),
            ("search_columns", {"connection_id": CONNECTION_ID, "question": "x", "rerank": "maybe"}),
            ("search_own_knowledge", {"connection_id": CONNECTION_ID, "question": "x"}),
            ("search_own_knowledge", {"connection_id": CONNECTION_ID, "question": "x", "user_id": ""}),
            ("get_metric", {"connection_id": CONNECTION_ID, "metric_id": "nope"}),
            ("get_own_knowledge", {"connection_id": CONNECTION_ID, "entry_id": ENTITY_ID}),
        )
        calls = []
        stand_in = lambda *args, **kwargs: calls.append(args)  # noqa: E731
        with patch.object(common, "search_session", stand_in), patch.object(common, "detail_session", stand_in), \
                patch.object(metric, "run_search", stand_in):
            for tool, arguments in invalid:
                with self.subTest(tool=tool, arguments=arguments):
                    self.assertTrue(call(tool, arguments).is_error)
        self.assertEqual(calls, [])


def query_result(confirmation: str = "not_required") -> QueryResult:
    return QueryResult(
        metric=QueryMetricInfo(
            metric_id=UUID(ENTITY_ID), name="revenue", label="Doanh thu", format=None, currency=None,
            warning_text=None, table="public.sales",
        ),
        columns=[ResultColumn(name="Doanh thu", role="metric")], rows=[["600.50"]], row_count=1, truncated=False,
        limit=100, sql="SELECT 1", parameters={}, pii=PiiReport(confirmation=confirmation), elapsed_ms=3,
    )


class QueryMetricToolTests(unittest.TestCase):
    ARGUMENTS = {"connection_id": CONNECTION_ID, "metric_id": ENTITY_ID}

    def invoke(self, pii_columns, answer=None, supports_elicitation=True, arguments=None):
        prepared, executed, asked = [], [], []

        def fake_prepare(connection_id, plan):
            prepared.append(plan)
            return SimpleNamespace(pii_columns=pii_columns)

        def fake_execute(compiled, confirmation):
            executed.append(confirmation)
            return query_result(confirmation)

        async def elicit(context, params):
            asked.append(params.message)
            return answer

        async def run():
            options = {"elicitation_callback": elicit} if supports_elicitation else {}
            async with Client(mcp, **options) as client:
                return await client.call_tool("query_metric", arguments or self.ARGUMENTS)

        with (
            patch.object(query_tool, "run_prepare", fake_prepare),
            patch.object(query_tool, "run_execute", fake_execute),
        ):
            result = asyncio.run(run())
        return result, prepared, executed, asked

    def test_schema_exposes_the_plan_but_not_the_context(self) -> None:
        async def check():
            async with Client(mcp) as client:
                tool = next(item for item in (await client.list_tools()).tools if item.name == "query_metric")
                return getattr(tool, "input_schema", None) or tool.inputSchema

        schema = asyncio.run(check())
        self.assertEqual(sorted(schema["required"]), ["connection_id", "metric_id"])
        plan_fields = {"connection_id", "metric_id", "group_by", "time", "filters", "order_by", "limit"}
        self.assertEqual(set(schema["properties"]), plan_fields)
        self.assertEqual(schema["properties"]["limit"]["default"], 100)

    def test_query_without_pii_runs_without_asking(self) -> None:
        result, prepared, executed, asked = self.invoke([])
        self.assertFalse(result.is_error)
        self.assertEqual((executed, asked), (["not_required"], []))
        self.assertEqual(prepared[0].limit, 100)
        self.assertEqual(result.structured_content["rows"], [["600.50"]])
        self.assertEqual(result.structured_content["pii"]["confirmation"], "not_required")

    def test_pii_query_asks_the_user_and_runs_after_consent(self) -> None:
        answer = ElicitResult(action="accept", content={"proceed": True})
        result, _, executed, asked = self.invoke(["Khách hàng", "Số điện thoại"], answer)
        self.assertFalse(result.is_error)
        self.assertEqual(executed, ["confirmed"])
        self.assertIn("Khách hàng, Số điện thoại", asked[0])
        self.assertIn("placeholder", asked[0])
        self.assertEqual(result.structured_content["pii"]["confirmation"], "confirmed")

    def test_pii_query_is_cancelled_when_the_user_declines(self) -> None:
        for answer in (
            ElicitResult(action="decline"), ElicitResult(action="cancel"),
            ElicitResult(action="accept", content={"proceed": False}),
        ):
            with self.subTest(action=answer.action, content=answer.content):
                result, _, executed, _ = self.invoke(["Khách hàng"], answer)
                self.assertTrue(result.is_error)
                self.assertEqual(executed, [])
                self.assertIn("hủy", result.content[0].text)

    def test_client_without_elicitation_still_gets_masked_data_and_a_marker(self) -> None:
        result, _, executed, asked = self.invoke(["Khách hàng"], supports_elicitation=False)
        self.assertFalse(result.is_error)
        self.assertEqual((executed, asked), (["not_supported"], []))
        self.assertEqual(result.structured_content["pii"]["confirmation"], "not_supported")

    def test_plan_arguments_reach_the_compiler(self) -> None:
        group, column_id = str(uuid4()), str(uuid4())
        arguments = {
            **self.ARGUMENTS, "group_by": [group], "limit": 7,
            "time": {"column_id": column_id, "start": "2026-01-01", "granularity": "month"},
            "filters": [{"column_id": column_id, "operator": "in", "value": ["a", "b"]}],
            "order_by": [{"by": "metric", "direction": "asc"}],
        }
        _, prepared, _, _ = self.invoke([], arguments=arguments)
        plan = prepared[0]
        self.assertEqual((str(plan.group_by[0]), plan.limit), (group, 7))
        self.assertEqual((plan.time.granularity, str(plan.time.start)), ("month", "2026-01-01"))
        self.assertEqual((plan.filters[0].operator, plan.filters[0].value), ("in", ["a", "b"]))
        self.assertEqual((plan.order_by[0].by, plan.order_by[0].direction), ("metric", "asc"))

    def test_malformed_plans_are_rejected_before_any_query(self) -> None:
        column_id = str(uuid4())
        invalid = (
            {"limit": 0}, {"limit": 5001}, {"group_by": ["not-a-uuid"]}, {"group_by": [str(uuid4())] * 6},
            {"filters": [{"column_id": column_id, "operator": "drop_table", "value": 1}]},
            {"filters": [{"column_id": column_id, "operator": "equals", "value": 1, "sql": "1=1"}]},
            {"time": {"column_id": column_id, "granularity": "decade"}},
            {"order_by": [{"by": "metric", "direction": "sideways"}]},
        )
        for extra in invalid:
            with self.subTest(extra=extra):
                result, prepared, executed, _ = self.invoke([], arguments={**self.ARGUMENTS, **extra})
                self.assertTrue(result.is_error)
                self.assertEqual((prepared, executed), ([], []))

    def test_unknown_top_level_arguments_are_ignored_and_never_become_sql(self) -> None:
        arguments = {**self.ARGUMENTS, "sql": "DROP TABLE sales", "raw_sql": "SELECT 1"}
        result, prepared, executed, _ = self.invoke([], arguments=arguments)
        self.assertFalse(result.is_error)
        self.assertEqual(len(executed), 1)
        self.assertFalse(any(hasattr(prepared[0], name) for name in ("sql", "raw_sql")))

    def test_business_errors_from_planning_reach_the_client(self) -> None:
        def fail(connection_id, plan):
            raise Text2SqlInvalidRequest("Không lọc theo cột dữ liệu cá nhân.")

        async def run():
            async with Client(mcp) as client:
                return await client.call_tool("query_metric", self.ARGUMENTS)

        with patch.object(query_tool, "run_prepare", fail):
            result = asyncio.run(run())
        self.assertTrue(result.is_error)
        self.assertIn("dữ liệu cá nhân", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
