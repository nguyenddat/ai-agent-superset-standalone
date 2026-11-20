import json
import logging
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from pydantic import ValidationError
from pydantic_core import to_jsonable_python

from .get_chat_models import build_messages, get_chat_model

logger = logging.getLogger(__name__)

EXHAUSTED_NOTICE = (
    "Đã hết lượt gọi công cụ. Trả lời ngay bằng các kết quả đã có; nói rõ phần nào chưa trả lời được và vì sao."
)
REPEATED_FAILURE = "Lời gọi này đã lỗi trước đó với đúng các tham số này. Hãy sửa tham số hoặc đổi cách làm."
SECOND_PAUSE = "Mỗi lượt chỉ dừng chờ người dùng một lần; lời gọi này bị bỏ qua."


class ToolError(Exception):
    pass


class AgentPause(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("agent paused")
        self.payload = payload


@dataclass(frozen=True)
class ToolAgentPause:
    tool_call_id: str
    tool: str
    payload: dict[str, Any]
    messages: list[AnyMessage]
    rounds: int


@dataclass(frozen=True)
class ToolAgentResume:
    pause: ToolAgentPause
    reply: Any


ToolCallback = Callable[[str, dict[str, Any], Any], None]
ToolStartCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class TextStream:
    delta: Callable[[int, str], None]
    end: Callable[[int, bool], None]


class ToolAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    rounds: int
    exhausted: bool
    pause: dict[str, Any] | None


@dataclass
class ToolAgentContext:
    tools: Sequence[BaseTool]
    max_steps: int
    model: BaseChatModel | None = None
    failed_calls: set[str] = field(default_factory=set)
    on_tool: ToolCallback | None = None
    on_text: TextStream | None = None
    on_tool_start: ToolStartCallback | None = None


@dataclass(frozen=True)
class ToolAgentResult:
    answer: str
    exhausted: bool
    messages: list[AnyMessage]
    pause: ToolAgentPause | None = None


def _stream_round(
    runnable: Any, messages: list[AnyMessage], on_text: TextStream, round_: int, can_call_tools: bool = True,
) -> AIMessage:
    acc: AIMessageChunk | None = None
    pushed = 0
    with closing(runnable.stream(messages)) as chunks:
        for chunk in chunks:
            acc = chunk if acc is None else acc + chunk
            if acc.tool_call_chunks:
                continue
            text = acc.text
            if len(text) > pushed:
                on_text.delta(round_, text[pushed:])
                pushed = len(text)
    message = message_chunk_to_message(acc) if acc is not None else AIMessage(content="")
    ends = not (can_call_tools and message.tool_calls)
    discard = not ends and pushed > 0
    if ends and len(message.text) > pushed:
        on_text.delta(round_, message.text[pushed:])
    on_text.end(round_, discard)
    return message


def _model_reply(
    runnable: Any, messages: list[AnyMessage], context: ToolAgentContext, round_: int, can_call_tools: bool = True,
) -> AIMessage:
    if context.on_text is None:
        return runnable.invoke(messages)
    return _stream_round(runnable, messages, context.on_text, round_, can_call_tools)


def _call_model(state: ToolAgentState, runtime: Runtime[ToolAgentContext]) -> dict[str, Any]:
    context = runtime.context
    model = context.model or get_chat_model()
    round_ = state["rounds"]
    if round_ >= context.max_steps:
        notice = HumanMessage(content=EXHAUSTED_NOTICE)
        reply = _model_reply(model, [*state["messages"], notice], context, round_, can_call_tools=False)
        return {"messages": [notice, reply], "exhausted": True}
    return {"messages": [_model_reply(model.bind_tools(list(context.tools)), state["messages"], context, round_)]}


def _validation_message(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}" for item in error.errors()
    )


