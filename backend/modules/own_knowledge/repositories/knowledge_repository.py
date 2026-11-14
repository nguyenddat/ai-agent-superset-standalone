from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OwnClarification, OwnKnowledgeEntry, OwnProposal


class OwnKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def clarification(self, clarification_id: UUID, lock: bool = False) -> OwnClarification | None:
        statement = select(OwnClarification).where(OwnClarification.id == clarification_id)
        return self.session.scalar(statement.with_for_update() if lock else statement)

    def by_key(self, connection_id: UUID, user_id: str, key: str) -> OwnClarification | None:
        return self.session.scalar(select(OwnClarification).where(
            OwnClarification.connection_id == connection_id,
            OwnClarification.user_id == user_id,
            OwnClarification.idempotency_key == key,
        ))

    def proposals(self, clarification_id: UUID) -> list[OwnProposal]:
        return list(self.session.scalars(
            select(OwnProposal).where(OwnProposal.clarification_id == clarification_id).order_by(OwnProposal.id)
        ))

    def entry(self, entry_id: UUID, lock: bool = False) -> OwnKnowledgeEntry | None:
        statement = select(OwnKnowledgeEntry).where(OwnKnowledgeEntry.id == entry_id)
        return self.session.scalar(statement.with_for_update() if lock else statement)

    def own_entry(self, connection_id: UUID, user_id: str, kind: str, name: str) -> OwnKnowledgeEntry | None:
        return self.session.scalar(select(OwnKnowledgeEntry).where(
            OwnKnowledgeEntry.connection_id == connection_id,
            OwnKnowledgeEntry.user_id == user_id,
            OwnKnowledgeEntry.kind == kind,
            OwnKnowledgeEntry.normalized_name == name,
        ))

    def own_entries(self, connection_id: UUID, user_id: str) -> list[OwnKnowledgeEntry]:
        return list(self.session.scalars(
            select(OwnKnowledgeEntry).where(
                OwnKnowledgeEntry.connection_id == connection_id, OwnKnowledgeEntry.user_id == user_id,
            ).order_by(OwnKnowledgeEntry.name, OwnKnowledgeEntry.id)
        ))

    def review_entries(
        self, connection_id: UUID | None, status: str | None, user_id: str | None,
    ) -> list[OwnKnowledgeEntry]:
        statement = select(OwnKnowledgeEntry)
        if connection_id is not None:
            statement = statement.where(OwnKnowledgeEntry.connection_id == connection_id)
        if status is not None:
            statement = statement.where(OwnKnowledgeEntry.review_status == status)
        if user_id is not None:
            statement = statement.where(OwnKnowledgeEntry.user_id == user_id)
        return list(self.session.scalars(statement.order_by(OwnKnowledgeEntry.updated_at.desc(), OwnKnowledgeEntry.id)))
