import json
from collections.abc import Callable
from typing import Any

from pydantic_core import to_jsonable_python

from ..schemas import AgentStepOut, ChatOut, ExplanationOut, PreprocessOut, QuestionAnswerOut
from .pii_masker import PiiMasker, split_placeholder_tail

Emit = Callable[[str, dict[str, Any]], None]
Event = tuple[str, dict[str, Any]]

KNOWLEDGE_NAMES = ("glossary", "expert_rules", "own_knowledge")

QUESTION_STARTED = "question_started"
TOOL_STARTED = "tool_started"
ANSWER_DELTA = "answer_delta"
ANSWER_RESET = "answer_reset"
SYNTHESIZE_STARTED = "synthesize_started"


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=to_jsonable_python)
    return f"event: {event}\ndata: {payload}\n\n"


def preprocess_event(preprocess: PreprocessOut) -> dict[str, Any]:
    return {
        "rewritten_question": preprocess.rewritten_question, "is_split": preprocess.is_split,
        "execution_mode": preprocess.execution_mode, "stages": preprocess.stages,
        "questions": [
            {
                "position": item.position, "question": item.question, "depends_on": item.depends_on,
                "question_type": item.question_type, "business_concepts": item.business_concepts,
                "metrics": [{"name": metric.name, "label": metric.label} for metric in item.knowledge.metrics],
                **{
                    field: [hit.display_name for hit in getattr(item.knowledge, field)] for field in KNOWLEDGE_NAMES
                },
            }
            for item in preprocess.questions
        ],
    }


def step_event(position: int, step: AgentStepOut) -> dict[str, Any]:
    return {"position": position, **step.model_dump(mode="json")}


def lookup_event(position: int, tool: str, arguments: dict[str, Any], output: Any) -> dict[str, Any]:
    error = output.get("error") if isinstance(output, dict) else None
    return step_event(position, AgentStepOut(tool=tool, arguments=arguments, error=error))


def tool_started_event(position: int, tool: str, subject: str | None) -> dict[str, Any]:
    return {"position": position, "tool": tool, "subject": subject}


def delta_event(position: int | None, round_: int, final: bool, text: str) -> dict[str, Any]:
    return {"position": position, "round": round_, "final": final, "text": text}


def reset_event(position: int | None, round_: int) -> dict[str, Any]:
    return {"position": position, "round": round_}


def answered_event(answer: QuestionAnswerOut) -> dict[str, Any]:
    return {
        "position": answer.position, "question": answer.question, "answer": answer.answer,
        "exhausted": answer.exhausted,
    }


def update_events(node: str, update: dict[str, Any] | None) -> list[Event]:
    if not update:
        return []
    if node == "preprocess":
        return [("preprocess", preprocess_event(update["preprocess"]))]
    if node == "synthesize":
        return [("answer", {"answer": update["answer"]})]
    if node != "answer_question":
        return []
    events: list[Event] = [
        ("question_waiting", {"position": position, "question": pending.question, "options": pending.options})
        for position, pending in update.get("pending", {}).items() if pending is not None
    ]
    events.extend(("question_answered", answered_event(answer)) for answer in update.get("answers", {}).values())
    return events


def clarification_event(out: ChatOut) -> dict[str, Any]:
    return {
        "question": out.clarification_question, "options": out.clarification_options, "resume_id": out.resume_id,
        "expires_at": out.resume_expires_at,
    }


def done_event(out: ChatOut) -> dict[str, Any]:
    return {
        "status": out.status, "answer": out.answer, "clarification_question": out.clarification_question,
        "clarification_options": out.clarification_options, "resume_id": out.resume_id,
        "resume_expires_at": out.resume_expires_at, "conversation_id": out.conversation_id, "turn_id": out.turn_id,
        "history_answer": out.history_answer,
    }


# Trường gửi người dùng có thể chứa nhãn thay thế, được đổi về giá trị thật; sql và arguments giữ đúng thứ đã chạy.
UNMASKED_FIELDS = {
    "answer": ("answer",), "question_answered": ("answer",), "question_waiting": ("question", "options"),
    "tool": ("rows", "chart", "explanations"),
}


class UnmaskingEmit:
    def __init__(self, emit: Emit, masker: PiiMasker) -> None:
        self.emit = emit
        self.masker = masker
        self.held: dict[tuple[int | None, int], str] = {}

    def __call__(self, event: str, data: dict[str, Any]) -> None:
        if event == ANSWER_DELTA:
            key = (data["position"], data["round"])
            text, self.held[key] = split_placeholder_tail(self.held.get(key, "") + data["text"])
            if text:
                self.emit(event, {**data, "text": self.masker.unmask(text)})
            return
        if event == ANSWER_RESET:
            self.held.pop((data["position"], data["round"]), None)
        fields = [name for name in UNMASKED_FIELDS.get(event, ()) if name in data]
        if fields:
            data = {**data, **{name: self.masker.unmask_value(data[name]) for name in fields}}
        self.emit(event, data)


def unmasked_step(step: AgentStepOut, masker: PiiMasker) -> AgentStepOut:
    if not masker.values:
        return step
    return step.model_copy(update={
        "rows": masker.unmask_value(step.rows),
        "chart": masker.unmask_value(step.chart),
        "explanations": [
            ExplanationOut.model_validate(masker.unmask_value(item.model_dump())) for item in step.explanations
        ],
    })


def unmasked_answer(answer: QuestionAnswerOut, masker: PiiMasker) -> QuestionAnswerOut:
    return answer.model_copy(update={
        "answer": masker.unmask(answer.answer), "steps": [unmasked_step(step, masker) for step in answer.steps],
    })
