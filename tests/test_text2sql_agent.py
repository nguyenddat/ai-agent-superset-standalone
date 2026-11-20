import json
import threading
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent_package.tool_agent import (
    EXHAUSTED_NOTICE,
    REPEATED_FAILURE,
    AgentPause,
    ToolAgentPause,
    ToolError,
    run_tool_agent,
)
from backend.modules.text2sql.repositories.source_query_repository import (
    QueryRows,
    source_url,
)
from backend.modules.text2sql.schemas import (
    AgentStepOut,
    PreprocessedQuestionOut,
    PreprocessOut,
    QuestionAnswerOut,
    QuestionKnowledgeOut,
)
from backend.modules.text2sql.services.agent_catalog import (
    AgentCatalog,
    ColumnInfo,
    MetricInfo,
    RuleCondition,
    RuleInfo,
    TableInfo,
)
from backend.modules.text2sql.services.agent_tools import (
    MAX_CLARIFICATIONS,
    QueryCache,
    Text2SqlToolkit,
    json_cell,
)
from backend.modules.text2sql.services.chat_graph import (
    ChatGraphContext,
    Clarification,
    PendingQuestion,
    run_chat_graph,
)
from backend.modules.text2sql.services.sql_builder import (
    QueryMetricArgs,
    build_metric_query,
)
from backend.modules.text2sql.services.sql_guard import validate_select
from backend.modules.text2sql.services.text2sql_agent_service import (
    AgentRun,
    date_ranges,
    tool_reporter,
)
from backend.modules.text2sql.utils.exceptions import (
    Text2SqlConnectionNotFound,
    Text2SqlInvalidRequest,
)

TABLE_ID = uuid4()
METRIC_ID = uuid4()
COLUMNS = (
    ColumnInfo("ngay", "date", "Ngày", None, (), False),
    ColumnInfo("thanh_pho", "text", "Thành phố", None, ("tỉnh",), False),
    ColumnInfo("luong_mua", "numeric", "Lượng mưa", None, (), False),
    ColumnInfo("loai_tram", "text", "Loại trạm", None, (), False),
    ColumnInfo("quan_trac_vien", "text", "Quan trắc viên", None, (), True),
)
RULE = RuleInfo(
    id=uuid4(), name="Chỉ trạm chính", table_id=TABLE_ID, description=None,
    conditions=(RuleCondition("loai_tram", "equals", "chinh"),), exceptions=(), examples=(),
    metric_ids=frozenset({METRIC_ID}),
)


def make_catalog(source_sql: str | None = None) -> AgentCatalog:
    table = TableInfo(TABLE_ID, "weather", "daily", "Thời tiết ngày", None, None, COLUMNS)
    metric = MetricInfo(
        METRIC_ID, "tong_luong_mua", "Tổng lượng mưa", "SUM(luong_mua)", None, None, None, None, TABLE_ID,
        source_sql,
    )
    return AgentCatalog(tables={TABLE_ID: table}, metrics={METRIC_ID: metric}, rules=[RULE])


class FakeRunner:
    def __init__(self, rows: list[tuple] | None = None, error: ToolError | None = None) -> None:
        self.calls: list[str] = []
        self.rows = rows if rows is not None else [("Huế", Decimal("12.5"))]
        self.error = error

    def __call__(self, sql: str, max_rows: int) -> QueryRows:
        self.calls.append(sql)
        if self.error is not None:
            raise self.error
        return QueryRows(columns=["thanh_pho", "value"], rows=self.rows, truncated=False, elapsed_ms=1)


