from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import exists, func, select, tuple_
from sqlalchemy.orm import Session

from ..models import Conversation, ConversationTurn, ConversationTurnFeedback


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def conversation(self, conversation_id: UUID, lock: bool = False) -> Conversation | None:
        statement = select(Conversation).where(Conversation.id == conversation_id)
        return self.session.scalar(statement.with_for_update() if lock else statement)

    def list_page(
        self, user_id: str, connection_id: UUID | None, archived: bool, query: str | None, limit: int, offset: int,
    ) -> list[Conversation]:
        statement = select(Conversation).where(
            Conversation.user_id == user_id, Conversation.is_archived.is_(archived),
        )
        if connection_id is not None:
            statement = statement.where(Conversation.connection_id == connection_id)
        if query:
            statement = statement.where(Conversation.title.ilike(f"%{_escape_like(query)}%", escape="\\"))
        statement = statement.order_by(
            Conversation.is_pinned.desc(), Conversation.last_message_at.desc().nulls_last(),
            Conversation.created_at.desc(), Conversation.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def turn_counts(self, conversation_ids: Iterable[UUID]) -> dict[UUID, int]:
        ids = list(conversation_ids)
        if not ids:
            return {}
        rows = self.session.execute(
            select(ConversationTurn.conversation_id, func.count())
            .where(ConversationTurn.conversation_id.in_(ids)).group_by(ConversationTurn.conversation_id)
        )
        return {conversation_id: count for conversation_id, count in rows}

    def last_turns(self, conversation_ids: Iterable[UUID]) -> dict[UUID, ConversationTurn]:
        ids = list(conversation_ids)
        if not ids:
            return {}
        latest = (
            select(ConversationTurn.conversation_id, func.max(ConversationTurn.sequence))
            .where(ConversationTurn.conversation_id.in_(ids)).group_by(ConversationTurn.conversation_id)
        )
        turns = self.session.scalars(select(ConversationTurn).where(
            tuple_(ConversationTurn.conversation_id, ConversationTurn.sequence).in_(latest)
        ))
        return {turn.conversation_id: turn for turn in turns}

    def turn_count(self, conversation_id: UUID) -> int:
        return self.turn_counts([conversation_id]).get(conversation_id, 0)

    def next_sequence(self, conversation_id: UUID) -> int:
        current = self.session.scalar(
            select(func.max(ConversationTurn.sequence)).where(ConversationTurn.conversation_id == conversation_id)
        )
        return (current or 0) + 1

    def turns(self, conversation_id: UUID, limit: int, offset: int) -> list[ConversationTurn]:
        return list(self.session.scalars(
            select(ConversationTurn).where(ConversationTurn.conversation_id == conversation_id)
            .order_by(ConversationTurn.sequence).offset(offset).limit(limit)
        ))

    def turn(self, conversation_id: UUID, turn_id: UUID) -> ConversationTurn | None:
        return self.session.scalar(select(ConversationTurn).where(
            ConversationTurn.id == turn_id, ConversationTurn.conversation_id == conversation_id,
        ))

    def recent_turns(self, conversation_id: UUID, statuses: Iterable[str], limit: int) -> list[ConversationTurn]:
        rows = self.session.scalars(
            select(ConversationTurn).where(
                ConversationTurn.conversation_id == conversation_id, ConversationTurn.status.in_(list(statuses)),
            ).order_by(ConversationTurn.sequence.desc()).limit(limit)
        )
        return list(reversed(list(rows)))

    def user_questions(
        self, user_id: str, connection_id: UUID, statuses: Iterable[str], excluded_ratings: Iterable[str], limit: int,
    ) -> list[str]:
        rated = exists().where(
            ConversationTurnFeedback.turn_id == ConversationTurn.id,
            ConversationTurnFeedback.rating.in_(list(excluded_ratings)),
        )
        return list(self.session.scalars(
            select(ConversationTurn.question).join(Conversation, Conversation.id == ConversationTurn.conversation_id)
            .where(
                Conversation.user_id == user_id, Conversation.connection_id == connection_id,
                ConversationTurn.status.in_(list(statuses)), ~rated,
            ).order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc()).limit(limit)
        ))

    def connection_results(self, connection_id: UUID, statuses: Iterable[str], limit: int) -> list[list | None]:
        return list(self.session.scalars(
            select(ConversationTurn.results).join(Conversation, Conversation.id == ConversationTurn.conversation_id)
            .where(Conversation.connection_id == connection_id, ConversationTurn.status.in_(list(statuses)))
            .order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc()).limit(limit)
        ))

    def feedback(self, turn_id: UUID, user_id: str) -> ConversationTurnFeedback | None:
        return self.session.scalar(select(ConversationTurnFeedback).where(
            ConversationTurnFeedback.turn_id == turn_id, ConversationTurnFeedback.user_id == user_id,
        ))

    def feedbacks(self, turn_ids: Iterable[UUID], user_id: str) -> dict[UUID, ConversationTurnFeedback]:
        ids = list(turn_ids)
        if not ids:
            return {}
        rows = self.session.scalars(select(ConversationTurnFeedback).where(
            ConversationTurnFeedback.turn_id.in_(ids), ConversationTurnFeedback.user_id == user_id,
        ))
        return {row.turn_id: row for row in rows}
