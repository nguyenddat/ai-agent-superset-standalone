import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.agent_package.agents.dataset_plan_agent import DatasetPlanDraft, DatasetSelectDraft
from backend.agent_package.agents.query_plan_agent import DraftQuery, PlanDraft
from backend.agent_package.errors import AgentUnavailableError
from backend.common.base_model import Base
from backend.core.setting import config
from backend.main import app
from backend.modules.conversation.models import Conversation, ConversationTurn
from backend.modules.conversation.services import ConversationService
from backend.modules.conversation.utils.exceptions import ConversationNotFoundError, ConversationTurnNotContinuableError
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.text2sql.chat.events import ChatEvent
from backend.modules.text2sql.chat.pipeline import ChatPipeline
from backend.modules.text2sql.chat.suggestions import SuggestionService
from backend.modules.text2sql.chat.turns import TurnRequest
from backend.modules.text2sql.common.errors import Text2SqlChatTurnInvalid, Text2SqlJoinChoiceOutdated
from backend.modules.text2sql.routes.chat import get_chat_pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_text2sql_chat_pipeline as base  # noqa: E402

URL = "/api/v1/text2sql/chat"
HISTORY_KEYS = {"question", "rewritten_question", "status", "answer", "clarification_question"}


class ChatConversationTests(unittest.TestCase):
    setUp = base.ChatPipelineTests.setUp
    build_catalog = base.ChatPipelineTests.build_catalog
    runner = base.ChatPipelineTests.runner
    clients = base.ChatPipelineTests.clients
    pipeline = base.ChatPipelineTests.pipeline
    column_hits = base.ChatPipelineTests.column_hits
    metric_hit = base.ChatPipelineTests.metric_hit
    final = base.ChatPipelineTests.final
    datasets = base.ChatPipelineTests.datasets

    def chat(self, question: str, turn_request: TurnRequest, **overrides) -> list:
        return list(self.pipeline(**overrides).run(self.connection_id, question, "alice", turn_request))

    def turns(self) -> list[ConversationTurn]:
        with Session(self.engine) as s:
            return list(s.scalars(select(ConversationTurn).order_by(ConversationTurn.created_at,
                                                                   ConversationTurn.sequence)))

    def turn(self, turn_id) -> ConversationTurn:
        with Session(self.engine) as s:
            return s.get(ConversationTurn, UUID(str(turn_id)))

    def ids(self, events) -> dict:
        self.assertEqual(events[0].event, "turn")
        return events[0].data

    def prepare(self, **values) -> TurnRequest:
        for key in ("conversation_id", "previous_turn_id"):
            if isinstance(values.get(key), str):
                values[key] = UUID(values[key])
        return self.pipeline().prepare_turn(self.connection_id, values.pop("user_id", "alice"), **values)

    def metric_plan(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=["B1. Đếm"], status="ok",
                                     queries=[DraftQuery(metric_id=str(self.metric_id))], reason="Đếm đơn.")
        self.rows = [(6,), (7,), (8,)]

    def ambiguous(self) -> list:
        self.column_hits("orders.total", "locations.city")
        self.script.dataset = base.dataset_plan(
            tables=["public.orders", "public.locations"], group_by=["locations.city"],
            select=[DatasetSelectDraft(column="locations.city"),
                    DatasetSelectDraft(column="orders.id", aggregation="count", alias="orders")],
            assumptions=["Tính mọi đơn"],
        )
        return self.chat("Số đơn theo thành phố?", TurnRequest("alice"))

    def test_a_new_conversation_records_the_whole_turn(self) -> None:
        self.metric_plan()
        events = self.chat("  Có bao nhiêu đơn hàng?  ", TurnRequest("alice"), max_stored_rows=2)
        ids = self.ids(events)
        done = self.final(events)
        self.assertEqual((done["conversation_id"], done["turn_id"]), (ids["conversation_id"], ids["turn_id"]))
        self.assertEqual(events[0].to_sse().split("\n")[0], "event: turn")
        [turn] = self.turns()
        self.assertEqual(str(turn.id), ids["turn_id"])
        self.assertEqual((turn.status, turn.flow, turn.sequence), ("answered", "metric", 1))
        self.assertEqual(turn.question, "Có bao nhiêu đơn hàng?")
        self.assertEqual(turn.rewritten_question, "Có bao nhiêu đơn hàng? (viết lại)")
        self.assertEqual(turn.answer, "Kết luận: doanh thu đã có.")
        self.assertEqual((turn.model, turn.error_code, turn.error_message), (config.openrouter_model, None, None))
        self.assertIsNotNone(turn.duration_ms)
        self.assertEqual(turn.assumptions, [])
        self.assertEqual(turn.rewrite["changes"], ["c"])
        self.assertEqual(turn.results[0]["kind"], "metric")
        self.assertEqual(turn.results[0]["metric"]["name"], "order_count")
        self.assertEqual((turn.results[0]["rows"], turn.results[0]["stored_truncated"]), ([[6], [7]], True))
        self.assertEqual(turn.pii["confirmation"], "not_supported")
        steps = {item["step"]: item for item in turn.steps}
        self.assertEqual(list(steps)[:3], ["rewrite", "metric_search", "metric_query"])
        self.assertEqual(steps["rewrite"]["reasoning"], [{"source": "model", "text": "B1. Đọc câu hỏi"},
                                                          {"source": "model", "text": "B2. Giữ nguyên"}])
        self.assertEqual(steps["rewrite"]["detail"]["rewritten_question"], "Có bao nhiêu đơn hàng? (viết lại)")
        self.assertEqual(steps["analysis"]["status"], "done")
        self.assertIsNone(turn.continuation)
        with Session(self.engine) as s:
            conversation = s.get(Conversation, turn.conversation_id)
            self.assertEqual((conversation.user_id, conversation.title), ("alice", "Có bao nhiêu đơn hàng?"))
            self.assertEqual(SuggestionService(s).suggest(self.connection_id, "alice")[0].question,
                             "Có bao nhiêu đơn hàng?")
            self.assertEqual(SuggestionService(s).suggest(self.connection_id, "alice")[0].source, "history")
            self.assertEqual(ConversationService(s).metric_usage(self.connection_id)["order_count"], 1)
        self.assertEqual(base.TrackedSession.closed_count, 2)

    def test_without_a_turn_request_nothing_is_recorded(self) -> None:
        events = list(self.pipeline().run(self.connection_id, "Doanh thu?", "alice"))
        self.assertNotIn("turn", [event.event for event in events])
        self.assertNotIn("turn_id", self.final(events))
        self.assertEqual(self.turns(), [])

    def test_follow_up_questions_send_a_compact_history_to_the_rewrite(self) -> None:
        contexts: list[dict] = []

        def rewrite(context):
            contexts.append(context)
            return self.script.rewrite(context)

        self.metric_plan()
        rewriter = SimpleNamespace(stream=base.streamed(rewrite))
        first = self.ids(self.chat("Số đơn tháng này?", TurnRequest("alice"), rewriter=rewriter))
        conversation_id = first["conversation_id"]
        request = self.prepare(conversation_id=conversation_id)
        second = self.ids(self.chat("còn tháng trước thì sao?", request, rewriter=rewriter))
        self.assertEqual(second["conversation_id"], conversation_id)
        self.assertNotIn("history", contexts[0])
        history = contexts[1]["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(set(history[0]), HISTORY_KEYS)
        self.assertEqual(history[0]["question"], "Số đơn tháng này?")
        self.assertEqual(history[0]["rewritten_question"], "Số đơn tháng này? (viết lại)")
        self.assertEqual(history[0]["status"], "answered")
        self.assertNotIn("rows", json.dumps(history))
        self.assertEqual([turn.sequence for turn in self.turns()], [1, 2])

    def test_history_is_capped_at_six_turns_and_answers_are_clipped(self) -> None:
        with Session(self.engine) as s:
            service = ConversationService(s)
            conversation = service.start(self.connection_id, "alice", "Câu 1")
            for index in range(1, 9):
                turn = service.begin_turn(conversation, f"Câu {index}")
                service.complete_turn(turn, status="answered", flow="metric", answer="chữ " * 300,
                                      results=[{"kind": "metric", "rows": [["bí mật"]]}])
            s.commit()
            conversation_id = conversation.id
        contexts: list[dict] = []

        def rewrite(context):
            contexts.append(context)
            return self.script.rewrite(context)

        self.chat("Tiếp", self.prepare(conversation_id=conversation_id),
                  rewriter=SimpleNamespace(stream=base.streamed(rewrite)))
        history = contexts[0]["history"]
        self.assertEqual([item["question"] for item in history], [f"Câu {index}" for index in range(3, 9)])
        self.assertTrue(all(len(item["answer"]) <= 501 for item in history))
        self.assertNotIn("bí mật", json.dumps(history, ensure_ascii=False))

    def test_clarification_options_reach_done_the_turn_and_the_next_history(self) -> None:
        self.column_hits("orders.total", "customers.region")
        self.script.dataset = DatasetPlanDraft.model_validate({
            "analysis": ["B1"], "status": "needs_clarification", "clarification_question": "Xem chỉ số nào?",
            "clarification_options": ["Tổng tiền", " Số đơn ", "Tổng tiền", "", "A", "B", "C"],
        })
        events = self.chat("Tình hình đơn hàng?", TurnRequest("alice"))
        done = self.final(events)
        self.assertEqual(done["clarification_options"], ["Tổng tiền", "Số đơn", "A", "B"])
        turn = self.turns()[0]
        self.assertEqual((turn.status, turn.clarification_question), ("needs_clarification", "Xem chỉ số nào?"))
        self.assertEqual(turn.clarification_options, ["Tổng tiền", "Số đơn", "A", "B"])
        with Session(self.engine) as s:
            [entry] = ConversationService(s).recent_history(turn.conversation_id)
            self.assertEqual(entry.clarification_question, "Xem chỉ số nào?")
            stored = ConversationService(s).get_turn(turn.conversation_id, turn.id, "alice")
            self.assertEqual(stored["clarification_options"], ["Tổng tiền", "Số đơn", "A", "B"])

    def test_metric_clarification_options_and_no_options_by_default(self) -> None:
        self.metric_hit()
        self.script.plan = PlanDraft(analysis=[], status="needs_clarification", clarification_question="Năm nào?",
                                     clarification_options=["2025", "2026"])
        self.assertEqual(self.final(self.chat("Số đơn?", TurnRequest("alice")))["clarification_options"],
                         ["2025", "2026"])
        self.script.plan = PlanDraft(analysis=[], status="needs_clarification", clarification_question="Năm nào?")
        self.assertNotIn("clarification_options", self.final(self.chat("Số đơn?", TurnRequest("alice"))))

    def test_terminal_statuses_and_errors_are_recorded(self) -> None:
        self.column_hits("orders.total", "weather.temp")
        self.script.dataset = base.dataset_plan(
            tables=["public.orders", "public.weather"], group_by=[],
            select=[DatasetSelectDraft(column="orders.total", aggregation="sum"),
                    DatasetSelectDraft(column="weather.temp", aggregation="avg")],
        )
        self.chat("Đơn và thời tiết?", TurnRequest("alice"))
        self.index.hits = {}
        self.chat("Không có gì?", TurnRequest("alice"))

        def broken(context):
            raise AgentUnavailableError()

        self.chat("Lỗi bước đầu?", TurnRequest("alice"), rewriter=SimpleNamespace(stream=broken))
        self.script.analysis_error = AgentUnavailableError()
        events = self.chat("Lỗi phân tích?", TurnRequest("alice"))
        self.assertEqual(events[-1].event, "error")
        turns = self.turns()
        self.assertEqual([turn.status for turn in turns], ["join_not_declared", "cannot_answer", "error", "error"])
        self.assertEqual([turn.error_code for turn in turns], [None, None, "agent_unavailable", "agent_unavailable"])
        self.assertIn("AgentUnavailableError", turns[2].error_message)
        self.assertEqual(turns[2].flow, "none")
        self.assertEqual(turns[3].answer, "Kết luận: doanh thu đã có.")
        with Session(self.engine) as s:
            output = ConversationService(s).get_turn(turns[3].conversation_id, turns[3].id, "alice")
        self.assertNotIn("error_message", output)
        self.assertEqual(output["error_code"], "agent_unavailable")

    def test_a_disconnect_closes_the_turn_instead_of_leaving_it_running(self) -> None:
        stream = self.pipeline().run(self.connection_id, "Doanh thu?", "alice", TurnRequest("alice"))
        self.assertEqual(next(stream).event, "turn")
        self.assertEqual(next(stream).data["step"], "rewrite")
        self.assertEqual(self.turns()[0].status, "running")
        stream.close()
        turn = self.turns()[0]
        self.assertEqual((turn.status, turn.error_code), ("error", "client_disconnected"))
        self.assertEqual(turn.steps[0]["step"], "rewrite")
        self.assertTrue(self.index.closed)
        self.assertEqual(base.TrackedSession.closed_count, 2)

    def test_prepare_checks_owner_connection_and_previous_turn(self) -> None:
        conversation_id = self.ids(self.chat("Câu đầu?", TurnRequest("alice")))["conversation_id"]
        with self.assertRaises(ConversationNotFoundError):
            self.prepare(user_id="bob", conversation_id=conversation_id)
        with Session(self.engine) as s:
            other = DatabaseConnection(name=f"o-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            s.add(other)
            s.commit()
            other_id = other.id
        with self.assertRaises(Text2SqlChatTurnInvalid):
            self.pipeline().prepare_turn(other_id, "alice", UUID(conversation_id))
        answered = self.turns()[0].id
        with self.assertRaises(ConversationTurnNotContinuableError):
            self.prepare(conversation_id=conversation_id, previous_turn_id=answered, join_signature="x")

    def test_choosing_a_join_continues_without_rewriting_or_planning(self) -> None:
        events = self.ambiguous()
        ids = self.ids(events)
        self.assertEqual(self.final(events)["status"], "join_ambiguous")
        detail = next(event.data["detail"] for event in events
                      if event.event == "step" and event.data["step"] == "join_plan" and event.data["status"] == "done")
        signatures = [option["signature"] for option in detail["options"]]
        previous = self.turn(ids["turn_id"])
        self.assertEqual(previous.continuation["signatures"], signatures)
        self.assertEqual(previous.continuation["assumptions"], ["Tính mọi đơn"])
        self.assertEqual(previous.steps[-2]["step"], "join_plan")
        calls = dict(self.script.calls)
        request = self.prepare(conversation_id=ids["conversation_id"], previous_turn_id=ids["turn_id"],
                               join_signature=signatures[1])
        events = self.chat(request.resume.question, request)
        resumed = self.ids(events)
        self.assertEqual(resumed["conversation_id"], ids["conversation_id"])
        self.assertEqual({key: self.script.calls[key] for key in ("rewrite", "plan", "dataset")},
                         {key: calls[key] for key in ("rewrite", "plan", "dataset")})
        self.assertEqual(self.script.calls["analysis"], calls["analysis"] + 1)
        steps = [(event.data["step"], event.data["status"]) for event in events if event.event == "step"]
        self.assertEqual(steps, [("join_plan", "started"), ("join_plan", "done"), ("dataset_query", "started"),
                                 ("dataset_query", "done"), ("analysis", "started"), ("analysis", "done")])
        done = self.final(events)
        self.assertEqual((done["status"], done["flow"], done["assumptions"]), ("answered", "dataset", ["Tính mọi đơn"]))
        [dataset] = self.datasets()
        self.assertEqual(dataset.signature, signatures[1])
        turn = self.turn(resumed["turn_id"])
        self.assertEqual((turn.status, turn.continued_from, turn.sequence), ("answered", previous.id, 2))
        self.assertEqual(turn.question, "Số đơn theo thành phố?")
        self.assertEqual(turn.rewritten_question, "Số đơn theo thành phố? (viết lại)")
        self.assertEqual(turn.results[0]["kind"], "dataset")
        self.assertEqual(self.script.contexts["analysis"][-1]["join"]["status"], "ok")
        self.assertIsNone(turn.continuation)

    def test_an_unknown_or_outdated_signature_is_rejected(self) -> None:
        ids = self.ids(self.ambiguous())
        with self.assertRaises(Text2SqlChatTurnInvalid):
            self.prepare(conversation_id=ids["conversation_id"], previous_turn_id=ids["turn_id"],
                         join_signature="khong-co")
        with Session(self.engine) as s:
            turn = s.get(ConversationTurn, UUID(ids["turn_id"]))
            turn.continuation = {**turn.continuation, "signatures": [*turn.continuation["signatures"], "cu"]}
            s.commit()
        with self.assertRaises(Text2SqlJoinChoiceOutdated):
            self.prepare(conversation_id=ids["conversation_id"], previous_turn_id=ids["turn_id"],
                         join_signature="cu")


class ScriptedPipeline(ChatPipeline):
    def __init__(self, engine) -> None:
        super().__init__(session_factory=lambda: Session(engine))
        self.requests: list = []

    def run(self, connection_id, question, user_id=None, turn_request=None):
        self.requests.append((question, turn_request))
        yield ChatEvent("turn", {"conversation_id": "c", "turn_id": "t"})
        yield ChatEvent("done", {"status": "answered", "flow": "metric"})


class ChatRouteConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                         connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            first = DatabaseConnection(name=f"a-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            second = DatabaseConnection(name=f"b-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            s.add_all([first, second])
            s.flush()
            service = ConversationService(s)
            conversation = service.start(first.id, "alice", "Câu đầu")
            answered = service.begin_turn(conversation, "Câu đầu")
            service.complete_turn(answered, status="answered", flow="metric")
            s.commit()
            self.first, self.second = str(first.id), str(second.id)
            self.conversation, self.answered = str(conversation.id), str(answered.id)
        self.pipeline = ScriptedPipeline(self.engine)
        app.dependency_overrides[get_chat_pipeline] = lambda: self.pipeline
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def post(self, **body):
        return self.client.post(URL, json={"connection_id": self.first, **body})

    def test_turn_fields_are_validated_before_streaming(self) -> None:
        cases = [
            ({"question": "q", "conversation_id": self.conversation}, 422),
            ({"question": "q", "user_id": "alice", "conversation_id": self.conversation,
              "previous_turn_id": self.answered}, 422),
            ({"user_id": "alice", "conversation_id": self.conversation}, 422),
            ({"question": "q", "user_id": "alice", "previous_turn_id": self.answered, "join_signature": "s"}, 422),
            ({"question": "q", "user_id": "bob", "conversation_id": self.conversation}, 404),
            ({"question": "q", "user_id": "alice", "conversation_id": str(uuid4())}, 404),
            ({"question": "q", "user_id": "alice", "conversation_id": self.conversation, "connection_id": self.second},
             422),
            ({"user_id": "alice", "conversation_id": self.conversation, "previous_turn_id": str(uuid4()),
              "join_signature": "s"}, 404),
            ({"user_id": "alice", "conversation_id": self.conversation, "previous_turn_id": self.answered,
              "join_signature": "s"}, 409),
        ]
        for body, status in cases:
            with self.subTest(body=body):
                response = self.post(**body)
                self.assertEqual(response.status_code, status, response.text)
                self.assertTrue(response.headers["content-type"].startswith("application/json"))
        self.assertEqual(self.pipeline.requests, [])

    def test_a_user_without_conversation_starts_a_new_one_and_the_turn_event_streams(self) -> None:
        response = self.post(question="Doanh thu?", user_id=" alice ")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith('event: turn\ndata: {"conversation_id":"c","turn_id":"t"}'))
        question, request = self.pipeline.requests[0]
        self.assertEqual((question, request.user_id, request.conversation_id, request.resume),
                         ("Doanh thu?", "alice", None, None))
        response = self.post(question="Tiếp?", user_id="alice", conversation_id=self.conversation)
        self.assertEqual(str(self.pipeline.requests[1][1].conversation_id), self.conversation)
        self.post(question="Một lượt")
        self.assertIsNone(self.pipeline.requests[2][1])


if __name__ == "__main__":
    unittest.main()
