from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import DatabaseSchema


class DatabaseSchemaRepository(BaseRepository[DatabaseSchema]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatabaseSchema)

    def read_by_connection_id(self, connection_id: UUID) -> list[DatabaseSchema]:
        statement = select(self.model).where(self.model.connection_id == connection_id).order_by(self.model.name)
        return list(self.session.scalars(statement).all())

    def read_by_connection_and_name(self, connection_id: UUID, name: str) -> DatabaseSchema | None:
        statement = select(self.model).where(self.model.connection_id == connection_id, self.model.name == name)
        return self.session.scalar(statement)

    def delete_missing(self, connection_id: UUID, names: Collection[str]) -> None:
        statement = delete(self.model).where(self.model.connection_id == connection_id, self.model.name.not_in(names))
        self.session.execute(statement, execution_options={"synchronize_session": False})
