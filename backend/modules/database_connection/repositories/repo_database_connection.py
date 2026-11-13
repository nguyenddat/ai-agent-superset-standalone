from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import DatabaseConnection


class DatabaseConnectionRepository(BaseRepository[DatabaseConnection]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatabaseConnection)

    def read_by_name(self, name: str) -> DatabaseConnection | None:
        return self.session.scalar(select(self.model).where(self.model.name == name))

    def read_active(self) -> list[DatabaseConnection]:
        statement = select(self.model).where(self.model.is_active.is_(True)).order_by(self.model.name)
        return list(self.session.scalars(statement).all())
