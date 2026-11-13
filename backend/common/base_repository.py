from collections.abc import Iterable, Mapping
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from .base_model import Base


ModelType = TypeVar("ModelType", bound=Base)
EntityId = UUID | int


class BaseRepository(Generic[ModelType]):
    def __init__(self, session: Session, model: type[ModelType]) -> None:
        mapper = inspect(model)
        if len(mapper.primary_key) != 1 or mapper.primary_key[0].key != "id":
            raise ValueError("BaseRepository requires a model with one primary key named 'id'")

        self.session = session
        self.model = model
        self.id_column = mapper.primary_key[0]
        self.editable_columns = set(mapper.column_attrs.keys()) - {"id"}

    def read_by_id(self, entity_id: EntityId) -> ModelType | None:
        return self.session.get(self.model, entity_id)

    def read_by_ids(self, entity_ids: Iterable[EntityId]) -> list[ModelType]:
        ordered_ids = list(dict.fromkeys(entity_ids))
        if not ordered_ids:
            return []
        rows = self.session.scalars(select(self.model).where(self.id_column.in_(ordered_ids))).all()
        rows_by_id = {getattr(row, "id"): row for row in rows}
        return [rows_by_id[entity_id] for entity_id in ordered_ids if entity_id in rows_by_id]

    def read_all(self, *, offset: int = 0, limit: int = 100) -> list[ModelType]:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be non-negative and limit must be positive")
        statement = select(self.model).order_by(self.id_column).offset(offset).limit(limit)
        return list(self.session.scalars(statement).all())

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(self.model)) or 0

    def create(self, entity: ModelType, *, flush: bool = True) -> ModelType:
        self.session.add(entity)
        if flush:
            self.session.flush()
        return entity

    def create_many(self, entities: Iterable[ModelType], *, flush: bool = True) -> list[ModelType]:
        rows = list(entities)
        self.session.add_all(rows)
        if flush:
            self.session.flush()
        return rows

    def update(self, entity: ModelType, values: Mapping[str, Any], *, flush: bool = True) -> ModelType:
        unknown_columns = values.keys() - self.editable_columns
        if unknown_columns:
            raise ValueError(f"Cannot update unmapped or primary-key columns: {', '.join(sorted(unknown_columns))}")
        for attribute, value in values.items():
            setattr(entity, attribute, value)
        if flush:
            self.session.flush()
        return entity

    def delete(self, entity: ModelType, *, flush: bool = True) -> None:
        self.session.delete(entity)
        if flush:
            self.session.flush()

    def delete_by_id(self, entity_id: EntityId, *, flush: bool = True) -> bool:
        entity = self.read_by_id(entity_id)
        if entity is None:
            return False
        self.delete(entity, flush=flush)
        return True
