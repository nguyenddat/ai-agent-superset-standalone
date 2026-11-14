from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import DatabaseColumn


class DatabaseColumnRepository(BaseRepository[DatabaseColumn]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatabaseColumn)

    def read_by_table_id(self, table_id: UUID) -> list[DatabaseColumn]:
        statement = select(self.model).where(self.model.table_id == table_id).order_by(
            self.model.ordinal_position, self.model.id
        )
        return list(self.session.scalars(statement).all())

    def read_table_ids_by_column_id(self, table_ids: Collection[UUID]) -> dict[UUID, UUID]:
        if not table_ids:
            return {}
        statement = select(self.model.id, self.model.table_id).where(self.model.table_id.in_(table_ids))
        return {column_id: table_id for column_id, table_id in self.session.execute(statement)}

    def read_by_table_and_name(self, table_id: UUID, name: str) -> DatabaseColumn | None:
        statement = select(self.model).where(self.model.table_id == table_id, self.model.name == name)
        return self.session.scalar(statement)

    def delete_missing(self, table_id: UUID, names: Collection[str]) -> None:
        statement = delete(self.model).where(self.model.table_id == table_id, self.model.name.not_in(names))
        self.session.execute(statement, execution_options={"synchronize_session": False})
