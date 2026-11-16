import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from backend.core.setting import config
from backend.modules.conversation.models import ConversationTurn
from backend.modules.conversation.services import ConversationService, HistoryTurn

from ..common.errors import Text2SqlChatTurnInvalid, Text2SqlInvalidRequest, Text2SqlJoinChoiceOutdated
from ..dataset.join_schemas import JoinOption
from ..dataset.join_service import JoinService
from ..dataset.schemas import DatasetQueryPlan
from .analysis_context import ChatAnswer
from .dataset_flow import MappedDatasetPlan
from .events import ChatEvent
from .schemas import RewriteInfo

logger = logging.getLogger("text2sql.chat.turns")

HISTORY_TURNS = 6
CONTINUATION_VERSION = 1
DISCONNECTED_CODE = "client_disconnected"
DISCONNECTED_MESSAGE = "Client ngắt kết nối trước khi lượt hỏi đáp kết thúc."
UNFINISHED_CODE = "internal_error"
UNFINISHED_MESSAGE = "Stream kết thúc mà không có event done hoặc error."
ERROR_DETAIL_LENGTH = 2000


@dataclass(frozen=True)
class JoinResume:
    previous_turn_id: UUID
    question: str
    option: JoinOption
    plan: DatasetQueryPlan
    state: dict[str, Any]


@dataclass(frozen=True)
class TurnRequest:
    user_id: str
    conversation_id: UUID | None = None
    resume: JoinResume | None = None


def continuation_state(
    rewrite: RewriteInfo, mapped: MappedDatasetPlan, assumptions: list[str], reason: str, options: list[JoinOption],
) -> dict[str, Any]:
    return {
        "version": CONTINUATION_VERSION,
        "rewritten_question": rewrite.rewritten_question,
        "rewrite": rewrite.model_dump(mode="json", exclude={"analysis"}),
        "root_table_id": str(mapped.root_table_id),
        "table_ids": [str(table_id) for table_id in mapped.table_ids],
        "plan": mapped.plan.model_dump(mode="json"),
        "assumptions": list(assumptions),
        "reason": reason,
        "signatures": [option.signature for option in options],
    }


def prepare_turn(
    session: Session, connection_id: UUID, user_id: str, conversation_id: UUID | None = None,
    previous_turn_id: UUID | None = None, join_signature: str | None = None,
) -> TurnRequest:
    if conversation_id is None:
        if previous_turn_id is not None:
            raise Text2SqlChatTurnInvalid("Tiếp tục một lượt cần conversation_id.")
        return TurnRequest(user_id)
    service = ConversationService(session)
    conversation = service.get_owned(conversation_id, user_id)
    if conversation.connection_id != connection_id:
        raise Text2SqlChatTurnInvalid("Hội thoại thuộc connection khác với connection_id của request.")
    if previous_turn_id is None:
        return TurnRequest(user_id, conversation.id)
    previous = service.continuable_turn(conversation, previous_turn_id)
    state = previous.continuation or {}
    if join_signature not in (state.get("signatures") or []):
        raise Text2SqlChatTurnInvalid("Cách nối đã chọn không thuộc các phương án của lượt trước.")
    try:
        plan = DatasetQueryPlan.model_validate(state["plan"])
        table_ids = [UUID(item) for item in state["table_ids"]]
        root = UUID(state["root_table_id"])
    except (KeyError, TypeError, ValueError, PydanticValidationError):
        logger.warning("Trạng thái tiếp tục của lượt %s không đọc được", previous.id)
        raise Text2SqlJoinChoiceOutdated() from None
    try:
        join = JoinService(session).plan(connection_id, table_ids, root=root)
    except Text2SqlInvalidRequest:
        raise Text2SqlJoinChoiceOutdated() from None
    option = next((item for item in join.options if item.signature == join_signature), None)
    if option is None:
        raise Text2SqlJoinChoiceOutdated()
    return TurnRequest(user_id, conversation.id, JoinResume(previous.id, previous.question, option, plan, state))


def history_entry(item: HistoryTurn) -> dict[str, Any]:
    return {
        "question": item.question, "rewritten_question": item.rewritten_question, "status": item.status,
        "answer": item.answer, "clarification_question": item.clarification_question,
    }


