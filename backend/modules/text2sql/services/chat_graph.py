from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt

from backend.agent_package.tool_agent import ToolAgentPause

from ..schemas import (
    AgentStepOut,
    PreprocessedQuestionOut,
    PreprocessOut,
    QuestionAnswerOut,
)
from ..utils.exceptions import Text2SqlClientDisconnected
from .answer_stream import SynthesizeStream
from .chat_events import QUESTION_STARTED, SYNTHESIZE_STARTED, Emit, update_events

RECURSION_LIMIT = 100
STREAM_MODES = ["updates", "custom"]


@dataclass(frozen=True)
class PendingQuestion:
    position: int
    question: str
    options: list[str]
    pause: ToolAgentPause
    steps: list[AgentStepOut] = field(default_factory=list)


AnswerQuestion = Callable[
    [
        PreprocessOut, PreprocessedQuestionOut, Sequence[QuestionAnswerOut], PendingQuestion | None, str | None,
        Emit | None,
    ],
    QuestionAnswerOut | PendingQuestion,
]
TextCallback = Callable[[str], None]


class Synthesize(Protocol):
    def __call__(
        self, preprocess: PreprocessOut, answers: list[QuestionAnswerOut], on_text: TextCallback | None = None,
    ) -> str: ...


SCHEMA_MODULE = "backend.modules.text2sql.schemas.schema_text2sql"
CHECKPOINT_TYPES = (
    *((SCHEMA_MODULE, name) for name in (
        "PreprocessOut", "PreprocessedQuestionOut", "QuestionKnowledgeOut", "CandidateOut", "KnowledgeHitOut",
        "QuestionAnswerOut", "AgentStepOut",
    )),
    (__name__, "PendingQuestion"),
    ("backend.agent_package.tool_agent", "ToolAgentPause"),
)


def merge_answers(
    current: dict[int, QuestionAnswerOut], update: dict[int, QuestionAnswerOut]
) -> dict[int, QuestionAnswerOut]:
    return {**current, **update}


def merge_present(current: dict[int, Any], update: dict[int, Any]) -> dict[int, Any]:
    return {key: value for key, value in {**current, **update}.items() if value is not None}


class ChatState(TypedDict, total=False):
    preprocess: PreprocessOut
    answers: Annotated[dict[int, QuestionAnswerOut], merge_answers]
    pending: Annotated[dict[int, PendingQuestion], merge_present]
    replies: Annotated[dict[int, str], merge_present]
    answer: str


class QuestionTask(TypedDict, total=False):
    preprocess: PreprocessOut
    item: PreprocessedQuestionOut
    prior: list[QuestionAnswerOut]
    pending: PendingQuestion
    reply: str


def never() -> bool:
    return False


@dataclass(frozen=True)
class ChatGraphContext:
    preprocess: Callable[[], PreprocessOut]
    answer_question: AnswerQuestion
    synthesize: Synthesize
    should_stop: Callable[[], bool] = never
    streaming: bool = False


@dataclass(frozen=True)
class Clarification:
    question: str
    options: list[str]
    positions: list[int]


@dataclass(frozen=True)
class ChatRun:
    state: ChatState
    clarification: Clarification | None = None
    snapshot: bytes | None = None


def clarification_request(pending: dict[int, PendingQuestion]) -> dict[str, Any]:
    items = [pending[position] for position in sorted(pending)]
    if len(items) == 1:
        return {"question": items[0].question, "options": items[0].options, "positions": [items[0].position]}
    return {
        "question": "\n".join(f"{index}. {item.question}" for index, item in enumerate(items, start=1)),
        "options": [], "positions": [item.position for item in items],
    }


def _preprocess(state: ChatState, runtime: Runtime[ChatGraphContext]) -> dict[str, Any]:
    return {"preprocess": runtime.context.preprocess()}


def _dispatch(state: ChatState) -> dict[str, Any]:
    return {}


def _ready_questions(state: ChatState) -> list[Send] | str:
    done = state.get("answers", {})
    pending = state.get("pending", {})
    replies = state.get("replies", {})
    preprocess = state["preprocess"]
    sends = []
    for item in preprocess.questions:
        if item.position in done or not all(position in done for position in item.depends_on):
            continue
        task: QuestionTask = {
            "preprocess": preprocess, "item": item, "prior": [done[position] for position in item.depends_on],
        }
        if item.position not in pending:
            sends.append(Send("answer_question", task))
        elif item.position in replies:
            sends.append(Send("answer_question", {
                **task, "pending": pending[item.position], "reply": replies[item.position],
            }))
    if sends:
        return sends
    return "clarify" if pending else "synthesize"


def _emitter(runtime: Runtime[ChatGraphContext]) -> Emit:
    writer = get_stream_writer()

    def emit(event: str, data: dict[str, Any]) -> None:
        if runtime.context.should_stop():
            raise Text2SqlClientDisconnected()
        writer({"event": event, "data": data})

    return emit