class ValueRunner:
    def __init__(self, values: list[str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def __call__(self, sql: str, max_rows: int) -> QueryRows:
        self.calls.append(sql)
        if "ILIKE" in sql:
            return QueryRows(columns=["thanh_pho"], rows=[], truncated=False, elapsed_ms=1)
        if sql.startswith("SELECT DISTINCT"):
            rows = [(value,) for value in self.values]
            return QueryRows(columns=["thanh_pho"], rows=rows, truncated=False, elapsed_ms=1)
        return QueryRows(columns=["value"], rows=[(Decimal(1),)], truncated=False, elapsed_ms=1)


class ScriptedModel:
    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = replies
        self.received: list[list] = []
        self.bound: list[list[str]] = []

    def bind_tools(self, tools):
        self.bound.append([tool.name for tool in tools])
        return self

    def invoke(self, messages):
        self.received.append(list(messages))
        return self.replies.pop(0)


def tool_call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


TABLE_NAMES = {"weather.daily": "weather.daily", "daily": "weather.daily"}


class SqlGuardTests(unittest.TestCase):
    def test_qualifies_known_tables_and_keeps_ctes(self) -> None:
        sql = validate_select("WITH a AS (SELECT * FROM daily) SELECT * FROM a;", TABLE_NAMES)
        self.assertEqual(sql, 'WITH a AS (SELECT * FROM "weather"."daily") SELECT * FROM a')

    def test_rejects_writes_and_system_access(self) -> None:
        cases = {
            "DELETE FROM daily": "SELECT",
            "SELECT 1; SELECT 2": "một câu lệnh",
            "SELECT * INTO copy FROM daily": "INTO",
            "SELECT * FROM daily FOR UPDATE": "LOCK",
            "SELECT pg_sleep(10)": "pg_sleep",
            "SELECT * FROM pg_catalog.pg_user": "không có trong connection",
            "SELECT * FROM other": "schema.bảng",
            "SELECT * FROM (WITH users AS (SELECT 1) SELECT * FROM users) a, users": "'users'",
            "WITH users AS (SELECT * FROM users) SELECT * FROM users": "'users'",
            "WITH b AS (SELECT * FROM a), a AS (SELECT 1) SELECT * FROM b": "'a'",
            "SELECT schema_to_xml('public', true, true, '')": "schema_to_xml",
            "SELECT database_to_xml(true, true, '')": "database_to_xml",
            "SELECT query_to_xmlschema('select 1', true, true, '')": "query_to_xmlschema",
            "SELECT ts_stat('select to_tsvector(note) from users')": "ts_stat",
            "SELECT * FROM crosstab('select * from users') AS t(a text)": "crosstab",
        }
        for sql, message in cases.items():
            with self.subTest(sql=sql), self.assertRaisesRegex(ToolError, message):
                validate_select(sql, TABLE_NAMES)

    def test_ctes_resolve_by_scope(self) -> None:
        cases = (
            "WITH RECURSIVE r AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT * FROM r",
            "WITH a AS (SELECT 1), b AS (SELECT * FROM a) SELECT * FROM b",
            "SELECT * FROM (WITH x AS (SELECT * FROM daily) SELECT * FROM x) AS s",
        )
        for sql in cases:
            with self.subTest(sql=sql):
                validate_select(sql, TABLE_NAMES)


class SqlBuilderTests(unittest.TestCase):
    def test_builds_grouped_query_and_applies_linked_rule(self) -> None:
        built = build_metric_query(make_catalog(), QueryMetricArgs(
            metric="Tổng lượng mưa", group_by=["tỉnh"], time_grain={"column": "ngay", "grain": "week"},
            filters=[{"column": "ngay", "operator": "greater_than_or_equal", "value": "2026-11-01"}],
            order_by=[{"field": "value"}], limit=3,
        ))
        self.assertEqual(built.sql, (
            'SELECT CAST(DATE_TRUNC(\'WEEK\', "ngay") AS DATE) AS "ngay", "thanh_pho", '
            'SUM("luong_mua") AS "tong_luong_mua" '
            'FROM "weather"."daily" WHERE "ngay" >= \'2026-11-01\' AND "loai_tram" = \'chinh\' '
            'GROUP BY CAST(DATE_TRUNC(\'WEEK\', "ngay") AS DATE), "thanh_pho" '
            'ORDER BY "tong_luong_mua" DESC NULLS LAST LIMIT 3'
        ))
        self.assertIn("Đã áp quy tắc 'Chỉ trạm chính'", built.notes[0])

    def test_rule_already_in_metric_expression_is_not_filtered_again(self) -> None:
        catalog = make_catalog()
        catalog.metrics[METRIC_ID] = MetricInfo(
            METRIC_ID, "ty_le_tram_chinh", "Tỷ lệ trạm chính",
            "100.0 * COUNT(CASE WHEN loai_tram = 'chinh' THEN 1 END) / NULLIF(COUNT(*), 0)",
            None, None, None, None, TABLE_ID, None,
        )
        built = build_metric_query(catalog, QueryMetricArgs(metric="ty_le_tram_chinh"))
        self.assertNotIn("WHERE", built.sql)
        self.assertIn("đã nằm trong biểu thức metric", built.notes[0])

    def test_extract_epoch_expression_is_buildable(self) -> None:
        catalog = make_catalog()
        catalog.metrics[METRIC_ID] = MetricInfo(
            METRIC_ID, "so_ngay_tb", "Số ngày", "AVG(EXTRACT(EPOCH FROM (ngay - ngay)))",
            None, None, None, None, TABLE_ID, None,
        )
        built = build_metric_query(catalog, QueryMetricArgs(metric="so_ngay_tb", skip_rules=["Chỉ trạm chính"]))
        self.assertIn('AVG(EXTRACT(EPOCH FROM ("ngay" - "ngay")))', built.sql)

    def test_question_filter_overrides_rule_on_same_column(self) -> None:
        built = build_metric_query(make_catalog(), QueryMetricArgs(
            metric="tong_luong_mua", filters=[{"column": "loai_tram", "operator": "equals", "value": "phu"}],
        ))
        self.assertIn("\"loai_tram\" = 'phu'", built.sql)
        self.assertNotIn("'chinh'", built.sql)
        self.assertIn("đã lọc cột này", built.notes[0])

    def test_skip_rules_removes_rule(self) -> None:
        built = build_metric_query(
            make_catalog(), QueryMetricArgs(metric="tong_luong_mua", skip_rules=["chỉ trạm chính"])
        )
        self.assertNotIn("WHERE", built.sql)

    def test_errors_name_valid_alternatives(self) -> None:
        with self.assertRaisesRegex(ToolError, "Các cột hợp lệ: ngay, thanh_pho"):
            build_metric_query(make_catalog(), QueryMetricArgs(metric="tong_luong_mua", group_by=["quan"]))
        with self.assertRaisesRegex(ToolError, "không phải số"):
            build_metric_query(make_catalog(), QueryMetricArgs(
                metric="tong_luong_mua", filters=[{"column": "luong_mua", "operator": "greater_than", "value": "x"}],
            ))
        with self.assertRaisesRegex(ToolError, "run_sql"):
            build_metric_query(make_catalog("SELECT 1"), QueryMetricArgs(metric="tong_luong_mua"))


class ToolkitTests(unittest.TestCase):
    def make(self, runner: FakeRunner, max_rows_to_llm: int = 50) -> Text2SqlToolkit:
        return Text2SqlToolkit(make_catalog(), QueryCache(runner=runner, max_rows=200), max_rows_to_llm)

    def test_query_metric_records_step_and_caps_rows_for_llm(self) -> None:
        runner = FakeRunner(rows=[("Huế", Decimal("12.5")), ("Vinh", Decimal(3))])
        toolkit = self.make(runner, max_rows_to_llm=1)
        output = toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        self.assertEqual(output["rows"], [["Huế", "12,5"]])
        self.assertTrue(output["truncated"])
        self.assertEqual(toolkit.steps[0].rows, [["Huế", 12.5], ["Vinh", 3]])
        self.assertEqual(toolkit.steps[0].sql, runner.calls[-1])
        self.assertIn("Không lọc theo thời gian", output["notes"][0])

    def test_identical_sql_runs_once(self) -> None:
        runner = FakeRunner()
        toolkit = self.make(runner)
        toolkit.run_sql("SELECT thanh_pho FROM daily", "a")
        toolkit.run_sql("SELECT thanh_pho FROM weather.daily", "b")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(len(toolkit.steps), 2)

    def test_rejected_sql_is_recorded_without_running(self) -> None:
        runner = FakeRunner()
        toolkit = self.make(runner)
        with self.assertRaises(ToolError):
            toolkit.run_sql("DELETE FROM daily", "xoá")
        self.assertEqual(runner.calls, [])
        self.assertIn("SELECT", toolkit.steps[0].error)

    def test_database_error_is_recorded(self) -> None:
        toolkit = self.make(FakeRunner(error=ToolError("Database báo lỗi 42703: column \"x\" does not exist")))
        with self.assertRaisesRegex(ToolError, "42703"):
            toolkit.run_sql("SELECT x FROM daily", "thử")
        self.assertIn("42703", toolkit.steps[0].error)

    def test_column_values_refuse_personal_data(self) -> None:
        with self.assertRaisesRegex(ToolError, "dữ liệu cá nhân"):
            self.make(FakeRunner()).get_column_values("daily", "quan_trac_vien")

    def test_filter_value_is_matched_to_data_ignoring_accents(self) -> None:
        runner = ValueRunner(["Da Nang", "Ha Noi", "Hue"])
        toolkit = self.make(runner)
        output = toolkit.query_metric(
            metric="tong_luong_mua", filters=[{"column": "thanh_pho", "operator": "equals", "value": "Đà Nẵng"}],
        )
        self.assertIn("\"thanh_pho\" = 'Da Nang'", runner.calls[-1])
        self.assertIn("'Da Nang'", output["notes"][0])
        toolkit.query_metric(
            metric="tong_luong_mua", filters=[{"column": "thanh_pho", "operator": "contains", "value": "Huế"}],
        )
        self.assertIn("\"thanh_pho\" IN ('Hue')", runner.calls[-1])

    def test_unknown_filter_value_lists_known_values(self) -> None:
        toolkit = self.make(ValueRunner(["Da Nang", "Ha Noi"]))
        with self.assertRaisesRegex(ToolError, "không có giá trị 'Sa Pa'.*Da Nang"):
            toolkit.query_metric(
                metric="tong_luong_mua", filters=[{"column": "thanh_pho", "operator": "equals", "value": "Sa Pa"}],
            )
        self.assertIsNotNone(toolkit.steps[-1].error)

    def test_query_metric_notes_when_all_entities_are_merged(self) -> None:
        toolkit = self.make(ValueRunner(["Da Nang", "Hue"]))
        merged = toolkit.query_metric(
            metric="tong_luong_mua", filters=[{"column": "ngay", "operator": "equals", "value": "2026-03-03"}],
        )
        self.assertTrue(any("một số gộp mọi dòng của bảng weather.daily" in note for note in merged["notes"]))
        for arguments in (
            {"group_by": ["thanh_pho"]},
            {"filters": [{"column": "thanh_pho", "operator": "equals", "value": "Hue"}]},
        ):
            output = toolkit.query_metric(metric="tong_luong_mua", **arguments)
            self.assertFalse(any("gộp mọi dòng" in note for note in output.get("notes", [])), arguments)

    def test_group_by_points_to_narrower_column_in_other_table(self) -> None:
        catalog = make_catalog()
        fact = catalog.tables[TABLE_ID]
        fact = TableInfo(fact.id, fact.schema, fact.name, fact.label, None, None, (
            *fact.columns, ColumnInfo("vung", "text", "Vùng", None, (), False),
        ))
        city = TableInfo(uuid4(), "weather", "city", "Thành phố", None, None, (
            ColumnInfo("thanh_pho", "text", "Thành phố", None, (), False),
            ColumnInfo("vung_khi_hau", "text", "Vùng khí hậu", None, (), False),
            ColumnInfo("vung", "text", "Vùng", None, (), False),
        ))
        catalog = AgentCatalog(tables={fact.id: fact, city.id: city}, metrics=catalog.metrics, rules=[])
        toolkit = Text2SqlToolkit(catalog, QueryCache(runner=FakeRunner(), max_rows=200), 50)
        notes = toolkit.query_metric(metric="tong_luong_mua", group_by=["vung"])["notes"]
        related = [note for note in notes if "tên gần giống" in note]
        self.assertEqual(len(related), 1)
        self.assertIn("weather.city.vung_khi_hau (Vùng khí hậu)", related[0])
        self.assertNotIn("weather.city.vung ", related[0])
        plain = toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])["notes"]
        self.assertFalse(any("tên gần giống" in note for note in plain))

    def test_column_values_search_ignores_accents(self) -> None:
        runner = ValueRunner(["Ha Noi", "Hai Phong", "Hue"])
        output = self.make(runner).get_column_values("daily", "thanh_pho", search="Hải Phòng")
        self.assertEqual(output["rows"], [["Hai Phong"]])
        self.assertIn("ILIKE '%Hải Phòng%'", runner.calls[0])