class TurnRecorder:
    def __init__(self, session_factory: Callable[[], Session], max_stored_rows: int | None = None) -> None:
        self.session_factory = session_factory
        self.max_stored_rows = max_stored_rows
        self.session: Session | None = None
        self.turn: ConversationTurn | None = None
        self.history: list[dict[str, Any]] = []
        self.steps: dict[str, dict[str, Any]] = {}
        self.results: list[dict[str, Any]] = []
        self.tokens: list[str] = []
        self.final: dict[str, Any] | None = None
        self.failure: dict[str, Any] | None = None
        self.finished = False
        self.started = monotonic()

    @property
    def ids(self) -> dict[str, str]:
        assert self.turn is not None
        return {"conversation_id": str(self.turn.conversation_id), "turn_id": str(self.turn.id)}

    def open(self, connection_id: UUID, question: str, request: TurnRequest) -> None:
        self.session = self.session_factory()
        service = ConversationService(self.session, self.max_stored_rows)
        try:
            if request.conversation_id is None:
                conversation = service.start(connection_id, request.user_id, question)
            else:
                conversation = service.get_owned(request.conversation_id, request.user_id)
            history = [] if request.resume else service.recent_history(conversation.id, HISTORY_TURNS)
            self.turn = service.begin_turn(
                conversation, question, continued_from=request.resume.previous_turn_id if request.resume else None,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.history = [history_entry(item) for item in history]

    def observe(self, event: ChatEvent) -> ChatEvent:
        data = event.data
        if event.event == "step":
            entry = self._step(data["step"])
            entry["status"] = data["status"]
            if data.get("detail"):
                entry["detail"] = data["detail"]
        elif event.event == "reasoning":
            items = self._step(data["step"])["reasoning"]
            while len(items) <= data["index"]:
                items.append({"source": data["source"], "text": ""})
            items[data["index"]]["text"] += data["delta"]
        elif event.event == "data":
            self.results.append(data)
        elif event.event == "token":
            self.tokens.append(data["text"])
        elif event.event == "done":
            self.final = data
            if self.turn is not None:
                return ChatEvent("done", {**data, **self.ids})
        elif event.event == "error":
            self.failure = data
        return event

    def _step(self, name: str) -> dict[str, Any]:
        return self.steps.setdefault(name, {"step": name, "status": "started", "detail": {}, "reasoning": []})

    def finish(self, answer: ChatAnswer | None, disconnected: bool = False) -> None:
        if self.finished or self.turn is None or self.session is None:
            return
        self.finished = True
        values = self._values(answer, disconnected)
        try:
            ConversationService(self.session, self.max_stored_rows).complete_turn(self.turn, **values)
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Không ghi được kết quả lượt hỏi đáp %s", self.turn.id)

    def _values(self, answer: ChatAnswer | None, disconnected: bool) -> dict[str, Any]:
        final = self.final or {}
        error_code: str | None = None
        error_message: str | None = None
        if self.final is not None:
            status = final["status"]
            if status == "error":
                error_code = (answer.error_code if answer else None) or UNFINISHED_CODE
                error_message = answer.error_detail if answer else None
        elif self.failure is not None:
            status = "error"
            error_code = self.failure.get("code") or UNFINISHED_CODE
            error_message = (answer.error_detail if answer else None) or self.failure.get("message")
        else:
            status = "error"
            error_code = DISCONNECTED_CODE if disconnected else UNFINISHED_CODE
            error_message = DISCONNECTED_MESSAGE if disconnected else UNFINISHED_MESSAGE
        rewrite = answer.rewrite if answer else None
        return {
            "status": status, "flow": final.get("flow") or (answer.flow if answer else "none"),
            "answer": "".join(self.tokens) or None,
            "rewritten_question": rewrite.rewritten_question if rewrite else None,
            "steps": list(self.steps.values()) or None, "results": self.results or None,
            "rewrite": {
                "glossary_terms": [item.name for item in rewrite.glossary_terms],
                "rules": [item.name for item in rewrite.rules],
                "own_knowledge": [item.name for item in rewrite.own_knowledge], "changes": rewrite.changes,
            } if rewrite else None,
            "assumptions": final["assumptions"] if "assumptions" in final else (answer.assumptions if answer else None),
            "pii": self._pii(), "dataset_id": answer.dataset_id if answer else None,
            "duration_ms": int((monotonic() - self.started) * 1000), "model": config.openrouter_model,
            "error_code": error_code, "error_message": error_message[:ERROR_DETAIL_LENGTH] if error_message else None,
            "clarification_question": final.get("clarification_question"),
            "clarification_options": final.get("clarification_options"),
            "continuation": answer.continuation if answer and status == "join_ambiguous" else None,
        }

    def _pii(self) -> dict[str, Any] | None:
        reports = [item["pii"] for item in self.results if isinstance(item.get("pii"), dict)]
        if not reports:
            return None
        detected: dict[str, int] = {}
        for report in reports:
            for kind, count in (report.get("detected") or {}).items():
                detected[kind] = detected.get(kind, 0) + int(count)
        masked = (name for report in reports for name in report.get("masked_columns") or [])
        return {
            "confirmation": reports[0].get("confirmation"),
            "masked_columns": list(dict.fromkeys(masked)),
            "detected": detected,
            "warnings": list(dict.fromkeys(report["warning"] for report in reports if report.get("warning"))),
        }

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