def _answer_question(task: QuestionTask, runtime: Runtime[ChatGraphContext]) -> dict[str, Any]:
    item = task["item"]
    pending = task.get("pending")
    emit = _emitter(runtime) if runtime.context.streaming else None
    if emit is not None:
        emit(QUESTION_STARTED, {"position": item.position, "question": item.question, "resumed": pending is not None})
    result = runtime.context.answer_question(
        task["preprocess"], item, task["prior"], pending, task.get("reply"), emit,
    )
    update: dict[str, Any] = {"replies": {item.position: None}} if pending is not None else {}
    if isinstance(result, PendingQuestion):
        return {**update, "pending": {item.position: result}}
    return {**update, "pending": {item.position: None}, "answers": {item.position: result}}


def _clarify(state: ChatState) -> dict[str, Any]:
    pending = state["pending"]
    reply = interrupt(clarification_request(pending))
    return {"replies": {position: str(reply) for position in pending}}


def _synthesize(state: ChatState, runtime: Runtime[ChatGraphContext]) -> dict[str, Any]:
    answers = [state["answers"][position] for position in sorted(state.get("answers", {}))]
    if len(answers) == 1 and not state["preprocess"].is_split:
        return {"answer": answers[0].answer}
    context = runtime.context
    if not context.streaming:
        return {"answer": context.synthesize(state["preprocess"], answers)}
    emit = _emitter(runtime)
    emit(SYNTHESIZE_STARTED, {})
    stream = SynthesizeStream(emit)
    answer = context.synthesize(state["preprocess"], answers, on_text=stream.delta)
    stream.close()
    return {"answer": answer}


def _build_graph() -> StateGraph:
    graph = StateGraph(ChatState, context_schema=ChatGraphContext)
    graph.add_node("preprocess", _preprocess)
    graph.add_node("dispatch", _dispatch)
    graph.add_node("answer_question", _answer_question)
    graph.add_node("clarify", _clarify)
    graph.add_node("synthesize", _synthesize)
    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "dispatch")
    graph.add_conditional_edges("dispatch", _ready_questions, ["answer_question", "clarify", "synthesize"])
    graph.add_edge("answer_question", "dispatch")
    graph.add_edge("clarify", "dispatch")
    graph.add_edge("synthesize", END)
    return graph


chat_graph_builder = _build_graph()


class SnapshotSaver(InMemorySaver):
    def __init__(self) -> None:
        super().__init__(serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES))

    def export_thread(self, thread_id: str) -> bytes:
        storage = [
            [namespace, checkpoint_id, list(checkpoint), list(metadata), parent]
            for namespace, items in self.storage.get(thread_id, {}).items()
            for checkpoint_id, (checkpoint, metadata, parent) in items.items()
        ]
        writes = [
            [namespace, checkpoint_id, task_id, index, task, channel, list(value), path]
            for (thread, namespace, checkpoint_id), items in self.writes.items() if thread == thread_id
            for (task_id, index), (task, channel, value, path) in items.items()
        ]
        blobs = [
            [namespace, channel, version, list(value)]
            for (thread, namespace, channel, version), value in self.blobs.items() if thread == thread_id
        ]
        kind, data = self.serde.dumps_typed({"storage": storage, "writes": writes, "blobs": blobs})
        if kind != "msgpack":
            raise TypeError(f"Không xuất được checkpoint dạng {kind}.")
        return data

    def import_thread(self, thread_id: str, snapshot: bytes) -> None:
        data = self.serde.loads_typed(("msgpack", snapshot))
        for namespace, checkpoint_id, checkpoint, metadata, parent in data["storage"]:
            self.storage[thread_id][namespace][checkpoint_id] = (tuple(checkpoint), tuple(metadata), parent)
        for namespace, checkpoint_id, task_id, index, task, channel, value, path in data["writes"]:
            self.writes[(thread_id, namespace, checkpoint_id)][(task_id, index)] = (task, channel, tuple(value), path)
        for namespace, channel, version, value in data["blobs"]:
            self.blobs[(thread_id, namespace, channel, version)] = tuple(value)


def run_chat_graph(
    context: ChatGraphContext, thread_id: str, reply: str | None = None, snapshot: bytes | None = None,
    on_event: Emit | None = None,
) -> ChatRun:
    saver = SnapshotSaver()
    if snapshot is not None:
        saver.import_thread(thread_id, snapshot)
    graph = chat_graph_builder.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    start: Any = Command(resume=reply) if snapshot is not None else {"answers": {}}
    for mode, chunk in graph.stream(start, config, context=context, stream_mode=STREAM_MODES, durability="exit"):
        if on_event is None:
            continue
        events = [(chunk["event"], chunk["data"])] if mode == "custom" else [
            event for node, update in chunk.items() for event in update_events(node, update)
        ]
        for event, data in events:
            on_event(event, data)
    snapshot_state = graph.get_state(config)
    state: ChatState = snapshot_state.values
    if not snapshot_state.interrupts:
        return ChatRun(state=state)
    request = snapshot_state.interrupts[0].value
    clarification = Clarification(request["question"], list(request["options"]), list(request["positions"]))
    return ChatRun(state=state, clarification=clarification, snapshot=saver.export_thread(thread_id))
