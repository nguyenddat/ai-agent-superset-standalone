from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository
from backend.modules.database_connection.models import DatabaseColumn


class DatabaseColumnRepository(BaseRepository[DatabaseColumn]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatabaseColumn)

    def read_by_table_id(self, table_id: UUID) -> list[DatabaseColumn]:
        statement = select(self.model).where(self.model.table_id == table_id).order_by(
            self.model.ordinal_position, self.model.id
        )
        return list(self.session.scalars(statement).all())

    def read_by_table_and_name(self, table_id: UUID, name: str) -> DatabaseColumn | None:
        statement = select(self.model).where(self.model.table_id == table_id, self.model.name == name)
        return self.session.scalar(statement)
