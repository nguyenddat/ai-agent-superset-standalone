from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository
from backend.modules.database_connection.models import DatabaseSchema, DatabaseTable

from ..models import LineageColumnDependency, LineageTransformation, LineageTransformationInput


class LineageRepository(BaseRepository[LineageTransformation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, LineageTransformation)

    def read_by_connection_id(self, connection_id: UUID) -> list[LineageTransformation]:
        statement = (
            select(self.model)
            .join(DatabaseTable, DatabaseTable.id == self.model.target_table_id)
            .join(DatabaseSchema, DatabaseSchema.id == DatabaseTable.schema_id)
            .where(DatabaseSchema.connection_id == connection_id)
            .order_by(self.model.name, self.model.id)
        )
        return list(self.session.scalars(statement).all())

    def read_parts(
        self, transformation_ids: Collection[UUID],
    ) -> tuple[list[LineageTransformationInput], list[LineageColumnDependency]]:
        if not transformation_ids:
            return [], []
        inputs = self.session.scalars(
            select(LineageTransformationInput)
            .where(LineageTransformationInput.transformation_id.in_(transformation_ids))
            .order_by(LineageTransformationInput.id)
        ).all()
        dependencies = self.session.scalars(
            select(LineageColumnDependency)
            .where(LineageColumnDependency.transformation_id.in_(transformation_ids))
            .order_by(LineageColumnDependency.id)
        ).all()
        return list(inputs), list(dependencies)

    def replace_parts(
        self, transformation_id: UUID, source_table_ids: list[UUID], dependencies: list[dict],
    ) -> None:
        self.session.execute(delete(LineageColumnDependency).where(
            LineageColumnDependency.transformation_id == transformation_id
        ))
        self.session.execute(delete(LineageTransformationInput).where(
            LineageTransformationInput.transformation_id == transformation_id
        ))
        self.session.add_all([
            LineageTransformationInput(transformation_id=transformation_id, source_table_id=table_id)
            for table_id in source_table_ids
        ])
        self.session.add_all([
            LineageColumnDependency(transformation_id=transformation_id, **item) for item in dependencies
        ])
        self.session.flush()
