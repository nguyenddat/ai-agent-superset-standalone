from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import DataLayer


class DataLayerRepository(BaseRepository[DataLayer]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DataLayer)

    def read_ordered(self) -> list[DataLayer]:
        statement = select(self.model).order_by(self.model.level, self.model.sort_order, self.model.name)
        return list(self.session.scalars(statement).all())

    def read_by_name(self, name: str) -> DataLayer | None:
        return self.session.scalar(select(self.model).where(func.lower(self.model.name) == name.lower()))
