import json
import random
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk

from backend.agent_package import get_chat_models
from backend.agent_package.agents.dataset_plan_agent import DatasetPlanAgent, DatasetPlanDraft
from backend.agent_package.agents.query_plan_agent import PlanDraft, QueryPlanAgent
from backend.agent_package.agents.question_rewrite_agent import QuestionRewriteAgent, RewriteDraft
from backend.agent_package.errors import AgentUnavailableError
from backend.agent_package.get_chat_models import ReasoningDelta, stream_structured

ANALYSIS = [
    "B1. Câu hỏi nói \"doanh thu\" theo miền Bắc\\Nam",
    "B2. Dòng mới\nvà tab\tđi kèm; ký tự đặc biệt: á, ố, ữ, đ, 😀,  ",
    "",
    "B4. Kết luận: giữ nguyên câu hỏi",
]
DRAFT = {"analysis": ANALYSIS, "rewritten_question": "Doanh thu theo miền?", "changes": ["không đổi"]}


def pieces(text: str, cuts: list[int]) -> list[str]:
    bounds = [0, *sorted(set(cuts)), len(text)]
    return [text[start:end] for start, end in zip(bounds, bounds[1:], strict=False) if end > start]


class FakeToolModel:
    def __init__(self, parts=(), error_after: int | None = None, content_only: bool = False,
                 bind_error: Exception | None = None):
        self.parts = list(parts)
        self.error_after = error_after
        self.content_only = content_only
        self.bind_error = bind_error
        self.bound = None
        self.seen = None
        self.closed = False
        self.yielded = 0

    def bind_tools(self, tools, **kwargs):
        if self.bind_error is not None:
            raise self.bind_error
        self.bound = (tools, kwargs)
        return self

    def stream(self, messages):
        self.seen = messages
        try:
            yield AIMessageChunk(content="", tool_call_chunks=[] if self.content_only else [
                tool_call_chunk(name="RewriteDraft", args="", id="call_1", index=0),
            ])
            for position, part in enumerate(self.parts):
                if self.error_after == position:
                    raise RuntimeError("mất kết nối")
                self.yielded += 1
                if self.content_only:
                    yield AIMessageChunk(content=part)
                else:
                    yield AIMessageChunk(content="", tool_call_chunks=[
                        tool_call_chunk(name=None, args=part, id=None, index=0),
                    ])
        finally:
            self.closed = True


def drain(generator, deltas: list[ReasoningDelta]):
    while True:
        try:
            deltas.append(next(generator))
        except StopIteration as finished:
            return finished.value


def joined(deltas: list[ReasoningDelta]) -> list[str]:
    items: dict[int, str] = {}
    for delta in deltas:
        items[delta.index] = items.get(delta.index, "") + delta.text
    return [items[index] for index in sorted(items)]


