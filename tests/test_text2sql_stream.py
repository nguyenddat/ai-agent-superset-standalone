import json
import threading
import unittest
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    message_chunk_to_message,
)
from openai import APIConnectionError
from test_text2sql_agent import FakeRunner, make_catalog, make_preprocess
from test_text2sql_chat import (
    CONNECTION_ID,
    PARALLEL_REWRITE,
    REWRITE,
    SINGLE_REWRITE,
    FakeCompletion,
    FakeText,
    read_events,
    stream_service,
)

from backend.agent_package.get_chat_text import get_chat_text
from backend.agent_package.tool_agent import (
    TextStream,
    ToolAgentPause,
    ToolAgentResume,
    run_tool_agent,
)
from backend.core.database import get_database
from backend.main import app
from backend.modules.text2sql.dependencies import (
    get_chat_service,
    get_chat_service_factory,
)
from backend.modules.text2sql.schemas import QuestionAnswerOut
from backend.modules.text2sql.services.agent_tools import QueryCache, Text2SqlToolkit
from backend.modules.text2sql.services.answer_stream import (
    DeltaBuffer,
    SynthesizeStream,
)
from backend.modules.text2sql.services.chat_graph import (
    ChatGraphContext,
    run_chat_graph,
)
from backend.modules.text2sql.services.text2sql_agent_service import (
    AgentRun,
    tool_subject,
)
from backend.modules.text2sql.utils.exceptions import (
    Text2SqlAgentUnavailable,
    Text2SqlClientDisconnected,
)
from tests.service_key import use_service_key

TODAY = date(2026, 11, 20)
SINGLE_QUESTION = SINGLE_REWRITE["rewritten_question"]
FIRST, SECOND = (item["question"] for item in REWRITE["sub_questions"])
QUERY = {"metric": "tong_luong_mua", "group_by": ["thanh_pho"]}


def text(piece: str) -> AIMessageChunk:
    return AIMessageChunk(content=piece)


def call(name: str, args: dict | str, call_id: str = "c1") -> AIMessageChunk:
    raw = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": raw, "id": call_id, "index": 0}])


def merged(chunks: list[AIMessageChunk]) -> AIMessage:
    total = chunks[0]
    for chunk in chunks[1:]:
        total = total + chunk
    return message_chunk_to_message(total)


class StreamModel:
    def __init__(self, scripts: dict[str, list[list[AIMessageChunk]]], after_chunk=None) -> None:
        self.scripts = {question: list(rounds) for question, rounds in scripts.items()}
        self.after_chunk = after_chunk
        self.streamed = 0
        self.invoked = 0
        self.bound = 0
        self.closed = 0
        self.lock = threading.Lock()

    def bind_tools(self, tools):
        self.bound += 1
        return self

    def _next(self, messages) -> list[AIMessageChunk]:
        human = next(message for message in messages if isinstance(message, HumanMessage))
        try:
            question = json.loads(human.content).get("question", "")
        except json.JSONDecodeError:
            question = ""
        with self.lock:
            rounds = self.scripts.get(question) or self.scripts[""]
            return rounds.pop(0)

    def invoke(self, messages):
        self.invoked += 1
        return merged(self._next(messages))

    def stream(self, messages):
        self.streamed += 1
        chunks = self._next(messages)
        try:
            for chunk in chunks:
                yield chunk
                if self.after_chunk is not None:
                    self.after_chunk()
        finally:
            self.closed += 1


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def stream(self) -> TextStream:
        return TextStream(
            delta=lambda round_, piece: self.events.append(("delta", round_, piece)),
            end=lambda round_, discard: self.events.append(("end", round_, discard)),
        )


def toolkit() -> Text2SqlToolkit:
    return Text2SqlToolkit(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), 50)


