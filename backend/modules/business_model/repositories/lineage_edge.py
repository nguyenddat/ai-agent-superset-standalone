from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import LineageEdge


class LineageEdgeRepository(BaseRepository[LineageEdge]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, LineageEdge)

    def read_between(self, dictionary_ids: Collection[UUID]) -> list[LineageEdge]:
        if not dictionary_ids:
            return []
        statement = select(self.model).where(
            self.model.source_table_dictionary_id.in_(dictionary_ids),
            self.model.target_table_dictionary_id.in_(dictionary_ids),
        )
        return list(self.session.scalars(statement).all())

    def read_by_key(self, source_id: UUID, target_id: UUID, kind: str) -> LineageEdge | None:
        return self.session.scalar(select(self.model).where(
            self.model.source_table_dictionary_id == source_id,
            self.model.target_table_dictionary_id == target_id,
            self.model.kind == kind,
        ))