class ToolAgentTests(unittest.TestCase):
    def tools(self, runner: FakeRunner):
        return Text2SqlToolkit(make_catalog(), QueryCache(runner=runner, max_rows=200), 50).tools()

    def test_tool_error_goes_back_to_model_which_retries(self) -> None:
        model = ScriptedModel([
            tool_call("query_metric", {"metric": "tong_luong_mua", "group_by": ["quan"]}),
            tool_call("query_metric", {"metric": "tong_luong_mua", "group_by": ["thanh_pho"]}, "c2"),
            AIMessage(content="Huế mưa nhiều nhất."),
        ])
        result = run_tool_agent("prompt", {"question": "q"}, self.tools(FakeRunner()), 5, model)
        self.assertEqual(result.answer, "Huế mưa nhiều nhất.")
        self.assertFalse(result.exhausted)
        first_reply = model.received[1][-1]
        self.assertIsInstance(first_reply, ToolMessage)
        self.assertEqual(first_reply.status, "error")
        self.assertIn("Các cột hợp lệ", json.loads(first_reply.content)["error"])

    def test_repeating_a_failed_call_is_blocked(self) -> None:
        bad = {"sql": "SELECT * FROM other", "purpose": "x"}
        model = ScriptedModel([tool_call("run_sql", bad), tool_call("run_sql", bad, "c2"), AIMessage(content="xong")])
        run_tool_agent("prompt", {}, self.tools(FakeRunner()), 5, model)
        self.assertEqual(json.loads(model.received[2][-1].content)["error"], REPEATED_FAILURE)

    def test_invalid_arguments_are_reported(self) -> None:
        model = ScriptedModel([tool_call("query_metric", {"limit": 5}), AIMessage(content="xong")])
        run_tool_agent("prompt", {}, self.tools(FakeRunner()), 5, model)
        self.assertIn("metric", json.loads(model.received[1][-1].content)["error"])

    def test_exhausted_steps_force_final_answer_without_tools(self) -> None:
        model = ScriptedModel([
            tool_call("get_metric", {"metric": "tong_luong_mua"}), AIMessage(content="Trả lời một phần."),
        ])
        result = run_tool_agent("prompt", {}, self.tools(FakeRunner()), 1, model)
        self.assertTrue(result.exhausted)
        self.assertEqual(result.answer, "Trả lời một phần.")
        self.assertEqual(len(model.bound), 1)
        self.assertEqual(model.received[-1][-1].content, EXHAUSTED_NOTICE)

    def test_every_tool_call_is_reported_with_recorded_step(self) -> None:
        toolkit = Text2SqlToolkit(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), 50)
        events: list[tuple[str, dict]] = []
        model = ScriptedModel([
            tool_call("get_metric", {"metric": "khong_co"}),
            tool_call("query_metric", {"metric": "tong_luong_mua", "group_by": ["thanh_pho"]}, "c2"),
            AIMessage(content="xong"),
        ])
        run_tool_agent(
            "prompt", {}, toolkit.tools(), 5, model,
            on_tool=tool_reporter(3, toolkit, lambda event, data: events.append((event, data))),
        )
        self.assertEqual([(event, data["position"], data["tool"]) for event, data in events], [
            ("tool", 3, "get_metric"), ("tool", 3, "query_metric"),
        ])
        self.assertIsNotNone(events[0][1]["error"])
        self.assertIsNone(events[0][1]["sql"])
        self.assertEqual(events[1][1]["rows"], [["Huế", 12.5]])
        self.assertEqual(events[1][1]["sql"], toolkit.steps[0].sql)


