from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from backend.common.base_repository import BaseRepository
from backend.modules.database_connection.models import DatabaseColumn

from ..models import ColumnDictionary


class ColumnDictionaryRepository(BaseRepository[ColumnDictionary]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ColumnDictionary)

    def read_by_column_ids(self, column_ids: Iterable[UUID]) -> list[ColumnDictionary]:
        ids = list(column_ids)
        if not ids:
            return []
        return list(self.session.scalars(select(self.model).where(self.model.column_id.in_(ids))).all())

    def read_saved_column_ids(self, column_ids: Iterable[UUID]) -> set[UUID]:
        ids = list(column_ids)
        if not ids:
            return set()
        return set(self.session.scalars(select(self.model.column_id).where(self.model.column_id.in_(ids))).all())

    def read_table_references(self, table_ids: Iterable[UUID]) -> list[tuple[UUID, UUID]]:
        ids = list(table_ids)
        if not ids:
            return []
        source = aliased(DatabaseColumn)
        target = aliased(DatabaseColumn)
        statement = select(source.table_id, target.table_id).select_from(self.model).join(
            source, source.id == self.model.column_id
        ).join(target, target.id == self.model.referenced_column_id).where(
            source.table_id.in_(ids), target.table_id.in_(ids), source.table_id != target.table_id
        ).distinct()
        return list(self.session.execute(statement).all())