class ToolAgentStreamTests(unittest.TestCase):
    def test_text_then_tool_call_is_discarded_and_rounds_are_numbered(self) -> None:
        model = StreamModel({"": [
            [text("Để trả lời, "), text("tôi xem chỉ số."), call("query_metric", QUERY)],
            [text("Huế mưa "), text("**12,5 mm**.")],
        ]})
        recorder = Recorder()
        result = run_tool_agent("p", {}, toolkit().tools(), 5, model, on_text=recorder.stream())
        self.assertEqual(result.answer, "Huế mưa **12,5 mm**.")
        self.assertEqual(recorder.events, [
            ("delta", 0, "Để trả lời, "), ("delta", 0, "tôi xem chỉ số."), ("end", 0, True),
            ("delta", 1, "Huế mưa "), ("delta", 1, "**12,5 mm**."), ("end", 1, False),
        ])
        self.assertEqual((model.streamed, model.invoked, model.closed), (2, 0, 2))

    def test_without_on_text_the_model_is_invoked(self) -> None:
        model = StreamModel({"": [[call("query_metric", QUERY)], [text("xong")]]})
        result = run_tool_agent("p", {}, toolkit().tools(), 5, model)
        self.assertEqual(result.answer, "xong")
        self.assertEqual((model.streamed, model.invoked), (0, 2))

    def test_exhausted_round_streams_and_is_never_discarded(self) -> None:
        model = StreamModel({"": [[call("get_metric", {"metric": "tong_luong_mua"})], [text("Một phần.")]]})
        recorder = Recorder()
        result = run_tool_agent("p", {}, toolkit().tools(), 1, model, on_text=recorder.stream())
        self.assertTrue(result.exhausted)
        self.assertEqual(model.bound, 1)
        self.assertEqual(recorder.events, [("end", 0, False), ("delta", 1, "Một phần."), ("end", 1, False)])

    def test_tool_start_comes_before_tool_report_and_skips_ask_user(self) -> None:
        model = StreamModel({"": [
            [call("get_metric", {"metric": "tong_luong_mua"})],
            [call("ask_user", {"question": "Thành phố nào?"}, "ask")],
        ]})
        log: list[tuple[str, str]] = []
        result = run_tool_agent(
            "p", {}, toolkit().tools(), 5, model,
            on_tool=lambda name, args, output: log.append(("done", name)),
            on_tool_start=lambda name, args: log.append(("start", name)),
        )
        self.assertIsNotNone(result.pause)
        self.assertEqual(log, [("start", "get_metric"), ("done", "get_metric")])

    def test_resume_continues_round_numbers(self) -> None:
        pause = ToolAgentPause(
            tool_call_id="ask", tool="ask_user", payload={"question": "?"}, rounds=3,
            messages=[HumanMessage(content="{}"), AIMessage(content="", tool_calls=[
                {"name": "ask_user", "args": {"question": "?"}, "id": "ask"},
            ])],
        )
        recorder = Recorder()
        model = StreamModel({"": [[text("Huế.")]]})
        run_tool_agent(
            "p", {}, toolkit().tools(), 5, model, resume=ToolAgentResume(pause, "Huế"), on_text=recorder.stream(),
        )
        self.assertEqual(recorder.events, [("delta", 3, "Huế."), ("end", 3, False)])

    def test_tool_chunk_before_text_pushes_no_text(self) -> None:
        model = StreamModel({"": [[call("query_metric", QUERY), text("lời dẫn")], [text("xong")]]})
        recorder = Recorder()
        run_tool_agent("p", {}, toolkit().tools(), 5, model, on_text=recorder.stream())
        self.assertEqual(recorder.events[:1], [("end", 0, False)])
        self.assertEqual(recorder.events[1:], [("delta", 1, "xong"), ("end", 1, False)])

    def test_invalid_tool_call_ends_like_invoke(self) -> None:
        script = [text("Kết quả: "), call("query_metric", "[1,2]x"), text(" xong")]
        self.assertTrue(merged(script).invalid_tool_calls)
        recorder = Recorder()
        streamed = run_tool_agent(
            "p", {}, toolkit().tools(), 5, StreamModel({"": [list(script)]}), on_text=recorder.stream(),
        )
        invoked = run_tool_agent("p", {}, toolkit().tools(), 5, StreamModel({"": [list(script)]}))
        self.assertEqual(streamed.answer, invoked.answer)
        self.assertEqual(len(streamed.messages), len(invoked.messages))
        self.assertEqual(recorder.events, [("delta", 0, "Kết quả: "), ("delta", 0, " xong"), ("end", 0, False)])


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class DeltaBufferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.clock = FakeClock()
        self.buffer = DeltaBuffer(lambda event, data: self.events.append((event, data)), 2, False, clock=self.clock)

    def texts(self) -> list[str]:
        return [data["text"] for event, data in self.events if event == "answer_delta"]

    def test_first_piece_goes_out_then_pieces_are_grouped_by_size_and_time(self) -> None:
        self.buffer.delta(0, "Một")
        self.buffer.delta(0, " hai")
        self.assertEqual(self.texts(), ["Một"])
        self.buffer.delta(0, "x" * 30)
        self.assertEqual(self.texts(), ["Một", " hai" + "x" * 30])
        self.buffer.delta(0, "ba")
        self.clock.now = 0.06
        self.buffer.delta(0, " bốn")
        self.assertEqual(self.texts()[-1], "ba bốn")
        self.assertEqual(self.events[0][1], {"position": 2, "round": 0, "final": False, "text": "Một"})

    def test_round_change_flushes_first_and_end_flushes_before_reset(self) -> None:
        self.buffer.delta(0, "a")
        self.buffer.delta(0, "b")
        self.buffer.delta(1, "c")
        self.assertEqual([(data["round"], data["text"]) for _, data in self.events], [(0, "a"), (0, "b")])
        self.buffer.end(1, True)
        self.assertEqual(self.events[-2:], [
            ("answer_delta", {"position": 2, "round": 1, "final": False, "text": "c"}),
            ("answer_reset", {"position": 2, "round": 1}),
        ])
        self.buffer.end(2, False)
        self.assertEqual(len(self.events), 4)

    def test_synthesize_stream_has_no_position(self) -> None:
        stream = SynthesizeStream(lambda event, data: self.events.append((event, data)), clock=self.clock)
        stream.delta("Tổng ")
        stream.delta("hợp")
        stream.close()
        self.assertEqual([data for _, data in self.events], [
            {"position": None, "round": 0, "final": True, "text": "Tổng "},
            {"position": None, "round": 0, "final": True, "text": "hợp"},
        ])


