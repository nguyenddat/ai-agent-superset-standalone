from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository
from backend.modules.database_connection.models import DatabaseTable


class DatabaseTableRepository(BaseRepository[DatabaseTable]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatabaseTable)

    def read_by_schema_id(self, schema_id: UUID) -> list[DatabaseTable]:
        statement = select(self.model).where(self.model.schema_id == schema_id).order_by(self.model.name)
        return list(self.session.scalars(statement).all())

    def read_by_schema_and_name(self, schema_id: UUID, name: str) -> DatabaseTable | None:
        statement = select(self.model).where(self.model.schema_id == schema_id, self.model.name == name)
        return self.session.scalar(statement)

    def delete_missing(self, schema_id: UUID, names: Collection[str]) -> None:
        statement = delete(self.model).where(self.model.schema_id == schema_id, self.model.name.not_in(names))
        self.session.execute(statement, execution_options={"synchronize_session": False})