EMPTY_KNOWLEDGE = QuestionKnowledgeOut(
    metrics=[], tables=[], columns=[], glossary=[], expert_rules=[], own_knowledge=[],
)


def make_preprocess(depends_on: list[list[int]]) -> PreprocessOut:
    return PreprocessOut(
        rewritten_question="câu đầy đủ", is_split=len(depends_on) > 1,
        execution_mode="sequential" if any(depends_on) else "parallel",
        questions=[
            PreprocessedQuestionOut(
                position=position, question=f"câu {position}", depends_on=dependencies, question_type="T2",
                business_concepts=[], knowledge=EMPTY_KNOWLEDGE,
            )
            for position, dependencies in enumerate(depends_on, start=1)
        ],
        stages=[],
    )


class ChatGraphTests(unittest.TestCase):
    def run_graph(self, depends_on: list[list[int]], barrier: threading.Barrier | None = None):
        prior_seen: dict[int, list[int]] = {}
        synthesized: list[list[int]] = []

        def answer(preprocess, item, prior, pending=None, reply=None, emit=None):
            if barrier is not None and not item.depends_on:
                barrier.wait()
            prior_seen[item.position] = [answer.position for answer in prior]
            return QuestionAnswerOut(position=item.position, question=item.question, answer=f"đáp án {item.position}")

        def synthesize(preprocess, answers):
            synthesized.append([answer.position for answer in answers])
            return "tổng hợp"

        run = run_chat_graph(ChatGraphContext(
            preprocess=lambda: make_preprocess(depends_on), answer_question=answer, synthesize=synthesize,
        ), "thread-1")
        self.assertIsNone(run.clarification)
        return run.state, prior_seen, synthesized

    def test_independent_questions_run_in_parallel(self) -> None:
        state, _, synthesized = self.run_graph([[], []], threading.Barrier(2, timeout=5))
        self.assertEqual(sorted(state["answers"]), [1, 2])
        self.assertEqual(synthesized, [[1, 2]])
        self.assertEqual(state["answer"], "tổng hợp")

    def test_dependent_question_receives_prior_answers(self) -> None:
        _, prior_seen, _ = self.run_graph([[], [], [1, 2]])
        self.assertEqual(prior_seen, {1: [], 2: [], 3: [1, 2]})

    def test_single_question_skips_synthesis(self) -> None:
        state, _, synthesized = self.run_graph([[]])
        self.assertEqual(state["answer"], "đáp án 1")
        self.assertEqual(synthesized, [])