class StreamStructuredTests(unittest.TestCase):
    def run_stream(self, model: FakeToolModel, deltas: list[ReasoningDelta] | None = None, schema=RewriteDraft):
        collected = [] if deltas is None else deltas
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            return drain(stream_structured(schema, "PROMPT", {"question": "Doanh thu?"}), collected), collected

    def assert_streamed(self, deltas: list[ReasoningDelta], expected: list[str]) -> None:
        items: dict[int, str] = {}
        for delta in deltas:
            self.assertTrue(delta.text)
            items[delta.index] = items.get(delta.index, "") + delta.text
        for index, text in enumerate(expected):
            self.assertEqual(items.get(index, ""), text, index)
        self.assertEqual([delta.index for delta in deltas], sorted(delta.index for delta in deltas))

    def test_deltas_rebuild_every_item_verbatim_for_any_cut(self) -> None:
        generator = random.Random(7)
        for ensure_ascii in (False, True):
            text = json.dumps(DRAFT, ensure_ascii=ensure_ascii)
            layouts = [list(range(1, len(text))), [len(text) // 2]]
            layouts += [generator.sample(range(1, len(text)), generator.randint(1, 25)) for _ in range(40)]
            for cuts in layouts:
                with self.subTest(ensure_ascii=ensure_ascii, cuts=cuts[:8]):
                    model = FakeToolModel(pieces(text, cuts))
                    draft, deltas = self.run_stream(model)
                    self.assertEqual(draft, RewriteDraft.model_validate(DRAFT))
                    self.assert_streamed(deltas, ANALYSIS)
                    self.assertTrue(model.closed)

    def test_reasoning_is_streamed_before_the_rest_of_the_output_arrives(self) -> None:
        text = json.dumps(DRAFT, ensure_ascii=False)
        model = FakeToolModel(pieces(text, list(range(1, len(text)))))
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            stream = stream_structured(RewriteDraft, "PROMPT", {})
            first = next(stream)
        self.assertEqual(first.index, 0)
        self.assertLess(model.yielded, len(text) // 2)

    def test_a_provider_that_sends_the_arguments_at_once_gives_reasoning_at_the_end(self) -> None:
        model = FakeToolModel([json.dumps(DRAFT, ensure_ascii=False)])
        draft, deltas = self.run_stream(model)
        self.assertEqual(draft.rewritten_question, "Doanh thu theo miền?")
        self.assertEqual(deltas, [ReasoningDelta(0, ANALYSIS[0]), ReasoningDelta(1, ANALYSIS[1]),
                                  ReasoningDelta(3, ANALYSIS[3])])

    def test_it_binds_the_schema_as_the_forced_tool_and_sends_prompt_and_context(self) -> None:
        model = FakeToolModel([json.dumps(DRAFT)])
        self.run_stream(model)
        tools, options = model.bound
        self.assertEqual(tools, [RewriteDraft])
        self.assertEqual(options, {"tool_choice": "RewriteDraft", "parallel_tool_calls": False})
        self.assertEqual(model.seen[0].content, "PROMPT")
        self.assertIn("Doanh thu?", model.seen[1].content)

    def test_broken_or_incomplete_final_json_is_agent_unavailable(self) -> None:
        text = json.dumps(DRAFT, ensure_ascii=False)
        invalid = json.dumps({"analysis": ["B1. thiếu trường"]}, ensure_ascii=False)
        for parts in ([text[:-5]], [text[:40], text[40:-1] + "]"], [invalid], []):
            with self.subTest(parts=str(parts)[:50]):
                deltas: list[ReasoningDelta] = []
                with self.assertRaises(AgentUnavailableError):
                    self.run_stream(FakeToolModel(parts), deltas)
        deltas = []
        with self.assertRaises(AgentUnavailableError):
            self.run_stream(FakeToolModel([text[:-5]]), deltas)
        self.assertEqual(joined(deltas)[:2], ANALYSIS[:2])

    def test_an_error_in_the_middle_of_the_stream_is_agent_unavailable(self) -> None:
        text = json.dumps(DRAFT, ensure_ascii=False)
        model = FakeToolModel(pieces(text, list(range(1, len(text)))), error_after=60)
        deltas: list[ReasoningDelta] = []
        with self.assertRaises(AgentUnavailableError) as raised:
            self.run_stream(model, deltas)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertTrue(deltas)
        self.assertTrue(ANALYSIS[0].startswith(joined(deltas)[0]))
        self.assertTrue(model.closed)

    def test_a_reply_without_a_tool_call_or_a_failing_setup_is_agent_unavailable(self) -> None:
        for model in (FakeToolModel(["Xin chào"], content_only=True), FakeToolModel(bind_error=RuntimeError("x"))):
            with self.subTest(model=model.content_only):
                with self.assertRaises(AgentUnavailableError):
                    self.run_stream(model)

    def test_closing_the_generator_early_closes_the_model_stream(self) -> None:
        text = json.dumps(DRAFT, ensure_ascii=False)
        model = FakeToolModel(pieces(text, list(range(1, len(text)))))
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            stream = stream_structured(RewriteDraft, "PROMPT", {})
            next(stream)
            stream.close()
        self.assertTrue(model.closed)


class AgentStreamTests(unittest.TestCase):
    def test_each_structured_agent_streams_reasoning_then_returns_its_draft(self) -> None:
        cases = [
            (QuestionRewriteAgent(), RewriteDraft, DRAFT),
            (QueryPlanAgent(), PlanDraft, {"analysis": ["B1. Không có metric"], "status": "no_metric", "reason": "x"}),
            (DatasetPlanAgent(), DatasetPlanDraft, {"analysis": ["B1. Gốc là nhân sự"], "status": "cannot_answer"}),
        ]
        for agent, schema, payload in cases:
            with self.subTest(agent=type(agent).__name__):
                text = json.dumps(payload, ensure_ascii=False)
                model = FakeToolModel(pieces(text, [5, 17, 30]))
                deltas: list[ReasoningDelta] = []
                with patch.object(get_chat_models, "get_chat_model", lambda model=model: model):
                    draft = drain(agent.stream({"question": "q"}), deltas)
                self.assertIsInstance(draft, schema)
                self.assertEqual(joined(deltas), [item for item in payload["analysis"] if item])
                self.assertEqual(model.bound[1]["tool_choice"], schema.__name__)


if __name__ == "__main__":
    unittest.main()
