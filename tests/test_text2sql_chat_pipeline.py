import re
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.agent_package.agents.dataset_plan_agent import DatasetPlanDraft, DatasetSelectDraft, DatasetTimeDraft
from backend.agent_package.agents.query_plan_agent import DraftQuery, DraftTime, PlanDraft
from backend.agent_package.agents.question_rewrite_agent import RewriteDraft
from backend.agent_package.errors import AgentUnavailableError
from backend.agent_package.get_chat_models import ReasoningDelta
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
from backend.modules.text2sql.chat.columns import source_data_type
from backend.modules.text2sql.chat.pipeline import INTERNAL_ERROR, NO_FIELDS_MESSAGE, ChatClients, ChatPipeline
from backend.modules.text2sql.common.errors import Text2SqlQueryFailed
from backend.modules.text2sql.dataset.join_graph import JoinGraph
from backend.modules.text2sql.dataset.store import DatasetStore
from backend.modules.text2sql.models import QueryDataset
from backend.modules.text2sql.query.executor import RawResult
from backend.modules.text2sql.query.schemas import ResultColumn
from backend.modules.text2sql.query.service import QueryService, value_types
from backend.modules.text2sql.vector_store.ingestion.documents.context import load_context

register_all_models()
TODAY = date(2026, 4, 2)
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

LAYOUT = {
    ("public", "customers"): [("id", "integer"), ("name", "text"), ("region", "text")],
    ("public", "locations"): [("id", "integer"), ("city", "text")],
    ("public", "orders"): [("id", "integer"), ("customer_id", "integer"), ("ship_from", "integer"),
                           ("ship_to", "integer"), ("total", "numeric(12,2)"), ("status", "text")],
    ("public", "items"): [("id", "integer"), ("order_id", "integer"), ("qty", "integer")],
    ("public", "weather"): [("day", "date"), ("temp", "numeric")],
    ("archive", "orders"): [("id", "integer"), ("total", "numeric(12,2)")],
}
RELATIONS = [
    ("orders.customer_id", "customers.id"), ("orders.ship_from", "locations.id"), ("orders.ship_to", "locations.id"),
    ("items.order_id", "orders.id"),
]


def point(entity_id, text, topic, table_id=None):
    return {"score": 0.9, "payload": {
        "entity_id": str(entity_id), "table_id": str(table_id) if table_id else None, "text": text,
        "name": text, "display_name": text, "topic": topic,
    }}


class FakeIndex:
    def __init__(self):
        self.hits: dict[str, list] = {}
        self.closed = False

    def search(self, question, vector, connection_id, topic, limit, filters=None):
        return list(self.hits.get(topic, []))

    def close(self):
        self.closed = True


class FakeEmbedding:
    closed = False

    def embed(self, texts):
        return [[0.1] * 4 for _ in texts]

    def close(self):
        self.closed = True


class Script:
    def __init__(self):
        self.plan = PlanDraft(analysis=[], status="no_metric", reason="Không có metric phù hợp.")
        self.dataset: DatasetPlanDraft | None = None
        self.chunks: list[str] = ["Kết luận: ", "doanh thu ", "đã có."]
        self.analysis_error: Exception | None = None
        self.calls = {"rewrite": 0, "plan": 0, "dataset": 0, "analysis": 0}
        self.contexts: dict[str, list] = {"plan": [], "dataset": [], "analysis": []}

    def rewrite(self, context):
        self.calls["rewrite"] += 1
        return RewriteDraft(analysis=["B1. Đọc câu hỏi", "B2. Giữ nguyên"],
                            rewritten_question=context["question"] + " (viết lại)", changes=["c"])

    def make_plan(self, context):
        self.calls["plan"] += 1
        self.contexts["plan"].append(context)
        return self.plan

    def make_dataset(self, context):
        self.calls["dataset"] += 1
        self.contexts["dataset"].append(context)
        return self.dataset

    def stream(self, context):
        self.calls["analysis"] += 1
        self.contexts["analysis"].append(context)
        for chunk in self.chunks:
            yield chunk
        if self.analysis_error is not None:
            raise self.analysis_error


def streamed(make):
    def stream(context):
        draft = make(context)
        for index, line in enumerate(draft.analysis):
            yield ReasoningDelta(index, line[:3])
            if line[3:]:
                yield ReasoningDelta(index, line[3:])
        return draft

    return stream


class FakeReranker:
    def __init__(self, metric_score: float, column_score: float = 0.9):
        self.scores = {"metric": metric_score, "column": column_score}

    def rerank(self, question, passages, subject="metric"):
        return [self.scores.get(subject, 0.9)] * len(passages)


class TrackedSession(Session):
    closed_count = 0

    def close(self) -> None:
        TrackedSession.closed_count += 1
        super().close()


def dataset_plan(**fields) -> DatasetPlanDraft:
    defaults = {"analysis": ["B1"], "status": "ok", "root_table": "public.orders",
                "tables": ["public.orders", "public.customers"],
                "select": [DatasetSelectDraft(column="customers.region"),
                           DatasetSelectDraft(column="orders.total", aggregation="sum", alias="revenue")],
                "group_by": ["customers.region"], "reason": "Doanh thu theo vùng."}
    return DatasetPlanDraft(**{**defaults, **fields})


class ChatPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.build_catalog()
        self.index = FakeIndex()
        self.embedding = FakeEmbedding()
        self.script = Script()
        self.runner_calls: list[str] = []
        self.rows: list[tuple] = [("Bắc", Decimal("350.00")), ("Nam", Decimal("100.00")), (None, Decimal("30.00"))]
        self.runner_error: Exception | None = None
        self.reranker: FakeReranker | None = None
        patcher = patch.object(QueryService, "resolve_source", lambda service, connection_id: make_url("sqlite://"))
        patcher.start()
        self.addCleanup(patcher.stop)
        TrackedSession.closed_count = 0

    def build_catalog(self) -> None:
        with Session(self.engine) as s:
            connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            s.add(connection)
            s.flush()
            schemas = {}
            for name in ("public", "archive"):
                schemas[name] = DatabaseSchema(connection_id=connection.id, name=name)
                s.add(schemas[name])
            s.flush()
            self.t, self.c, dictionaries = {}, {}, {}
            for (schema_name, table_name), columns in LAYOUT.items():
                table = DatabaseTable(schema_id=schemas[schema_name].id, name=table_name, table_type="TABLE")
                s.add(table)
                s.flush()
                prefix = "" if schema_name == "public" else "archive."
                self.t[prefix + table_name] = table.id
                label = {"customers": "Khách hàng", "orders": "Đơn hàng", "locations": "Địa điểm",
                         "items": "Dòng hàng", "weather": "Thời tiết"}[table_name]
                s.add(TableDictionary(table_id=table.id, display_name=label, grain_description=f"Một {label}"))
                for position, (column_name, data_type) in enumerate(columns, start=1):
                    column = DatabaseColumn(
                        table_id=table.id, name=column_name, data_type=data_type, ordinal_position=position,
                        is_nullable=column_name != "id",
                    )
                    s.add(column)
                    s.flush()
                    key = f"{prefix}{table_name}.{column_name}"
                    self.c[key] = column.id
                    dictionaries[key] = ColumnDictionary(
                        column_id=column.id, display_name=key, is_primary_key=column_name == "id" or None,
                        contains_pii=key == "customers.name",
                    )
                    s.add(dictionaries[key])
            s.flush()
            for child, parent in RELATIONS:
                dictionaries[child].referenced_column_id = self.c[parent]
            metric = Metric(table_id=self.t["orders"], name="order_count", label="Số đơn hàng", expression="COUNT(*)")
            s.add(metric)
            s.commit()
            self.connection_id = connection.id
            self.metric_id = metric.id

    def runner(self, url, sql, parameters, expanding, max_rows, timeout):
        self.runner_calls.append(sql)
        if self.runner_error is not None:
            raise self.runner_error
        return RawResult(columns=[], rows=list(self.rows)[:max_rows], elapsed_ms=1)

    def clients(self) -> ChatClients:
        return ChatClients(self.index, self.embedding, self.reranker)

    def pipeline(self, **overrides) -> ChatPipeline:
        script = self.script
        options = {
            "session_factory": lambda: TrackedSession(self.engine), "clients": self.clients,
            "rewriter": SimpleNamespace(stream=streamed(script.rewrite)),
            "planner": SimpleNamespace(stream=streamed(script.make_plan)),
            "dataset_planner": SimpleNamespace(stream=streamed(script.make_dataset)),
            "analyst": SimpleNamespace(stream=script.stream), "runner": self.runner, "today": lambda: TODAY,
        }
        return ChatPipeline(**{**options, **overrides})

    def run_chat(self, question="Doanh thu theo vùng?", **overrides) -> list:
        return list(self.pipeline(**overrides).run(self.connection_id, question, None))

    def column_hits(self, *keys):
        self.index.hits["column"] = [
            point(self.c[key], key, "column", self.t[key.rsplit(".", 1)[0]]) for key in keys
        ]

    def metric_hit(self):
        self.index.hits["metric"] = [point(self.metric_id, "Số đơn hàng", "metric", self.t["orders"])]

    def steps(self, events) -> list[tuple[str, str]]:
        return [(event.data["step"], event.data["status"]) for event in events if event.event == "step"]

    def final(self, events):
        return next(event.data for event in events if event.event == "done")

    def reasoning(self, events, name, source=None) -> list[str]:
        items: dict[int, str] = {}
        for event in events:
            data = event.data
            if event.event == "reasoning" and data["step"] == name and source in (None, data["source"]):
                items[data["index"]] = items.get(data["index"], "") + data["delta"]
        return [items[index] for index in sorted(items)]

    def assert_reasoning_inside_steps(self, events) -> None:
        open_steps: set[str] = set()
        for event in events:
            if event.event == "step":
                if event.data["status"] == "started":
                    open_steps.add(event.data["step"])
                else:
                    open_steps.discard(event.data["step"])
            elif event.event == "reasoning":
                self.assertIn(event.data["step"], open_steps, event.data)
                self.assertIn(event.data["source"], ("model", "server"))
        blob = str([event.data for event in events if event.event == "reasoning"])
        self.assertIsNone(UUID_TEXT.search(blob))
        self.assertNotIn("sqlite://", blob)

    def datasets(self) -> list[QueryDataset]:
        with Session(self.engine) as s:
            return list(s.scalars(select(QueryDataset)))

    def test_metric_flow_emits_events_in_order_and_runs_the_query_masked(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=[], status="ok", queries=[DraftQuery(metric_id=str(self.metric_id))],
                                     reason="Đếm đơn.")
        self.rows = [(6,)]
        events = self.run_chat("Có bao nhiêu đơn hàng?")
        names = [event.event for event in events if event.event != "reasoning"]
        self.assertEqual(names[:6], ["step"] * 5 + ["data"])
        self.assert_reasoning_inside_steps(events)
        self.assertEqual(self.reasoning(events, "rewrite", "model"), ["B1. Đọc câu hỏi", "B2. Giữ nguyên"])
        self.assertEqual(self.reasoning(events, "metric_search", "server"), [
            "Giữ metric 'Số đơn hàng' theo tìm kiếm ngữ nghĩa (chưa chấm được điểm Jev).",
        ])
        self.assertEqual(self.reasoning(events, "metric_query", "server"), [
            "Truy vấn metric 'Số đơn hàng' chạy xong, trả về 1 dòng.",
        ])
        self.assertEqual(self.steps(events), [
            ("rewrite", "started"), ("rewrite", "done"), ("metric_search", "started"), ("metric_search", "done"),
            ("metric_query", "started"), ("metric_query", "done"), ("analysis", "started"), ("analysis", "done"),
        ])
        self.assertEqual(names[-1], "done")
        self.assertEqual(self.final(events), {"status": "answered", "flow": "metric", "assumptions": [],
                                              "message": "Đếm đơn."})
        data = next(event.data for event in events if event.event == "data")
        self.assertEqual((data["kind"], data["rows"], data["metric"]["label"]), ("metric", [[6]], "Số đơn hàng"))
        self.assertEqual(data["pii"]["confirmation"], "not_supported")
        rewrite = next(event.data["detail"] for event in events
                       if event.event == "step" and event.data["step"] == "rewrite" and event.data["status"] == "done")
        self.assertEqual(rewrite["rewritten_question"], "Có bao nhiêu đơn hàng? (viết lại)")
        self.assertEqual(self.script.calls, {"rewrite": 1, "plan": 1, "dataset": 0, "analysis": 1})
        context = self.script.contexts["analysis"][0]
        self.assertEqual((context["flow"], context["status"], context["queries"][0]["rows"]), ("metric", "answered",
                                                                                              [[6]]))

    def test_metric_clarification_runs_nothing_and_asks_back(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=[], status="needs_clarification", clarification_question="Năm nào?")
        events = self.run_chat("Số đơn?")
        self.assertEqual(self.runner_calls, [])
        self.assertEqual(self.final(events), {
            "status": "needs_clarification", "flow": "metric", "assumptions": [], "message": "",
            "clarification_question": "Năm nào?",
        })
        self.assertEqual(self.script.contexts["analysis"][0]["clarification_question"], "Năm nào?")
        self.assertEqual(self.script.calls["dataset"], 0)

    def test_dataset_flow_succeeds_and_saves_the_dataset_only_after_the_run(self) -> None:
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan()
        events = self.run_chat()
        self.assertEqual(self.script.calls["plan"], 0)
        self.assertEqual(self.steps(events), [
            ("rewrite", "started"), ("rewrite", "done"), ("metric_search", "started"), ("metric_search", "done"),
            ("metric_query", "skipped"), ("field_search", "started"), ("field_search", "done"),
            ("dataset_plan", "started"), ("dataset_plan", "done"), ("join_plan", "started"), ("join_plan", "done"),
            ("dataset_query", "started"), ("dataset_query", "done"), ("analysis", "started"), ("analysis", "done"),
        ])
        self.assert_reasoning_inside_steps(events)
        self.assertIn("Chuyển sang luồng dataset", self.reasoning(events, "metric_search", "server")[-1])
        fields = self.reasoning(events, "field_search", "server")
        self.assertEqual(fields[0], "Tìm được 2 cột liên quan trong 2 bảng.")
        self.assertIn("Chưa chấm được điểm liên quan bằng Jev", fields[-1])
        self.assertEqual(self.reasoning(events, "dataset_plan", "model"), ["B1"])
        self.assertEqual(self.reasoning(events, "dataset_plan"), [
            "B1", "Ánh xạ kế hoạch thành công: bảng gốc Đơn hàng, dùng 2 bảng (Đơn hàng, Khách hàng).",
        ])
        join = self.reasoning(events, "join_plan", "server")
        self.assertEqual(join[:2], ["Chỉ có một cách nối hợp lệ nên dùng luôn.", "Bảng gốc: Đơn hàng."])
        self.assertTrue(join[2].startswith("LEFT JOIN: "))
        self.assertEqual(self.reasoning(events, "dataset_query", "server"), [
            "Truy vấn chạy xong, trả về 3 dòng.", "Tạo dataset mới cho cách nối này, thêm 2 cột mới.",
        ])
        data = next(event.data for event in events if event.event == "data")
        self.assertEqual(data["kind"], "dataset")
        self.assertEqual(data["rows"], [["Bắc", "350.00"], ["Nam", "100.00"], [None, "30.00"]])
        self.assertIn('LEFT JOIN "public"."customers"', self.runner_calls[0])
        saved = self.datasets()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].root_table_id, self.t["orders"])
        self.assertEqual(saved[0].selected_column_ids, [str(self.c["customers.region"]), str(self.c["orders.total"])])
        final = self.final(events)
        self.assertEqual((final["status"], final["flow"], final["dataset_id"]), ("answered", "dataset",
                                                                                  str(saved[0].id)))
        context = self.script.contexts["dataset"][0]
        self.assertEqual([table["name"] for table in context["tables"]], ["public.orders", "public.customers"])
        self.assertEqual(context["tables"][0]["short_name"], "orders")
        self.assertEqual(set(context["tables"][0]["fields"][0]), {
            "name", "display_name", "data_type", "semantic_role", "description", "unit", "contains_pii",
        })

    def test_second_run_reuses_the_dataset_and_only_adds_new_columns(self) -> None:
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan()
        first = self.final(self.run_chat())
        self.script.dataset = dataset_plan(select=[
            DatasetSelectDraft(column="customers.region"),
            DatasetSelectDraft(column="orders.id", aggregation="count", alias="so_don"),
        ])
        events = self.run_chat()
        detail = next(event.data["detail"] for event in events
                      if event.event == "step" and event.data["step"] == "dataset_query"
                      and event.data["status"] == "done")
        self.assertEqual((detail["created"], detail["added_columns"]), (False, 1))
        self.assertEqual(self.final(events)["dataset_id"], first["dataset_id"])
        saved = self.datasets()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].selected_column_ids[-1], str(self.c["orders.id"]))
        self.assertEqual(self.reasoning(events, "dataset_query")[-1],
                         "Dùng lại dataset đã lưu với cùng cách nối, thêm 1 cột mới.")

    def test_no_metric_from_the_plan_falls_through_to_the_dataset_flow(self) -> None:
        self.metric_hit()
        self.column_hits("orders.total", "customers.region")
        self.script.plan = PlanDraft(analysis=["B1. Không metric nào đếm doanh thu"], status="no_metric",
                                     reason="Không có metric phù hợp.")
        self.script.dataset = dataset_plan()
        events = self.run_chat()
        self.assertEqual(self.script.calls["plan"], 1)
        self.assertIn(("metric_query", "skipped"), self.steps(events))
        self.assertEqual(self.final(events)["flow"], "dataset")
        self.assertEqual(self.final(events)["status"], "answered")
        self.assert_reasoning_inside_steps(events)
        self.assertEqual(self.reasoning(events, "metric_query"), [
            "B1. Không metric nào đếm doanh thu",
            "Kế hoạch không chọn được metric phù hợp (Không có metric phù hợp.). Chuyển sang luồng dataset: tìm trực "
            "tiếp các cột liên quan trong data dictionary, lập kế hoạch rồi để server tự nối bảng.",
        ])
        sources = [event.data["source"] for event in events
                   if event.event == "reasoning" and event.data["step"] == "metric_query"]
        self.assertEqual(sources, ["model", "model", "server"])

    def test_metric_below_the_jev_threshold_is_dropped_and_the_flow_moves_to_datasets(self) -> None:
        self.metric_hit()
        self.column_hits("orders.total", "customers.region")
        self.reranker = FakeReranker(metric_score=0.2)
        self.script.dataset = dataset_plan()
        events = self.run_chat()
        self.assertEqual(self.script.calls["plan"], 0)
        self.assertEqual(self.reasoning(events, "metric_search"), [
            "Loại metric 'Số đơn hàng': điểm Jev 0.20 dưới ngưỡng 0.60.",
            "Không có metric nào đủ liên quan tới câu hỏi. Chuyển sang luồng dataset: tìm trực tiếp các cột liên quan "
            "trong data dictionary, lập kế hoạch rồi để server tự nối bảng.",
        ])
        self.assertEqual(self.reasoning(events, "field_search")[-1],
                         "Các cột đã được Jev chấm điểm và chỉ giữ cột đạt ngưỡng liên quan.")

    def test_metric_above_the_jev_threshold_is_kept_with_its_score(self) -> None:
        self.metric_hit()
        self.reranker = FakeReranker(metric_score=0.85)
        self.script.plan = PlanDraft(analysis=[], status="needs_clarification", clarification_question="Năm nào?")
        events = self.run_chat()
        self.assertEqual(self.reasoning(events, "metric_search"),
                         ["Giữ metric 'Số đơn hàng': điểm Jev 0.85 đạt ngưỡng 0.60."])
        self.assertEqual(self.reasoning(events, "metric_query"),
                         ["Câu hỏi còn mơ hồ nên chưa chạy truy vấn mà hỏi lại người dùng."])

    def test_no_relevant_fields_means_cannot_answer_without_planning(self) -> None:
        events = self.run_chat()
        self.assertEqual(self.reasoning(events, "field_search"),
                         ["Không tìm thấy cột nào đủ liên quan tới câu hỏi nên dừng, không đoán."])
        self.assertEqual(self.script.calls["dataset"], 0)
        self.assertEqual(self.final(events), {"status": "cannot_answer", "flow": "dataset", "assumptions": [],
                                              "message": NO_FIELDS_MESSAGE})
        self.assertIn("diễn đạt lại", self.script.contexts["analysis"][0]["message"])

    def test_plan_agent_cannot_answer_and_clarification_stop_the_flow(self) -> None:
        self.column_hits("orders.total")
        for status, extra in (("cannot_answer", {"reason": "Thiếu cột chi phí."}),
                              ("needs_clarification", {"clarification_question": "Kỳ nào?"})):
            with self.subTest(status=status):
                self.script.dataset = DatasetPlanDraft(analysis=[], status=status, **extra)
                events = self.run_chat()
                self.assertEqual(self.final(events)["status"], status)
                self.assertNotIn(("join_plan", "started"), self.steps(events))
        self.assertEqual(self.runner_calls, [])
        self.assertEqual(self.script.contexts["analysis"][-1]["clarification_question"], "Kỳ nào?")

    def test_unknown_names_are_reported_without_retry_and_without_internal_ids(self) -> None:
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan(select=[DatasetSelectDraft(column="orders.amount", aggregation="sum")],
                                           group_by=[])
        events = self.run_chat()
        self.assertEqual(self.script.calls["dataset"], 1)
        self.assertEqual(self.final(events)["status"], "cannot_answer")
        message = self.script.contexts["analysis"][0]["message"]
        self.assertIn("orders.amount", message)
        self.assertIn("orders.total", message)
        self.assertIsNone(UUID_TEXT.search(message))
        self.assertEqual(self.runner_calls, [])
        self.assert_reasoning_inside_steps(events)
        mapping = self.reasoning(events, "dataset_plan", "server")
        self.assertEqual(len(mapping), 1)
        self.assertTrue(mapping[0].startswith("Không ánh xạ được kế hoạch về bảng và cột thật: "))
        self.assertIn("orders.amount", mapping[0])

    def test_short_table_names_shared_across_schemas_are_ambiguous(self) -> None:
        self.column_hits("orders.total", "archive.orders.total")
        self.script.dataset = dataset_plan(root_table="public.orders", tables=["public.orders"], group_by=[],
                                           select=[DatasetSelectDraft(column="orders.total", aggregation="sum")])
        events = self.run_chat()
        self.assertEqual(self.final(events)["status"], "cannot_answer")
        self.assertIn("trùng giữa nhiều schema", self.script.contexts["analysis"][0]["message"])

    def test_ambiguous_join_stops_and_marks_the_previously_used_option(self) -> None:
        with Session(self.engine) as s:
            plan = JoinGraph(load_context(s, self.connection_id)).plan(
                [self.t["orders"], self.t["locations"]], root=self.t["orders"],
            )
            used = plan.options[1]
            DatasetStore(s).get_or_create(self.connection_id, used)
            s.commit()
        self.column_hits("orders.total", "locations.city")
        self.script.dataset = dataset_plan(tables=["public.orders", "public.locations"],
                                           select=[DatasetSelectDraft(column="locations.city"),
                                                   DatasetSelectDraft(column="orders.id", aggregation="count")],
                                           group_by=["locations.city"])
        events = self.run_chat()
        self.assertEqual(self.final(events)["status"], "join_ambiguous")
        detail = next(event.data["detail"] for event in events
                      if event.event == "step" and event.data["step"] == "join_plan" and event.data["status"] == "done")
        flags = [option["previously_used"] for option in detail["options"]]
        self.assertEqual(flags, [False, True])
        self.assertIn("orders.ship_from", str(detail["options"]))
        self.assertEqual(self.runner_calls, [])
        join = self.script.contexts["analysis"][0]["join"]
        self.assertEqual(join["status"], "ambiguous")
        self.assertIn("đã được dùng", join["options"][1])
        self.assertIsNone(UUID_TEXT.search(str(join)))
        self.assertEqual(len(self.datasets()), 1)
        self.assert_reasoning_inside_steps(events)
        lines = self.reasoning(events, "join_plan", "server")
        self.assertEqual(lines[0], "Có 2 cách nối hợp lệ; không tự chọn mà hỏi lại người dùng.")
        self.assertTrue(lines[1].startswith("Cách 1: Bắt đầu từ Đơn hàng"))
        self.assertNotIn("đã dùng trước đây", lines[1])
        self.assertTrue(lines[2].endswith("(đã dùng trước đây)."))

    def test_undeclared_relation_is_reported_and_never_joined(self) -> None:
        self.column_hits("orders.total", "weather.temp")
        self.script.dataset = dataset_plan(tables=["public.orders", "public.weather"],
                                           select=[DatasetSelectDraft(column="orders.total", aggregation="sum"),
                                                   DatasetSelectDraft(column="weather.temp", aggregation="avg")],
                                           group_by=[])
        events = self.run_chat()
        self.assertEqual(self.final(events)["status"], "join_not_declared")
        self.assertIn("data dictionary", self.script.contexts["analysis"][0]["message"])
        self.assertEqual((self.runner_calls, self.datasets()), ([], []))
        self.assert_reasoning_inside_steps(events)
        lines = self.reasoning(events, "join_plan", "server")
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("Các bảng cần dùng chưa được khai báo quan hệ với nhau nên không tự nối"))
        self.assertIn("public.weather", lines[0])

    def test_compiler_rejection_is_cannot_answer_without_retry(self) -> None:
        self.column_hits("orders.total", "items.qty")
        self.script.dataset = dataset_plan(tables=["public.orders", "public.items"], group_by=[], select=[
            DatasetSelectDraft(expression="SUM(orders.total + items.qty)", alias="mixed"),
        ])
        events = self.run_chat()
        self.assertEqual(self.final(events)["status"], "cannot_answer")
        message = self.script.contexts["analysis"][0]["message"]
        self.assertIn("nhân dòng", message)
        self.assertEqual((self.script.calls["dataset"], self.runner_calls, self.datasets()), (1, [], []))
        self.assert_reasoning_inside_steps(events)
        self.assertTrue(any("nhân số dòng" in line for line in self.reasoning(events, "join_plan")))
        self.assertEqual(self.reasoning(events, "dataset_query"), [f"Không dựng được truy vấn an toàn: {message}"])

    def test_pii_is_always_masked_and_rows_to_the_llm_are_capped(self) -> None:
        self.column_hits("orders.total", "customers.name")
        self.script.dataset = dataset_plan(select=[
            DatasetSelectDraft(column="customers.name"),
            DatasetSelectDraft(column="orders.total", aggregation="sum", alias="revenue"),
        ], group_by=["customers.name"])
        names = ["Nguyễn Văn An", "Trần Thị Bình", "Lê Hoàng Cường", "Phạm Minh Dũng"]
        self.rows = [(name, Decimal(index)) for index, name in enumerate(names)]
        events = self.run_chat(max_rows_to_llm=2)
        data = next(event.data for event in events if event.event == "data")
        self.assertEqual(len(data["rows"]), 4)
        self.assertEqual(data["pii"]["confirmation"], "not_supported")
        self.assertTrue(all(str(row[0]).startswith("<PII") for row in data["rows"]))
        context = self.script.contexts["analysis"][0]
        self.assertEqual((len(context["queries"][0]["rows"]), context["queries"][0]["row_count"]), (2, 4))
        self.assertEqual(context["pii"]["masked_columns"], ["customers_name"])
        blob = str([event.data for event in events]) + str(context)
        self.assertFalse([name for name in names if name in blob])
        self.assert_reasoning_inside_steps(events)
        self.assertEqual(self.reasoning(events, "dataset_query")[0],
                         "Truy vấn chạy xong, trả về 4 dòng. Các cột chứa dữ liệu cá nhân đã được che: customers_name.")

    def test_a_failed_query_writes_no_dataset_and_still_answers_in_words(self) -> None:
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan()
        self.runner_error = Text2SqlQueryFailed()
        events = self.run_chat()
        self.assertEqual(self.datasets(), [])
        self.assertEqual(self.final(events), {"status": "error", "flow": "dataset", "assumptions": [],
                                              "message": Text2SqlQueryFailed.message})
        self.assertEqual(self.script.contexts["analysis"][0]["status"], "error")
        self.assertNotIn("data", [event.event for event in events])

    def test_analysis_streams_several_tokens(self) -> None:
        events = self.run_chat()
        tokens = [event.data["text"] for event in events if event.event == "token"]
        self.assertEqual(tokens, ["Kết luận: ", "doanh thu ", "đã có."])

    def test_a_broken_analysis_agent_sends_error_and_ends(self) -> None:
        self.script.analysis_error = AgentUnavailableError()
        events = self.run_chat()
        self.assertEqual(events[-1].event, "error")
        self.assertEqual(events[-1].data["code"], "agent_unavailable")
        self.assertNotIn("done", [event.event for event in events])

    def test_an_earlier_agent_failure_still_goes_through_analysis(self) -> None:
        def broken(context):
            raise AgentUnavailableError()

        events = self.run_chat(rewriter=SimpleNamespace(stream=broken))
        self.assertEqual(self.final(events), {"status": "error", "flow": "none", "assumptions": [],
                                              "message": AgentUnavailableError.message})
        self.assertEqual(self.script.contexts["analysis"][0]["status"], "error")

    def test_disconnecting_mid_stream_closes_clients_and_session(self) -> None:
        stream = self.pipeline().run(self.connection_id, "Doanh thu?", None)
        first = next(stream)
        self.assertEqual(first.data["step"], "rewrite")
        stream.close()
        self.assertTrue(self.index.closed)
        self.assertTrue(self.embedding.closed)
        self.assertEqual(TrackedSession.closed_count, 1)

    def test_clients_are_closed_after_a_normal_run(self) -> None:
        self.run_chat()
        self.assertTrue(self.index.closed)
        self.assertEqual(TrackedSession.closed_count, 1)

    def test_an_agent_failing_mid_reasoning_keeps_what_was_streamed_and_reports_an_error(self) -> None:
        closed: list[bool] = []

        def broken(context):
            try:
                yield ReasoningDelta(0, "B1. Đang ")
                raise AgentUnavailableError()
            finally:
                closed.append(True)

        events = self.run_chat(rewriter=SimpleNamespace(stream=broken))
        self.assertEqual(self.reasoning(events, "rewrite", "model"), ["B1. Đang "])
        self.assertNotIn(("rewrite", "done"), self.steps(events))
        self.assertEqual(self.final(events), {"status": "error", "flow": "none", "assumptions": [],
                                              "message": AgentUnavailableError.message})
        self.assertEqual(closed, [True])

    def test_disconnecting_during_model_reasoning_closes_the_agent_stream(self) -> None:
        closed: list[bool] = []

        def endless(context):
            try:
                while True:
                    yield ReasoningDelta(0, "x")
            finally:
                closed.append(True)

        stream = self.pipeline(rewriter=SimpleNamespace(stream=endless)).run(self.connection_id, "Doanh thu?", None)
        self.assertEqual(next(stream).event, "step")
        self.assertEqual(next(stream).data, {"step": "rewrite", "source": "model", "index": 0, "delta": "x"})
        stream.close()
        self.assertEqual(closed, [True])
        self.assertEqual(TrackedSession.closed_count, 1)

    def test_sse_format_is_one_json_line_per_event(self) -> None:
        events = self.run_chat()
        text = next(event for event in events if event.event == "step" and event.data["status"] == "done").to_sse()
        self.assertTrue(text.startswith("event: step\ndata: {"))
        self.assertTrue(text.endswith("}\n\n"))
        self.assertEqual(text.count("\n"), 3)
        self.assertIn("viết lại", text)
        thought = next(event for event in events if event.event == "reasoning").to_sse()
        self.assertEqual(
            thought, 'event: reasoning\ndata: {"step":"rewrite","source":"model","index":0,"delta":"B1."}\n\n',
        )

    def describe(self, key: str, **values) -> None:
        with Session(self.engine) as s:
            dictionary = s.scalar(select(ColumnDictionary).where(ColumnDictionary.column_id == self.c[key]))
            if values.pop("remove", False):
                s.delete(dictionary)
            for name, value in values.items():
                setattr(dictionary, name, value)
            s.commit()

    def add_column(self, table: str, name: str, data_type: str, display_name: str | None = None) -> None:
        with Session(self.engine) as s:
            column = DatabaseColumn(table_id=self.t[table], name=name, data_type=data_type, ordinal_position=99,
                                    is_nullable=True)
            s.add(column)
            s.flush()
            if display_name is not None:
                s.add(ColumnDictionary(column_id=column.id, display_name=display_name))
            s.commit()
            self.c[f"{table}.{name}"] = column.id

    def data_event(self, events) -> dict:
        return next(event.data for event in events if event.event == "data")

    def test_metric_columns_carry_ids_labels_normalized_types_and_metric_format(self) -> None:
        self.add_column("orders", "ordered_at", "timestamp with time zone", "Thời điểm đặt")
        self.describe("orders.status", display_name="Trạng thái", format="upper")
        with Session(self.engine) as s:
            metric = s.get(Metric, self.metric_id)
            metric.expression, metric.format, metric.currency = "SUM(total)", ",.2f", "VND"
            s.commit()
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=[], status="ok", reason="Doanh thu theo tháng.", queries=[DraftQuery(
            metric_id=str(self.metric_id), group_by=["status"],
            time=DraftTime(column="ordered_at", granularity="month"),
        )])
        self.rows = [(datetime(2026, 1, 1, tzinfo=UTC), "paid", Decimal("12.50")),
                     (datetime(2026, 2, 1, tzinfo=UTC), "paid", 3)]
        events = self.run_chat("Doanh thu theo tháng?")
        data = self.data_event(events)
        self.assertEqual(data["columns"], [
            {"name": "Thời điểm đặt (month)", "column_id": str(self.c["orders.ordered_at"]),
             "label": "Thời điểm đặt (theo tháng)", "role": "time", "data_type": "datetime", "format": None,
             "unit": None, "contains_pii": False},
            {"name": "Trạng thái", "column_id": str(self.c["orders.status"]), "label": "Trạng thái",
             "role": "dimension", "data_type": "text", "format": "upper", "unit": None, "contains_pii": False},
            {"name": "Số đơn hàng", "column_id": None, "label": "Số đơn hàng", "role": "metric",
             "data_type": "decimal", "format": ",.2f", "unit": "VND", "contains_pii": False},
        ])
        self.assertEqual([row[2] for row in data["rows"]], ["12.50", 3])
        analysis_columns = self.script.contexts["analysis"][0]["queries"][0]["columns"]
        self.assertEqual(analysis_columns[2], {"name": "Số đơn hàng", "label": "Số đơn hàng", "role": "metric",
                                               "data_type": "decimal", "unit": "VND"})
        self.assertIsNone(UUID_TEXT.search(str(analysis_columns)))

    def test_metric_value_type_falls_back_to_the_expression_when_no_row_has_a_value(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=[], status="ok", queries=[DraftQuery(metric_id=str(self.metric_id))])
        self.rows = []
        column = self.data_event(self.run_chat("Có bao nhiêu đơn?"))["columns"][0]
        self.assertEqual((column["data_type"], column["label"], column["unit"]), ("integer", "Số đơn hàng", None))

    def test_dataset_columns_use_the_dictionary_and_keep_decimals_as_strings(self) -> None:
        self.describe("customers.region", display_name="Vùng")
        self.describe("orders.total", display_name="Tổng tiền", unit="VND", format="#,##0")
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan()
        data = self.data_event(self.run_chat())
        self.assertEqual(data["columns"], [
            {"name": "customers_region", "column_id": str(self.c["customers.region"]), "label": "Vùng",
             "role": "dimension", "data_type": "text", "format": None, "unit": None, "contains_pii": False},
            {"name": "revenue", "column_id": str(self.c["orders.total"]), "label": "Tổng tiền (tổng)",
             "role": "metric", "data_type": "decimal", "format": "#,##0", "unit": "VND", "contains_pii": False},
        ])
        self.assertEqual(data["rows"][0], ["Bắc", "350.00"])

    def test_dataset_columns_without_a_dictionary_fall_back_to_the_result_name(self) -> None:
        self.describe("customers.region", remove=True)
        self.describe("orders.total", remove=True)
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = dataset_plan()
        columns = self.data_event(self.run_chat())["columns"]
        self.assertEqual([(item["label"], item["data_type"], item["unit"]) for item in columns],
                         [("customers_region", "text", None), ("revenue", "decimal", None)])

    def test_dataset_counts_and_time_buckets_get_their_own_types(self) -> None:
        self.add_column("orders", "ordered_on", "date", "Ngày đặt")
        self.describe("orders.id", unit="đơn")
        self.column_hits("orders.id", "orders.ordered_on")
        self.script.dataset = dataset_plan(
            tables=["public.orders"], group_by=[],
            time=DatasetTimeDraft(column="orders.ordered_on", granularity="year"),
            select=[DatasetSelectDraft(column="orders.id", aggregation="count", alias="so_don")],
        )
        self.rows = [(date(2025, 1, 1), 7), (date(2026, 1, 1), 2)]
        data = self.data_event(self.run_chat("Số đơn theo năm?"))
        self.assertEqual([(item["name"], item["label"], item["data_type"], item["unit"]) for item in data["columns"]], [
            ("time_bucket", "Ngày đặt (theo năm)", "date", None),
            ("so_don", "orders.id (số lượng)", "integer", None),
        ])
        self.assertEqual(data["rows"], [["2025-01-01", 7], ["2026-01-01", 2]])

    def test_done_carries_sanitized_assumptions_and_message(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(
            analysis=[], status="ok", queries=[DraftQuery(metric_id=str(self.metric_id))],
            assumptions=[f"Dùng metric {self.metric_id}", "Tính mọi trạng thái"], reason=f"Chọn {self.metric_id}.",
        )
        self.rows = [(6,)]
        final = self.final(self.run_chat("Có bao nhiêu đơn?"))
        self.assertEqual(final["assumptions"], ["Dùng metric 'Số đơn hàng'", "Tính mọi trạng thái"])
        self.assertEqual(final["message"], "Chọn 'Số đơn hàng'.")
        self.assertNotIn("clarification_question", final)
        self.assertIsNone(UUID_TEXT.search(str(final)))

    def test_done_for_a_dataset_clarification_has_the_question_and_assumptions(self) -> None:
        self.column_hits("orders.total")
        self.script.dataset = DatasetPlanDraft(analysis=[], status="needs_clarification", reason="Chưa rõ kỳ.",
                                               clarification_question="Kỳ nào?", assumptions=["Theo ngày đặt"])
        final = self.final(self.run_chat())
        self.assertEqual(final, {
            "status": "needs_clarification", "flow": "dataset", "assumptions": ["Theo ngày đặt"],
            "message": "Chưa rõ kỳ.", "clarification_question": "Kỳ nào?",
        })

    def test_done_for_an_unexpected_error_only_has_the_generic_message(self) -> None:
        def broken(context):
            raise RuntimeError("postgresql://user:secret@host/db failed")

        with self.assertLogs("text2sql.chat", level="ERROR"):
            final = self.final(self.run_chat(rewriter=SimpleNamespace(stream=broken)))
        self.assertEqual(final, {"status": "error", "flow": "none", "assumptions": [], "message": INTERNAL_ERROR})


class ColumnTypeTests(unittest.TestCase):
    def test_postgres_types_are_normalized(self) -> None:
        cases = {
            "integer": "integer", "bigint": "integer", "int4": "integer", "smallserial": "integer",
            "numeric(12,2)": "decimal", "money": "decimal", "double precision": "float", "real": "float",
            "date": "date", "timestamp without time zone": "datetime", "timestamptz": "datetime",
            "boolean": "boolean", "text": "text", "character varying(20)": "text", "uuid": "text",
            "interval": "text", "time without time zone": "text",
        }
        self.assertEqual({name: source_data_type(name) for name in cases}, cases)

    def test_python_value_types_are_read_before_formatting(self) -> None:
        rows = [(1, Decimal("1.5"), None, True, 2.5, date(2026, 1, 1), "a"),
                (2, 3, None, False, 1, datetime(2026, 1, 1), "b")]
        self.assertEqual(value_types(rows, 7), ["integer", "decimal", None, "boolean", "float", None, "text"])

    def test_hidden_fields_do_not_change_the_mcp_output(self) -> None:
        column = ResultColumn(name="m", role="metric", aggregation="sum")
        self.assertEqual(column.model_dump(), {"name": "m", "role": "metric", "column_id": None,
                                               "contains_pii": False})


if __name__ == "__main__":
    unittest.main()