def pending_question(position: int, question: str, options: list[str] | None = None) -> PendingQuestion:
    messages = [HumanMessage(content="ngữ cảnh"), tool_call("ask_user", {"question": question}, f"ask-{position}")]
    pause = ToolAgentPause(
        tool_call_id=f"ask-{position}", tool="ask_user", payload={"question": question}, messages=messages, rounds=1,
    )
    step = AgentStepOut(tool="ask_user", arguments={"question": question})
    return PendingQuestion(position, question, options or [], pause, [step])


class ClarifyingGraph:
    def __init__(self, depends_on: list[list[int]], asking: dict[int, str]) -> None:
        self.depends_on = depends_on
        self.asking = asking
        self.preprocessed = 0
        self.calls: list[tuple[int, str | None]] = []
        self.received: dict[int, PendingQuestion] = {}
        self.lock = threading.Lock()

    def context(self) -> ChatGraphContext:
        return ChatGraphContext(preprocess=self.preprocess, answer_question=self.answer, synthesize=self.synthesize)

    def preprocess(self) -> PreprocessOut:
        self.preprocessed += 1
        return make_preprocess(self.depends_on)

    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        with self.lock:
            self.calls.append((item.position, reply))
        if pending is not None:
            self.received[item.position] = pending
        if item.position in self.asking and reply is None:
            return pending_question(item.position, self.asking[item.position], ["Huế", "Vinh"])
        suffix = f" ({reply})" if reply else ""
        answer = f"đáp án {item.position}{suffix}"
        return QuestionAnswerOut(position=item.position, question=item.question, answer=answer)

    @staticmethod
    def synthesize(preprocess, answers):
        return " / ".join(answer.answer for answer in answers)


