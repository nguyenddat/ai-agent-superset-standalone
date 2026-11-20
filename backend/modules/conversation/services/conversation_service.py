import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.common.base_model import utc_now
from backend.common.charts import ChartSpecError, validate_chart
from backend.common.utils.type_formatters import iso_datetime
from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..models import (
    TURN_FLOWS,
    TURN_STATUSES,
    Conversation,
    ConversationTurn,
    ConversationTurnFeedback,
)
from ..repositories import ConversationRepository
from ..utils.exceptions import (
    ConversationChartInvalidError,
    ConversationConnectionNotFoundError,
    ConversationNotFoundError,
    ConversationResultNotFoundError,
    ConversationTurnNotContinuableError,
    ConversationTurnNotFoundError,
    ConversationValidationError,
)
from .result_views import normalize_results, result_fields, rows_complete

TITLE_LENGTH = 80
TITLE_MAX_LENGTH = 200
PREVIEW_LENGTH = 120
HISTORY_ANSWER_LENGTH = 500
QUESTION_MAX_LENGTH = 10000
COMMENT_MAX_LENGTH = 2000
HISTORY_STATUSES = ("answered", "needs_clarification", "cannot_answer", "join_ambiguous", "join_not_declared")
CONTINUABLE_STATUSES = ("join_ambiguous", "needs_clarification")
SUGGESTION_STATUSES = ("answered",)
REJECTED_RATINGS = ("down",)
FAILED_TURN_MESSAGE = "AI Agent không hoàn tất được câu trả lời."


@dataclass(frozen=True)
class HistoryTurn:
    question: str
    rewritten_question: str | None
    answer: str | None
    status: str = "answered"
    clarification_question: str | None = None


