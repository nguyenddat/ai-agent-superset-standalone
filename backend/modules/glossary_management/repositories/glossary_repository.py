from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GlossaryLink, GlossaryRevision, GlossaryTerm


class GlossaryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, term_id: UUID, lock: bool = False) -> GlossaryTerm | None:
        statement = select(GlossaryTerm).where(GlossaryTerm.id == term_id)
        return self.session.scalar(statement.with_for_update() if lock else statement)

    def list(self, connection_id: UUID) -> list[GlossaryTerm]:
        return list(self.session.scalars(
            select(GlossaryTerm).where(GlossaryTerm.connection_id == connection_id)
            .order_by(GlossaryTerm.canonical_name, GlossaryTerm.id)
        ))

    def find_name(self, connection_id: UUID, normalized_name: str) -> GlossaryTerm | None:
        return self.session.scalar(select(GlossaryTerm).where(
            GlossaryTerm.connection_id == connection_id, GlossaryTerm.normalized_name == normalized_name
        ))

    def revisions(self, term_id: UUID) -> list[GlossaryRevision]:
        return list(self.session.scalars(
            select(GlossaryRevision).where(GlossaryRevision.term_id == term_id)
            .order_by(GlossaryRevision.number.desc())
        ))

    def links(self, revision_id: UUID) -> list[GlossaryLink]:
        return list(self.session.scalars(
            select(GlossaryLink).where(GlossaryLink.revision_id == revision_id)
            .order_by(GlossaryLink.kind, GlossaryLink.id)
        ))