class TextModel:
    def __init__(self, pieces: list[str], error: Exception | None = None) -> None:
        self.pieces = pieces
        self.error = error
        self.calls: list[tuple[str, list]] = []
        self.closed = False

    def invoke(self, messages):
        self.calls.append(("invoke", messages))
        if self.error is not None:
            raise self.error
        return AIMessage(content="".join(self.pieces))

    def stream(self, messages):
        self.calls.append(("stream", messages))
        if self.error is not None:
            raise self.error
        try:
            for piece in self.pieces:
                yield AIMessageChunk(content=piece)
        finally:
            self.closed = True


def llm_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "http://llm"))


class ChatTextTests(unittest.TestCase):
    def test_invoke_without_callback_and_stream_with_it(self) -> None:
        model = TextModel(["  Câu {một}", " và hai.  "])
        self.assertEqual(get_chat_text("hệ {x}", {"a": "{b}"}, model=model), "Câu {một} và hai.")
        kind, messages = model.calls[0]
        self.assertEqual(kind, "invoke")
        self.assertEqual(messages[0].content, "hệ {x}")
        self.assertEqual(json.loads(messages[1].content), {"a": "{b}"})
        pieces: list[str] = []
        self.assertEqual(get_chat_text("p", {}, pieces.append, model=model), "Câu {một} và hai.")
        self.assertEqual(model.calls[1][0], "stream")
        self.assertEqual(pieces, ["  Câu {một}", " và hai.  "])

    def test_errors_propagate(self) -> None:
        with self.assertRaises(APIConnectionError):
            get_chat_text("p", {}, model=TextModel([], llm_error()))
        model = TextModel(["a", "b"])

        def stop(piece: str) -> None:
            raise Text2SqlClientDisconnected()

        with self.assertRaises(Text2SqlClientDisconnected):
            get_chat_text("p", {}, stop, model=model)
        self.assertTrue(model.closed)