class ChatGraphInterruptTests(unittest.TestCase):
    def test_pause_returns_question_and_resume_skips_finished_work(self) -> None:
        graph = ClarifyingGraph([[], [], [2]], {2: "Thành phố nào?"})
        paused = run_chat_graph(graph.context(), "t-1")
        self.assertEqual(paused.clarification, Clarification("Thành phố nào?", ["Huế", "Vinh"], [2]))
        self.assertIsInstance(paused.snapshot, bytes)
        self.assertEqual(sorted(paused.state["answers"]), [1])
        self.assertNotIn(3, [position for position, _ in graph.calls])
        resumed = run_chat_graph(graph.context(), "t-1", reply="Huế", snapshot=paused.snapshot)
        self.assertIsNone(resumed.clarification)
        self.assertEqual(graph.preprocessed, 1)
        self.assertEqual(graph.calls, [(1, None), (2, None), (2, "Huế"), (3, None)])
        self.assertEqual(resumed.state["answer"], "đáp án 1 / đáp án 2 (Huế) / đáp án 3")
        restored = graph.received[2]
        self.assertIsInstance(restored.pause, ToolAgentPause)
        self.assertIsInstance(restored.pause.messages[1], AIMessage)
        self.assertIsInstance(restored.steps[0], AgentStepOut)

    def test_parallel_branches_pausing_together_ask_once(self) -> None:
        graph = ClarifyingGraph([[], []], {1: "Metric nào?", 2: "Năm nào?"})
        paused = run_chat_graph(graph.context(), "t-2")
        self.assertEqual(paused.clarification.positions, [1, 2])
        self.assertEqual(paused.clarification.question, "1. Metric nào?\n2. Năm nào?")
        self.assertEqual(paused.clarification.options, [])
        resumed = run_chat_graph(graph.context(), "t-2", reply="lượng mưa, 2026", snapshot=paused.snapshot)
        self.assertEqual(sorted(graph.calls[2:]), [(1, "lượng mưa, 2026"), (2, "lượng mưa, 2026")])
        self.assertEqual(sorted(resumed.state["answers"]), [1, 2])

    def test_question_asking_again_pauses_again(self) -> None:
        graph = ClarifyingGraph([[]], {1: "Thành phố nào?"})
        first = run_chat_graph(graph.context(), "t-3")

        def ask_again(preprocess, item, prior, pending=None, reply=None, emit=None):
            graph.calls.append((item.position, reply))
            return pending_question(item.position, "Khoảng thời gian nào?")

        context = ChatGraphContext(preprocess=graph.preprocess, answer_question=ask_again, synthesize=graph.synthesize)
        second = run_chat_graph(context, "t-3", reply="Huế", snapshot=first.snapshot)
        self.assertEqual(second.clarification.question, "Khoảng thời gian nào?")
        third = run_chat_graph(graph.context(), "t-3", reply="tuần trước", snapshot=second.snapshot)
        self.assertEqual(third.state["answer"], "đáp án 1 (tuần trước)")
        self.assertEqual(graph.preprocessed, 1)


class AgentPauseTests(unittest.TestCase):
    def make_run(self, model: ScriptedModel) -> AgentRun:
        return AgentRun(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), date(2026, 11, 19), model)

    def test_ask_user_pauses_and_resume_continues_the_same_conversation(self) -> None:
        model = ScriptedModel([
            tool_call("get_metric", {"metric": "tong_luong_mua"}),
            AIMessage(content="", tool_calls=[
                {"name": "ask_user", "args": {"question": "Thành phố nào?", "options": ["Huế", " Huế", "Vinh"]},
                 "id": "ask"},
                {"name": "ask_user", "args": {"question": "Lần hai?"}, "id": "ask-2"},
            ]),
            AIMessage(content="Huế mưa 12,5 mm."),
        ])
        run = self.make_run(model)
        item = make_preprocess([[]]).questions[0]
        pending = run.answer(make_preprocess([[]]), item, [])
        self.assertIsInstance(pending, PendingQuestion)
        self.assertEqual((pending.question, pending.options), ("Thành phố nào?", ["Huế", "Vinh"]))
        self.assertEqual([step.tool for step in pending.steps], ["ask_user"])
        self.assertEqual(len(model.received), 2)
        answer = run.answer(make_preprocess([[]]), item, [], pending, "Huế")
        self.assertEqual(answer.answer, "Huế mưa 12,5 mm.")
        last = model.received[-1]
        self.assertEqual(json.loads(last[-1].content), {"user_reply": "Huế"})
        self.assertEqual(last[-1].tool_call_id, "ask")
        self.assertIn("Mỗi lượt chỉ dừng", json.loads(last[-2].content)["error"])
        self.assertEqual(answer.steps[0].notes, ["Người dùng trả lời: Huế"])

    def test_ask_user_is_limited_per_question(self) -> None:
        steps = [AgentStepOut(tool="ask_user", arguments={})] * MAX_CLARIFICATIONS
        toolkit = Text2SqlToolkit(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), 50, steps)
        with self.assertRaisesRegex(ToolError, "đủ số lần"):
            toolkit.ask_user("Hỏi nữa?")
        with self.assertRaises(AgentPause):
            Text2SqlToolkit(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), 50).ask_user("Hỏi?")


