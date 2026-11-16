import json
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.utils.json import parse_partial_json
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from backend.core.setting import config

from .errors import AgentUnavailableError

Output = TypeVar("Output", bound=BaseModel)
REASONING_FIELD = "analysis"
INVALID_OUTPUT = "Mô hình không trả kết quả đúng cấu trúc."
HIGH_SURROGATES = ("\ud800", "\udbff")


@dataclass(frozen=True)
class ReasoningDelta:
    index: int
    text: str


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.openrouter_model,
        temperature=0.0,
        max_tokens=4096,
        timeout=60,
        max_retries=2,
        api_key=config.require_openrouter_api_key(),
        base_url=config.openrouter_base_url,
    )


def structured_model(schema: type[Output]) -> Any:
    return get_chat_model().with_structured_output(schema, method="function_calling")


def tool_model(schema: type[Output]) -> Any:
    name = convert_to_openai_tool(schema)["function"]["name"]
    return get_chat_model().bind_tools([schema], tool_choice=name, parallel_tool_calls=False)


def build_messages(prompt: str, context: dict[str, Any]) -> list[SystemMessage | HumanMessage]:
    return [SystemMessage(content=prompt), HumanMessage(content=json.dumps(context, ensure_ascii=False, indent=2))]


def invoke_structured(schema: type[Output], prompt: str, context: dict[str, Any]) -> Output:
    try:
        result = structured_model(schema).invoke(build_messages(prompt, context))
    except Exception as error:
        raise AgentUnavailableError() from error
    if result is None:
        raise AgentUnavailableError(INVALID_OUTPUT)
    try:
        return schema.model_validate(result)
    except ValidationError as error:
        raise AgentUnavailableError(INVALID_OUTPUT) from error


def partial_reasoning(arguments: str) -> list[str]:
    try:
        parsed = parse_partial_json(arguments)
    except ValueError:
        return []
    items = parsed.get(REASONING_FIELD) if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    texts: list[str] = []
    for item in items:
        if not isinstance(item, str):
            break
        texts.append(item)
    return texts


def _stable(text: str) -> str:
    low, high = HIGH_SURROGATES
    return text[:-1] if text and low <= text[-1] <= high else text


def reasoning_deltas(emitted: list[str], items: list[str]) -> list[ReasoningDelta]:
    deltas: list[ReasoningDelta] = []
    for index, raw in enumerate(items):
        text = _stable(raw)
        if index == len(emitted):
            emitted.append("")
        previous = emitted[index]
        if len(text) > len(previous) and text.startswith(previous):
            deltas.append(ReasoningDelta(index, text[len(previous):]))
            emitted[index] = text
    return deltas


def _first_arguments(calls: dict[int, list[str]]) -> str:
    return "".join(calls[min(calls)]) if calls else ""


def _collect(chunk: Any, calls: dict[int, list[str]]) -> bool:
    changed = False
    for piece in getattr(chunk, "tool_call_chunks", None) or []:
        arguments = piece.get("args")
        if arguments:
            calls.setdefault(piece.get("index") or 0, []).append(arguments)
            changed = True
    return changed


def stream_structured(
    schema: type[Output], prompt: str, context: dict[str, Any],
) -> Generator[ReasoningDelta, None, Output]:
    calls: dict[int, list[str]] = {}
    emitted: list[str] = []
    stream: Any = None
    try:
        try:
            stream = iter(tool_model(schema).stream(build_messages(prompt, context)))
        except Exception as error:
            raise AgentUnavailableError() from error
        while True:
            try:
                chunk = next(stream)
            except StopIteration:
                break
            except Exception as error:
                raise AgentUnavailableError() from error
            if _collect(chunk, calls):
                yield from reasoning_deltas(emitted, partial_reasoning(_first_arguments(calls)))
    finally:
        closer = getattr(stream, "close", None)
        if closer is not None:
            closer()
    try:
        result = schema.model_validate(json.loads(_first_arguments(calls), strict=False))
    except (ValueError, ValidationError) as error:
        raise AgentUnavailableError(INVALID_OUTPUT) from error
    reasoning = getattr(result, REASONING_FIELD, None)
    if isinstance(reasoning, list):
        yield from reasoning_deltas(emitted, [item for item in reasoning if isinstance(item, str)])
    return result


def chunk_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block if isinstance(block, str) else block.get("text", "") for block in content
                 if isinstance(block, str) or (isinstance(block, dict) and block.get("type", "text") == "text")]
        return "".join(part for part in parts if isinstance(part, str))
    return ""


def stream_text(prompt: str, context: dict[str, Any]) -> Iterator[str]:
    try:
        for chunk in get_chat_model().stream(build_messages(prompt, context)):
            text = chunk_text(chunk.content)
            if text:
                yield text
    except Exception as error:
        raise AgentUnavailableError() from error
