from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import ColumnDictionary


class ColumnDictionaryRepository(BaseRepository[ColumnDictionary]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ColumnDictionary)

    def read_by_column_ids(self, column_ids: Iterable[UUID]) -> list[ColumnDictionary]:
        ids = list(column_ids)
        if not ids:
            return []
        return list(self.session.scalars(select(self.model).where(self.model.column_id.in_(ids))).all())
