from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.modules.conversation.services import ConversationService
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.metric_management.models import Metric

from ..common.errors import Text2SqlConnectionNotFound

SuggestionSource = Literal["history", "rule_example", "metric"]
HISTORY_FACTOR = 5
HISTORY_MIN = 50
QUESTION_MAX_LENGTH = 2000


@dataclass(frozen=True)
class Suggestion:
    question: str
    source: SuggestionSource


def normalize_question(text: str) -> str:
    return " ".join(text.split())


def metric_question(label: str, has_time: bool) -> str:
    return f"{label} theo tháng" if has_time else f"{label} là bao nhiêu?"


class SuggestionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def suggest(self, connection_id: UUID, user_id: str | None = None, limit: int = 6) -> list[Suggestion]:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        picked: list[Suggestion] = []
        seen: set[str] = set()
        sources: list[tuple[SuggestionSource, Iterator[str]]] = [
            ("history", self.history(connection_id, user_id, limit)),
            ("rule_example", self.rule_examples(connection_id)),
            ("metric", self.metric_questions(connection_id)),
        ]
        for source, questions in sources:
            for raw in questions:
                question = normalize_question(raw) if isinstance(raw, str) else ""
                key = question.casefold()
                if not question or len(question) > QUESTION_MAX_LENGTH or key in seen:
                    continue
                seen.add(key)
                picked.append(Suggestion(question, source))
                if len(picked) >= limit:
                    return picked
        return picked

    def history(self, connection_id: UUID, user_id: str | None, limit: int) -> Iterator[str]:
        if not user_id or not user_id.strip():
            return
        size = max(limit * HISTORY_FACTOR, HISTORY_MIN)
        yield from ConversationService(self.session).answered_questions(connection_id, user_id, size)

    def rule_examples(self, connection_id: UUID) -> Iterator[str]:
        for rule in ExpertRuleService(self.session).discovery(connection_id):
            for example in rule.get("examples") or []:
                question = example.get("question") if isinstance(example, dict) else None
                if isinstance(question, str):
                    yield question

    def metric_questions(self, connection_id: UUID) -> Iterator[str]:
        metrics = list(self.session.scalars(
            select(Metric).join(DatabaseTable, DatabaseTable.id == Metric.table_id)
            .join(DatabaseSchema, DatabaseSchema.id == DatabaseTable.schema_id)
            .where(
                DatabaseSchema.connection_id == connection_id, Metric.is_active.is_(True), Metric.source_sql.is_(None),
            ).order_by(func.lower(func.coalesce(Metric.label, Metric.name)), Metric.name, Metric.id)
        ))
        if not metrics:
            return
        usage = ConversationService(self.session).metric_usage(connection_id)
        timed = self.tables_with_time({metric.table_id for metric in metrics if metric.table_id is not None})
        ranked = sorted(enumerate(metrics), key=lambda item: (-usage.get(item[1].name, 0), item[0]))
        for _, metric in ranked:
            yield metric_question(metric.label or metric.name, metric.table_id in timed)

    def tables_with_time(self, table_ids: Iterable[UUID]) -> set[UUID]:
        ids = list(table_ids)
        if not ids:
            return set()
        data_type = func.lower(DatabaseColumn.data_type)
        return set(self.session.scalars(
            select(DatabaseColumn.table_id).where(
                DatabaseColumn.table_id.in_(ids), or_(data_type == "date", data_type.like("timestamp%")),
            ).distinct()
        ))