def _run_tool(tools: dict[str, BaseTool], name: str, arguments: dict[str, Any], failed_calls: set[str]) -> Any:
    key = json.dumps([name, arguments], ensure_ascii=False, sort_keys=True, default=str)
    if key in failed_calls:
        return {"error": REPEATED_FAILURE}
    tool = tools.get(name)
    if tool is None:
        output: Any = {"error": f"Không có công cụ '{name}'. Các công cụ hợp lệ: {', '.join(sorted(tools))}."}
    else:
        try:
            return tool.invoke(arguments)
        except ToolError as error:
            output = {"error": str(error)}
        except ValidationError as error:
            output = {"error": f"Tham số không hợp lệ: {_validation_message(error)}"}
    logger.info("Tool '%s' lỗi: %s", name, output["error"])
    failed_calls.add(key)
    return output


def _call_tools(state: ToolAgentState, runtime: Runtime[ToolAgentContext]) -> dict[str, Any]:
    tools = {tool.name: tool for tool in runtime.context.tools}
    last = state["messages"][-1]
    messages = []
    pause = None
    on_tool_start = runtime.context.on_tool_start
    for call in last.tool_calls:
        if on_tool_start is not None and call["name"] != "ask_user":
            on_tool_start(call["name"], call["args"])
        try:
            output = _run_tool(tools, call["name"], call["args"], runtime.context.failed_calls)
        except AgentPause as signal:
            if pause is None:
                pause = {"tool_call_id": call["id"], "tool": call["name"], "payload": signal.payload}
                continue
            output = {"error": SECOND_PAUSE}
        if runtime.context.on_tool is not None:
            runtime.context.on_tool(call["name"], call["args"], output)
        messages.append(ToolMessage(
            content=json.dumps(output, ensure_ascii=False, default=to_jsonable_python),
            tool_call_id=call["id"], name=call["name"],
            status="error" if isinstance(output, dict) and "error" in output else "success",
        ))
    return {"messages": messages, "rounds": state["rounds"] + 1, "pause": pause}


def _next_step(state: ToolAgentState) -> str:
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls and not state["exhausted"] else END


def _after_tools(state: ToolAgentState) -> str:
    return END if state.get("pause") else "agent"


def _build_graph() -> Any:
    graph = StateGraph(ToolAgentState, context_schema=ToolAgentContext)
    graph.add_node("agent", _call_model)
    graph.add_node("tools", _call_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _next_step, ["tools", END])
    graph.add_conditional_edges("tools", _after_tools, ["agent", END])
    return graph.compile()


tool_agent_graph = _build_graph()


def run_tool_agent(
    system_prompt: str, context: dict[str, Any], tools: Sequence[BaseTool], max_steps: int,
    model: BaseChatModel | None = None, resume: ToolAgentResume | None = None, on_tool: ToolCallback | None = None,
    on_text: TextStream | None = None, on_tool_start: ToolStartCallback | None = None,
) -> ToolAgentResult:
    messages, rounds = build_messages(system_prompt, context), 0
    if resume is not None:
        pause = resume.pause
        reply = ToolMessage(
            content=json.dumps({"user_reply": resume.reply}, ensure_ascii=False, default=to_jsonable_python),
            tool_call_id=pause.tool_call_id, name=pause.tool,
        )
        messages, rounds = [*pause.messages, reply], pause.rounds
    state = tool_agent_graph.invoke(
        {"messages": messages, "rounds": rounds, "exhausted": False, "pause": None},
        context=ToolAgentContext(
            tools=tools, max_steps=max_steps, model=model, on_tool=on_tool, on_text=on_text,
            on_tool_start=on_tool_start,
        ),
        config={"recursion_limit": 2 * max_steps + 5},
    )
    if state.get("pause"):
        found = state["pause"]
        return ToolAgentResult(
            answer="", exhausted=False, messages=state["messages"],
            pause=ToolAgentPause(
                tool_call_id=found["tool_call_id"], tool=found["tool"], payload=found["payload"],
                messages=state["messages"], rounds=state["rounds"],
            ),
        )
    last = state["messages"][-1]
    return ToolAgentResult(answer=last.text.strip(), exhausted=state["exhausted"], messages=state["messages"])