class DateRangeTests(unittest.TestCase):
    def test_ranges_are_half_open_and_week_starts_monday(self) -> None:
        ranges = date_ranges(date(2026, 3, 4))
        self.assertEqual(ranges["yesterday"], {"from": "2026-03-03", "before": "2026-03-04"})
        self.assertEqual(ranges["last_7_days"], {"from": "2026-02-25", "before": "2026-03-04"})
        self.assertEqual(ranges["last_week"], {"from": "2026-02-23", "before": "2026-03-02"})
        self.assertEqual(ranges["this_week"], {"from": "2026-03-02", "before": "2026-03-09"})
        self.assertEqual(ranges["this_month"], {"from": "2026-03-01", "before": "2026-04-01"})
        self.assertEqual(ranges["last_month"], {"from": "2026-02-01", "before": "2026-03-01"})
        self.assertEqual(date_ranges(date(2026, 1, 31))["last_month"], {"from": "2025-12-01", "before": "2026-01-01"})


class SourceUrlTests(unittest.TestCase):
    def test_missing_or_paused_connection_is_rejected(self) -> None:
        with self.assertRaises(Text2SqlConnectionNotFound):
            source_url(SimpleNamespace(get=lambda model, key: None), uuid4())
        paused = SimpleNamespace(is_active=False, uri_ciphertext="")
        with self.assertRaises(Text2SqlInvalidRequest):
            source_url(SimpleNamespace(get=lambda model, key: paused), uuid4())


class JsonCellTests(unittest.TestCase):
    def test_converts_database_values(self) -> None:
        self.assertEqual(
            [json_cell(value) for value in (Decimal(2), Decimal("2.5"), date(2026, 11, 19), b"x")],
            [2, 2.5, "2026-11-19", "<binary>"],
        )

    def test_non_finite_numbers_stay_valid_json(self) -> None:
        cells = [json_cell(value) for value in (Decimal("NaN"), Decimal("-Infinity"), float("nan"), float("inf"))]
        self.assertEqual(cells, ["NaN", "-Infinity", "nan", "inf"])
        json.loads(json.dumps(cells, allow_nan=False))


CITY_ROWS = [("Huế", Decimal("12.5")), ("Vinh", Decimal(3)), ("Hà Nội", Decimal(1))]
HORIZONTAL = {"type": "bar_horizontal", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "value"}]}}


