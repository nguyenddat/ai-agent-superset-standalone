import json
from dataclasses import dataclass, field
from typing import Any, Literal

StepName = Literal[
    "rewrite", "metric_search", "metric_query", "field_search", "dataset_plan", "join_plan", "dataset_query",
    "analysis",
]
StepStatus = Literal["started", "done", "skipped"]
EventName = Literal["turn", "step", "reasoning", "data", "token", "done", "error"]
ReasoningSource = Literal["model", "server"]


@dataclass(frozen=True)
class ChatEvent:
    event: EventName
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"), default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"


def turn(conversation_id: str, turn_id: str) -> ChatEvent:
    return ChatEvent("turn", {"conversation_id": conversation_id, "turn_id": turn_id})


def step(name: StepName, status: StepStatus, detail: dict[str, Any] | None = None) -> ChatEvent:
    return ChatEvent("step", {"step": name, "status": status, "detail": detail or {}})


def reasoning(name: StepName, source: ReasoningSource, index: int, delta: str) -> ChatEvent:
    return ChatEvent("reasoning", {"step": name, "source": source, "index": index, "delta": delta})


def token(text: str) -> ChatEvent:
    return ChatEvent("token", {"text": text})


def done(status: str, flow: str, dataset_id: str | None = None, **fields: Any) -> ChatEvent:
    data: dict[str, Any] = {"status": status, "flow": flow}
    if dataset_id is not None:
        data["dataset_id"] = dataset_id
    data.update({name: value for name, value in fields.items() if value is not None})
    return ChatEvent("done", data)


def error(code: str, message: str) -> ChatEvent:
    return ChatEvent("error", {"code": code, "message": message})
