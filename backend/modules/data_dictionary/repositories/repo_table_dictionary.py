from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import TableDictionary


class TableDictionaryRepository(BaseRepository[TableDictionary]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TableDictionary)

    def read_by_table_id(self, table_id: UUID) -> TableDictionary | None:
        return self.session.scalar(select(self.model).where(self.model.table_id == table_id))

    def read_by_table_ids(self, table_ids: Collection[UUID]) -> list[TableDictionary]:
        if not table_ids:
            return []
        return list(self.session.scalars(select(self.model).where(self.model.table_id.in_(table_ids))).all())

    def clear_catalog_references(self, catalog_id: UUID) -> None:
        statement = update(self.model).where(self.model.indicator_catalog_id == catalog_id).values(
            indicator_catalog_id=None
        )
        self.session.execute(statement, execution_options={"synchronize_session": "fetch"})
