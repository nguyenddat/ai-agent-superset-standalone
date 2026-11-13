from collections.abc import Iterable
from typing import ClassVar, TypeVar
from uuid import UUID

from sqlalchemy import delete, select

from backend.common.base_model import BaseModel
from backend.common.base_repository import BaseRepository

ChildModel = TypeVar("ChildModel", bound=BaseModel)


class ChildRepository(BaseRepository[ChildModel]):
    parent_key: ClassVar[str]

    def read_by_parent_ids(self, parent_ids: Iterable[UUID]) -> list[ChildModel]:
        ids = list(parent_ids)
        if not ids:
            return []
        statement = select(self.model).where(getattr(self.model, self.parent_key).in_(ids)).order_by(self.model.id)
        return list(self.session.scalars(statement).all())

    def delete_by_parent_id(self, parent_id: UUID) -> None:
        statement = delete(self.model).where(getattr(self.model, self.parent_key) == parent_id)
        self.session.execute(statement, execution_options={"synchronize_session": False})