class GraphStreamingTests(unittest.TestCase):
    def run_graph(self, streaming: bool, synthesize) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        received: list = []

        def answer(preprocess, item, prior, pending=None, reply=None, emit=None):
            received.append(emit)
            if emit is not None:
                emit("tool", {"position": item.position})
            return QuestionAnswerOut(position=item.position, question=item.question, answer=f"đáp án {item.position}")

        run_chat_graph(ChatGraphContext(
            preprocess=lambda: make_preprocess([[], []]), answer_question=answer, synthesize=synthesize,
            streaming=streaming,
        ), "t", on_event=lambda event, data: events.append((event, data)))
        self.received = received
        return events

    def test_not_streaming_sends_no_custom_events_and_calls_old_synthesize(self) -> None:
        def synthesize(preprocess, answers):
            return "tổng hợp"

        events = self.run_graph(False, synthesize)
        self.assertEqual([event for event, _ in events], [
            "preprocess", "question_answered", "question_answered", "answer",
        ])
        self.assertEqual(self.received, [None, None])

    def test_streaming_split_announces_synthesis_then_streams_it(self) -> None:
        def synthesize(preprocess, answers, on_text=None):
            on_text("tổng ")
            on_text("hợp")
            return "tổng hợp"

        events = self.run_graph(True, synthesize)
        names = [event for event, _ in events]
        self.assertEqual(names[-4:], ["synthesize_started", "answer_delta", "answer_delta", "answer"])
        self.assertEqual(names.count("question_started"), 2)
        self.assertEqual("".join(data["text"] for event, data in events if event == "answer_delta"), "tổng hợp")
        self.assertTrue(all(data["position"] is None for event, data in events if event == "answer_delta"))


class AgentRunStreamTests(unittest.TestCase):
    def answer(self, depends_on: list[list[int]], emit) -> tuple[StreamModel, object]:
        model = StreamModel({"": [[call("query_metric", QUERY)], [text("Huế mưa 12,5 mm.")]]})
        run = AgentRun(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), TODAY, model)
        preprocess = make_preprocess(depends_on)
        return model, run.answer(preprocess, preprocess.questions[0], [], emit=emit)

    def test_final_flag_follows_split(self) -> None:
        for depends_on, final in (([[]], True), ([[], []], False)):
            events: list[tuple[str, dict]] = []
            self.answer(depends_on, lambda event, data, sink=events: sink.append((event, data)))
            names = [event for event, _ in events]
            self.assertEqual(names, ["tool_started", "tool", "answer_delta"])
            self.assertEqual(events[0][1], {"position": 1, "tool": "query_metric", "subject": "Tổng lượng mưa"})
            self.assertEqual(events[2][1]["final"], final)

    def test_without_emit_nothing_streams(self) -> None:
        model, result = self.answer([[]], None)
        self.assertEqual(result.answer, "Huế mưa 12,5 mm.")
        self.assertEqual((model.streamed, model.invoked), (0, 2))

    def test_tool_subject(self) -> None:
        catalog = make_catalog()
        cases = [
            ("get_metric", {"metric": "tong_luong_mua"}, "Tổng lượng mưa"),
            ("query_metric", {"metric": "khong_co"}, "khong_co"),
            ("get_table", {"table": "weather.daily"}, "Thời tiết ngày"),
            ("get_table", {"table": "khac"}, "khac"),
            ("get_expert_rule", {"rule": "Chỉ trạm chính"}, "Chỉ trạm chính"),
            ("get_column_values", {"table": "weather.daily", "column": "thanh_pho"}, "Thành phố"),
            ("get_column_values", {"table": "weather.daily", "column": "quan"}, "quan"),
            ("run_sql", {"sql": "SELECT 1", "purpose": "x" * 100}, "x" * 80),
            ("run_sql", {"sql": "SELECT 1"}, None),
            ("make_chart", {"result_id": "1-1", "chart": {}}, None),
        ]
        for tool, arguments, expected in cases:
            self.assertEqual(tool_subject(catalog, tool, arguments), expected, tool)


class RealAgent:
    def __init__(self, model: StreamModel) -> None:
        self.model = model

    def start(self, connection_id):
        return AgentRun(make_catalog(), QueryCache(runner=FakeRunner(), max_rows=200), TODAY, self.model)