def shorten(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    cut = compact[:limit].rsplit(" ", 1)[0] or compact[:limit]
    return cut.rstrip() + "…"


def title_from_question(question: str) -> str:
    return shorten(question, TITLE_LENGTH)


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    head = cut.rsplit(None, 1)[0] if " " in cut or "\n" in cut else cut
    return (head or cut).rstrip() + "…"


class ConversationService:
    def __init__(self, session: Session, max_stored_rows: int | None = None) -> None:
        self.session = session
        self.repository = ConversationRepository(session)
        self.max_stored_rows = max_stored_rows or config.conversation_max_stored_rows

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        self._connection(values["connection_id"])
        title = values.get("title")
        conversation = Conversation(
            connection_id=values["connection_id"], user_id=self._user(values["user_id"]),
            title=self._title(title) if title is not None else "",
        )
        self.session.add(conversation)
        self.session.flush()
        return self._conversation(conversation, 0)

    def list_conversations(
        self, user_id: str, connection_id: UUID | None = None, archived: bool = False, query: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        if connection_id is not None:
            self._connection(connection_id)
        needle = " ".join(query.split()) if query else None
        rows = self.repository.list_page(self._user(user_id), connection_id, archived, needle or None, limit, offset)
        ids = [row.id for row in rows]
        counts = self.repository.turn_counts(ids)
        last = self.repository.last_turns(ids)
        items = []
        for row in rows:
            turn = last.get(row.id)
            items.append({
                **self._conversation(row, counts.get(row.id, 0)),
                "last_question": shorten(turn.question, PREVIEW_LENGTH) if turn else None,
                "last_status": turn.status if turn else None,
            })
        return items

    def detail(self, conversation_id: UUID, user_id: str, turns_limit: int = 100, turns_offset: int = 0) -> dict:
        conversation = self.get_owned(conversation_id, user_id)
        turns = self.repository.turns(conversation.id, turns_limit, turns_offset)
        return {
            **self._conversation(conversation, self.repository.turn_count(conversation.id)),
            "turns": self._turns(turns, conversation.user_id),
        }

    def update(self, conversation_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        conversation = self.get_owned(conversation_id, values["user_id"], lock=True)
        if values.get("title") is not None:
            conversation.title = self._title(values["title"])
        for field in ("is_pinned", "is_archived"):
            if values.get(field) is not None:
                setattr(conversation, field, bool(values[field]))
        conversation.updated_at = utc_now()
        self.session.flush()
        return self._conversation(conversation, self.repository.turn_count(conversation.id))

    def delete(self, conversation_id: UUID, user_id: str) -> None:
        self.session.delete(self.get_owned(conversation_id, user_id, lock=True))
        self.session.flush()

    def list_turns(self, conversation_id: UUID, user_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        conversation = self.get_owned(conversation_id, user_id)
        return self._turns(self.repository.turns(conversation.id, limit, offset), conversation.user_id)

    def get_turn(self, conversation_id: UUID, turn_id: UUID, user_id: str) -> dict[str, Any]:
        conversation = self.get_owned(conversation_id, user_id)
        return self._turns([self._owned_turn(conversation, turn_id)], conversation.user_id)[0]

    def delete_turn(self, conversation_id: UUID, turn_id: UUID, user_id: str) -> None:
        conversation = self.get_owned(conversation_id, user_id, lock=True)
        self.session.delete(self._owned_turn(conversation, turn_id))
        self.session.flush()

    def put_feedback(self, conversation_id: UUID, turn_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        conversation = self.get_owned(conversation_id, values["user_id"])
        turn = self._owned_turn(conversation, turn_id)
        rating = values["rating"]
        if rating not in ("up", "down"):
            raise ConversationValidationError("Đánh giá chỉ nhận 'up' hoặc 'down'.")
        comment = (values.get("comment") or "").strip() or None
        if comment is not None and len(comment) > COMMENT_MAX_LENGTH:
            raise ConversationValidationError("Nhận xét vượt quá giới hạn độ dài.")
        feedback = self.repository.feedback(turn.id, conversation.user_id)
        if feedback is None:
            try:
                with self.session.begin_nested():
                    feedback = ConversationTurnFeedback(
                        turn_id=turn.id, user_id=conversation.user_id, rating=rating, comment=comment,
                    )
                    self.session.add(feedback)
                    self.session.flush()
                return self._feedback(feedback)
            except IntegrityError:
                feedback = self.repository.feedback(turn.id, conversation.user_id)
                if feedback is None:
                    raise
        feedback.rating = rating
        feedback.comment = comment
        feedback.updated_at = utc_now()
        self.session.flush()
        return self._feedback(feedback)

    def delete_feedback(self, conversation_id: UUID, turn_id: UUID, user_id: str) -> None:
        conversation = self.get_owned(conversation_id, user_id)
        turn = self._owned_turn(conversation, turn_id)
        feedback = self.repository.feedback(turn.id, conversation.user_id)
        if feedback is not None:
            self.session.delete(feedback)
            self.session.flush()

    def put_view(
        self, conversation_id: UUID, turn_id: UUID, result_id: str, user_id: str, chart: dict[str, Any],
    ) -> dict[str, Any]:
        conversation = self.get_owned(conversation_id, user_id, lock=True)
        turn = self._owned_turn(conversation, turn_id)
        item = next((
            entry for entry in normalize_results(turn.results) or []
            if isinstance(entry, dict) and entry.get("result_id") == result_id
        ), None)
        if item is None:
            raise ConversationResultNotFoundError()
        rows = item.get("rows") if isinstance(item.get("rows"), list) else []
        try:
            checked = validate_chart(
                chart, result_fields(item), rows, result_id, rows_complete(item), config.text2sql_chart_types,
            )
        except ChartSpecError as error:
            raise ConversationChartInvalidError("\n".join(error.errors)) from None
        updated_at = iso_datetime(utc_now())
        spec = checked.json()
        turn.views = {**(turn.views or {}), result_id: {"chart": spec, "updated_at": updated_at}}
        self.session.flush()
        return {"result_id": result_id, "chart": spec, "warnings": checked.warnings, "updated_at": updated_at}

    def delete_view(self, conversation_id: UUID, turn_id: UUID, result_id: str, user_id: str) -> None:
        conversation = self.get_owned(conversation_id, user_id, lock=True)
        turn = self._owned_turn(conversation, turn_id)
        if turn.views and result_id in turn.views:
            turn.views = {key: value for key, value in turn.views.items() if key != result_id}
            self.session.flush()

    def get_owned(self, conversation_id: UUID, user_id: str, lock: bool = False) -> Conversation:
        conversation = self.repository.conversation(conversation_id, lock)
        if conversation is None or conversation.user_id != (user_id or "").strip():
            raise ConversationNotFoundError()
        return conversation

    def start(self, connection_id: UUID, user_id: str, question: str) -> Conversation:
        self._connection(connection_id)
        conversation = Conversation(
            connection_id=connection_id, user_id=self._user(user_id),
            title=title_from_question(self._question(question)),
        )
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def begin_turn(
        self, conversation: Conversation, question: str, retry_of: UUID | None = None,
        continued_from: UUID | None = None,
    ) -> ConversationTurn:
        text = self._question(question)
        locked = self.repository.conversation(conversation.id, lock=True)
        if locked is None:
            raise ConversationNotFoundError()
        if retry_of is not None and self.repository.turn(locked.id, retry_of) is None:
            raise ConversationValidationError("Lượt được thử lại không thuộc hội thoại này.")
        if continued_from is not None and self.repository.turn(locked.id, continued_from) is None:
            raise ConversationValidationError("Lượt được tiếp tục không thuộc hội thoại này.")
        if not locked.title:
            locked.title = title_from_question(text)
        turn = ConversationTurn(
            conversation_id=locked.id, sequence=self.repository.next_sequence(locked.id), question=text,
            status="running", retry_of=retry_of, continued_from=continued_from,
        )
        self.session.add(turn)
        locked.last_message_at = utc_now()
        self.session.flush()
        return turn

    def complete_turn(
        self, turn: ConversationTurn, *, status: str, flow: str | None = None, answer: str | None = None,
        rewritten_question: str | None = None, steps: list[Any] | None = None, results: list[Any] | None = None,
        rewrite: dict[str, Any] | None = None, assumptions: list[Any] | None = None,
        pii: dict[str, Any] | None = None, dataset_id: UUID | None = None, duration_ms: int | None = None,
        model: str | None = None, error_code: str | None = None, error_message: str | None = None,
        clarification_question: str | None = None, clarification_options: list[str] | None = None,
        continuation: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        if status not in TURN_STATUSES or status == "running":
            raise ConversationValidationError("Trạng thái kết thúc lượt không hợp lệ.")
        if flow is not None and flow not in TURN_FLOWS:
            raise ConversationValidationError("Luồng xử lý không hợp lệ.")
        if results is not None and not isinstance(results, list):
            raise ConversationValidationError("Kết quả truy vấn phải là danh sách.")
        turn.status = status
        turn.flow = flow
        turn.answer = answer
        turn.rewritten_question = rewritten_question
        turn.steps = self._jsonable(steps)
        turn.results = self._store_results(results)
        turn.rewrite = self._jsonable(rewrite)
        turn.assumptions = self._jsonable(assumptions)
        turn.pii = self._jsonable(pii)
        turn.dataset_id = dataset_id
        turn.duration_ms = duration_ms
        turn.model = model[:100] if model else None
        turn.error_code = error_code[:64] if error_code else None
        turn.error_message = error_message
        turn.clarification_question = clarification_question or None
        turn.clarification_options = self._jsonable(list(clarification_options)) if clarification_options else None
        turn.continuation = self._jsonable(continuation)
        conversation = self.session.get(Conversation, turn.conversation_id)
        if conversation is not None:
            conversation.last_message_at = utc_now()
        self.session.flush()
        return turn

    def recent_history(self, conversation_id: UUID, limit: int = 6) -> list[HistoryTurn]:
        if limit < 1:
            return []
        return [
            HistoryTurn(
                question=turn.question, rewritten_question=turn.rewritten_question,
                answer=clip(turn.answer, HISTORY_ANSWER_LENGTH) if turn.answer else None,
                status=turn.status, clarification_question=turn.clarification_question,
            )
            for turn in self.repository.recent_turns(conversation_id, HISTORY_STATUSES, limit)
        ]

    def continuable_turn(self, conversation: Conversation, turn_id: UUID) -> ConversationTurn:
        turn = self._owned_turn(conversation, turn_id)
        if turn.status not in CONTINUABLE_STATUSES or not isinstance(turn.continuation, dict):
            raise ConversationTurnNotContinuableError()
        return turn

    def answered_questions(self, connection_id: UUID, user_id: str, limit: int) -> list[str]:
        user = (user_id or "").strip()
        if not user or limit < 1:
            return []
        return self.repository.user_questions(user, connection_id, SUGGESTION_STATUSES, REJECTED_RATINGS, limit)

    def metric_usage(self, connection_id: UUID, turns: int = 500) -> Counter[str]:
        usage: Counter[str] = Counter()
        for results in self.repository.connection_results(connection_id, SUGGESTION_STATUSES, turns):
            for item in results if isinstance(results, list) else []:
                metric = item.get("metric") if isinstance(item, dict) and item.get("kind") == "metric" else None
                name = metric.get("name") if isinstance(metric, dict) else None
                if isinstance(name, str) and name:
                    usage[name] += 1
        return usage

    def _store_results(self, results: list[Any] | None) -> list[Any] | None:
        if results is None:
            return None
        stored = []
        for item in self._jsonable(results):
            if isinstance(item, dict) and isinstance(item.get("rows"), list):
                rows = item["rows"]
                limit = self.max_stored_rows
                item = {**item, "rows": rows[:limit], "stored_truncated": len(rows) > limit}
            stored.append(item)
        return stored

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if value is None:
            return None
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _connection(self, connection_id: UUID) -> None:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise ConversationConnectionNotFoundError()

    def _owned_turn(self, conversation: Conversation, turn_id: UUID) -> ConversationTurn:
        turn = self.repository.turn(conversation.id, turn_id)
        if turn is None:
            raise ConversationTurnNotFoundError()
        return turn

    @staticmethod
    def _user(user_id: str) -> str:
        normalized = (user_id or "").strip()
        if not normalized or len(normalized) > 255:
            raise ConversationValidationError("Mã người dùng trống hoặc quá dài.")
        return normalized

    @staticmethod
    def _title(title: str) -> str:
        normalized = " ".join(title.split())
        if not normalized:
            raise ConversationValidationError("Tiêu đề hội thoại không được để trống.")
        if len(normalized) > TITLE_MAX_LENGTH:
            raise ConversationValidationError(f"Tiêu đề hội thoại tối đa {TITLE_MAX_LENGTH} ký tự.")
        return normalized

    @staticmethod
    def _question(question: str) -> str:
        normalized = (question or "").strip()
        if not normalized or len(normalized) > QUESTION_MAX_LENGTH:
            raise ConversationValidationError("Câu hỏi trống hoặc vượt quá giới hạn độ dài.")
        return normalized

    @staticmethod
    def _conversation(conversation: Conversation, turn_count: int) -> dict[str, Any]:
        return {
            "id": conversation.id, "connection_id": conversation.connection_id, "user_id": conversation.user_id,
            "title": conversation.title, "is_pinned": conversation.is_pinned, "is_archived": conversation.is_archived,
            "last_message_at": conversation.last_message_at, "created_at": conversation.created_at,
            "updated_at": conversation.updated_at, "turn_count": turn_count,
        }

    @staticmethod
    def _feedback(feedback: ConversationTurnFeedback) -> dict[str, Any]:
        return {
            "rating": feedback.rating, "comment": feedback.comment,
            "created_at": feedback.created_at, "updated_at": feedback.updated_at,
        }

    @staticmethod
    def _resume(turn: ConversationTurn) -> dict[str, Any]:
        continuation = turn.continuation if turn.status in CONTINUABLE_STATUSES else None
        resume_id = continuation.get("resume_id") if isinstance(continuation, dict) else None
        try:
            expires_at = datetime.fromisoformat(str(continuation["expires_at"])) if resume_id else None
        except (KeyError, ValueError):
            expires_at = None
        if expires_at is None or expires_at.tzinfo is None or expires_at <= utc_now():
            return {"resume_id": None, "resume_expires_at": None}
        return {"resume_id": resume_id, "resume_expires_at": expires_at}

    def _turns(self, turns: list[ConversationTurn], user_id: str) -> list[dict[str, Any]]:
        feedbacks = self.repository.feedbacks([turn.id for turn in turns], user_id)
        return [{
            "id": turn.id, "conversation_id": turn.conversation_id, "sequence": turn.sequence,
            "question": turn.question, "rewritten_question": turn.rewritten_question, "answer": turn.answer,
            "flow": turn.flow, "status": turn.status, "steps": turn.steps, "results": normalize_results(turn.results),
            "rewrite": turn.rewrite, "assumptions": turn.assumptions, "pii": turn.pii,
            "dataset_id": turn.dataset_id, "retry_of": turn.retry_of, "continued_from": turn.continued_from,
            "clarification_question": turn.clarification_question,
            "clarification_options": turn.clarification_options or [], **self._resume(turn),
            "error_code": turn.error_code, "error": FAILED_TURN_MESSAGE if turn.status == "error" else None,
            "duration_ms": turn.duration_ms, "model": turn.model,
            "feedback": self._feedback(feedbacks[turn.id]) if turn.id in feedbacks else None, "views": turn.views,
            "created_at": turn.created_at, "updated_at": turn.updated_at,
        } for turn in turns]