class ChartToolTests(unittest.TestCase):
    def make(self, runner: FakeRunner | None = None, **options) -> Text2SqlToolkit:
        cache = QueryCache(runner=runner or FakeRunner(rows=list(CITY_ROWS)), max_rows=200)
        return Text2SqlToolkit(make_catalog(), cache, 50, today=date(2026, 11, 20), **options)

    def test_data_step_has_result_id_fields_explanations_and_chart(self) -> None:
        toolkit = self.make(position=2)
        output = toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        step = toolkit.steps[0]
        self.assertEqual((output["result_id"], step.result_id), ("2-1", "2-1"))
        self.assertEqual([item.name for item in step.fields], ["thanh_pho", "value"])
        self.assertEqual([item.kind for item in step.explanations][:2], ["metric", "source"])
        self.assertEqual((step.chart["type"], step.chart_source, step.display), ("bar", "auto", "chart_if_last"))
        self.assertEqual(step.chart_types[-1], "table")
        self.assertEqual(output["chart"], {"type": "bar", "x": "thanh_pho", "y": ["value"]})
        self.assertEqual(output["rows"][0], ["Huế", "12,5"])
        toolkit.run_sql("SELECT thanh_pho, luong_mua AS value FROM daily", "Mưa từng thành phố")
        self.assertEqual(toolkit.steps[-1].result_id, "2-2")
        self.assertEqual(toolkit.steps[-1].explanations[0].kind, "method")

    def test_failed_and_lookup_steps_do_not_count(self) -> None:
        toolkit = self.make()
        with self.assertRaises(ToolError):
            toolkit.run_sql("DELETE FROM daily", "xoá")
        toolkit.run_sql("SELECT thanh_pho, luong_mua AS value FROM daily", "a")
        self.assertEqual([step.result_id for step in toolkit.steps], [None, "1-1"])

    def test_chart_with_call_valid_and_invalid(self) -> None:
        toolkit = self.make()
        output = toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"], chart=HORIZONTAL)
        self.assertEqual((toolkit.steps[0].chart_source, output["display"]), ("agent", "chart"))
        self.assertNotIn("chart_error", output)
        bad = {"type": "bar", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "tong"}]}}
        output = toolkit.run_sql("SELECT thanh_pho, luong_mua AS value FROM daily", "b", chart=bad)
        self.assertIn("không có cột 'tong'", output["chart_error"])
        self.assertEqual(toolkit.steps[-1].chart_source, "auto")
        self.assertIsNone(toolkit.steps[-1].error)

    def test_make_chart_updates_data_step(self) -> None:
        toolkit = self.make()
        toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        output = toolkit.make_chart("1-1", {"type": "pie", "encoding": {
            "x": {"field": "thanh_pho"}, "y": [{"field": "value"}]}})
        self.assertEqual(output, {"result_id": "1-1", "chart": {"type": "pie", "x": "thanh_pho", "y": ["value"]},
                                  "display": "chart"})
        data, chart = toolkit.steps
        self.assertEqual((data.chart["type"], data.chart_source, data.display), ("pie", "agent", "chart"))
        self.assertIn("pie", data.chart_types)
        self.assertEqual((chart.tool, chart.result_id, chart.chart["type"]), ("make_chart", "1-1", "pie"))

    def test_make_chart_errors(self) -> None:
        toolkit = self.make()
        with self.assertRaisesRegex(ToolError, "Không có kết quả '1-1'. Các result_id: chưa có kết quả nào."):
            toolkit.make_chart("1-1", HORIZONTAL)
        toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        with self.assertRaisesRegex(ToolError, "Các result_id: 1-1"):
            toolkit.make_chart("1-7", HORIZONTAL)
        with self.assertRaisesRegex(ToolError, "axes.y2: không hỗ trợ trục y thứ hai"):
            toolkit.make_chart("1-1", {**HORIZONTAL, "axes": {"y2": {}}})
        self.assertEqual([step.tool for step in toolkit.steps], ["make_chart", "query_metric", "make_chart",
                                                                  "make_chart"])
        self.assertTrue(all(step.error for step in toolkit.steps if step.tool == "make_chart"))
        self.assertEqual(toolkit.steps[1].chart_source, "auto")

    def test_repeated_invalid_make_chart_is_blocked(self) -> None:
        toolkit = self.make()
        toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        bad = {"result_id": "1-1", "chart": {"type": "stacked_bar"}}
        model = ScriptedModel([tool_call("make_chart", bad), tool_call("make_chart", bad, "c2"),
                               AIMessage(content="xong")])
        run_tool_agent("prompt", {}, toolkit.tools(), 5, model)
        self.assertIn("bar_stacked", json.loads(model.received[1][-1].content)["error"])
        self.assertEqual(json.loads(model.received[2][-1].content)["error"], REPEATED_FAILURE)

    def test_resume_keeps_result_counter(self) -> None:
        first = self.make()
        first.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        old = [AgentStepOut.model_validate({key: value for key, value in step.model_dump().items()
                                            if key in ("tool", "arguments", "sql", "rows", "row_count")})
               for step in first.steps]
        resumed = self.make(steps=old)
        output = resumed.run_sql("SELECT thanh_pho, luong_mua AS value FROM daily", "x")
        self.assertEqual(output["result_id"], "1-2")

    def test_display_values_and_enabled_types(self) -> None:
        toolkit = self.make(runner=FakeRunner(rows=[("Huế", Decimal(1))]))
        toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        self.assertEqual(toolkit.steps[0].display, "none")
        limited = self.make(enabled=frozenset({"line", "table"}))
        output = limited.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])
        self.assertEqual((output["chart"]["type"], output["chart_types"], output["display"]),
                         ("table", ["table"], "none"))
        with self.assertRaisesRegex(ToolError, "chưa được hỗ trợ"):
            limited.make_chart("1-1", HORIZONTAL)

    def test_toolkit_defaults_without_position(self) -> None:
        toolkit = Text2SqlToolkit(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), 50)
        self.assertEqual(toolkit.query_metric(metric="tong_luong_mua", group_by=["thanh_pho"])["result_id"], "1-1")
        self.assertIn("make_chart", [tool.name for tool in toolkit.tools()])


if __name__ == "__main__":
    unittest.main()