def by_position(events: list[tuple[str, dict]], position: int) -> list[str]:
    return [
        event for event, data in events
        if event in ("question_started", "tool_started", "tool", "answer_delta", "answer_reset", "question_answered")
        and data.get("position") == position
    ]


class StreamRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, headers=use_service_key(self))

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def stream(self, service, **body) -> list[tuple[str, dict]]:
        app.dependency_overrides[get_chat_service_factory] = lambda: (lambda: nullcontext(service))
        payload = {"connection_id": str(CONNECTION_ID), "question": "câu hỏi", **body}
        response = self.client.post("/api/v1/text2sql/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        return read_events(response.text)

    def test_single_question_streams_final_text_and_resets_tool_round(self) -> None:
        model = StreamModel({SINGLE_QUESTION: [
            [text("Để trả lời, tôi xem chỉ số."), call("query_metric", QUERY)],
            [text("Huế mưa "), text("**12,5 mm**. ")],
        ]})
        service, *_ = stream_service(FakeCompletion(rewrite=SINGLE_REWRITE), RealAgent(model))
        events = self.stream(service)
        names = [event for event, _ in events]
        self.assertEqual(names[:6], [
            "preprocess", "question_started", "answer_delta", "answer_reset", "tool_started", "tool",
        ])
        self.assertEqual(names[-3:], ["question_answered", "answer", "done"])
        self.assertEqual(events[3][1], {"position": 1, "round": 0})
        self.assertEqual(events[4][1], {"position": 1, "tool": "query_metric", "subject": "Tổng lượng mưa"})
        self.assertEqual(events[5][1]["result_id"], "1-1")
        final = [data for event, data in events[6:] if event == "answer_delta"]
        self.assertTrue(final and all(data["final"] and data["round"] == 1 for data in final))
        answered = events[-3][1]["answer"]
        self.assertEqual("".join(data["text"] for data in final).strip(), answered)
        self.assertEqual(answered, "Huế mưa **12,5 mm**.")
        self.assertEqual(events[-1][1]["answer"], answered)

    def test_parallel_split_streams_drafts_per_position_then_synthesis(self) -> None:
        script = [[call("query_metric", QUERY)], [text("Huế mưa 12,5 mm.")]]
        model = StreamModel({FIRST: [list(item) for item in script], SECOND: [list(item) for item in script]})
        service, *_ = stream_service(FakeCompletion(rewrite=PARALLEL_REWRITE), RealAgent(model))
        service.text_completion = FakeText(pieces=["Tổng ", "hợp."])
        events = self.stream(service)
        for position in (1, 2):
            self.assertEqual(by_position(events, position), [
                "question_started", "tool_started", "tool", "answer_delta", "question_answered",
            ])
        drafts = [data for event, data in events if event == "answer_delta" and data["position"] is not None]
        self.assertTrue(all(not data["final"] for data in drafts))
        names = [event for event, _ in events]
        start = names.index("synthesize_started")
        self.assertGreater(start, max(index for index, name in enumerate(names) if name == "question_answered"))
        tail = events[start + 1:]
        self.assertEqual([event for event, _ in tail], ["answer_delta", "answer_delta", "answer", "done"])
        self.assertEqual([(data["position"], data["final"], data["text"]) for _, data in tail[:2]], [
            (None, True, "Tổng "), (None, True, "hợp."),
        ])
        self.assertTrue(service.text_completion.calls[0][2])

    def test_resume_after_clarification_streams_with_continued_rounds(self) -> None:
        model = StreamModel({
            FIRST: [[text("Huế mưa nhiều nhất.")]],
            SECOND: [
                [text("Tôi cần hỏi lại."), call("ask_user", {"question": "Thành phố nào?"}, "ask")],
                [text("Huế 20 °C.")],
            ],
        })
        service, _, _, checkpoints = stream_service(FakeCompletion(), RealAgent(model))
        events = self.stream(service)
        self.assertEqual(by_position(events, 2), ["question_started", "answer_delta", "answer_reset"])
        self.assertNotIn("tool_started", [event for event, _ in events])
        self.assertEqual([event for event, _ in events][-3:], ["question_waiting", "clarification", "done"])
        resume_id = events[-1][1]["resume_id"]
        resumed = self.stream(service, question="Huế", resume_id=resume_id)
        self.assertEqual([event for event, _ in resumed], [
            "question_started", "answer_delta", "question_answered", "synthesize_started", "answer_delta", "answer",
            "done",
        ])
        self.assertTrue(resumed[0][1]["resumed"])
        self.assertEqual(resumed[1][1], {"position": 2, "round": 1, "final": False, "text": "Huế 20 °C."})
        self.assertEqual(resumed[-1][1]["answer"], "Huế mưa nhiều nhất. / Huế 20 °C.")
        self.assertEqual(checkpoints.rows, {})

    def test_json_route_does_not_stream(self) -> None:
        script = [[call("query_metric", QUERY)], [text("Huế mưa 12,5 mm.")]]
        model = StreamModel({FIRST: [list(item) for item in script], SECOND: [list(item) for item in script]})
        service, *_ = stream_service(FakeCompletion(rewrite=PARALLEL_REWRITE), RealAgent(model))
        app.dependency_overrides[get_database] = lambda: SimpleNamespace(get=lambda model, key: object())
        app.dependency_overrides[get_chat_service] = lambda: service
        response = self.client.post("/api/v1/text2sql/chat", json={
            "connection_id": str(CONNECTION_ID), "question": "câu hỏi",
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["answer"], "Huế mưa 12,5 mm. / Huế mưa 12,5 mm.")
        self.assertEqual((model.streamed, model.invoked), (0, 4))
        self.assertFalse(service.text_completion.calls[0][2])
        self.assertEqual(body["answers"][0]["steps"][0]["result_id"], "1-1")

    def test_json_route_synthesis_llm_error_is_503(self) -> None:
        service, *_ = stream_service(FakeCompletion())
        service.text_completion = FakeText(error=llm_error())
        app.dependency_overrides[get_database] = lambda: SimpleNamespace(get=lambda model, key: object())
        app.dependency_overrides[get_chat_service] = lambda: service
        response = self.client.post("/api/v1/text2sql/chat", json={
            "connection_id": str(CONNECTION_ID), "question": "câu hỏi",
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], Text2SqlAgentUnavailable.message)


class StreamStopTests(unittest.TestCase):
    def test_stop_while_agent_streams_marks_turn_disconnected(self) -> None:
        stop = threading.Event()
        model = StreamModel({SINGLE_QUESTION: [[text("Huế "), text("mưa"), text(" nhiều.")]]}, after_chunk=stop.set)
        service, _, conversations, _ = stream_service(FakeCompletion(rewrite=SINGLE_REWRITE), RealAgent(model))
        prepared = service.prepare(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        events: list[tuple[str, dict]] = []
        with self.assertRaises(Text2SqlClientDisconnected):
            service.execute(prepared, lambda event, data: events.append((event, data)), should_stop=stop.is_set)
        self.assertEqual(model.closed, 1)
        self.assertEqual(conversations.completed["status"], "error")
        self.assertEqual(conversations.completed["error_code"], "client_disconnected")

    def test_stop_while_synthesis_streams_is_not_agent_unavailable(self) -> None:
        stop = threading.Event()
        service, _, conversations, _ = stream_service(FakeCompletion())
        text_model = TextModel(["Tổng ", "hợp ", "dở."])

        def first_piece(system_prompt, params, on_text=None):
            def watched(piece: str) -> None:
                on_text(piece)
                stop.set()

            return get_chat_text(system_prompt, params, watched if on_text else None, model=text_model)

        service.text_completion = first_piece
        prepared = service.prepare(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        events: list[tuple[str, dict]] = []
        with self.assertRaises(Text2SqlClientDisconnected):
            service.execute(prepared, lambda event, data: events.append((event, data)), should_stop=stop.is_set)
        self.assertTrue(text_model.closed)
        self.assertEqual([event for event, _ in events][-2:], ["synthesize_started", "answer_delta"])
        self.assertEqual(conversations.completed["status"], "error")
        self.assertEqual(conversations.completed["error_code"], "client_disconnected")
        self.assertIsNone(conversations.completed.get("answer"))


if __name__ == "__main__":
    unittest.main()
