from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modules.database_connection.models import DatabaseSchema, DatabaseTable

from ..models import Metric, SupersetDatabase, SupersetUser


class MetricRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, metric_id: UUID) -> Metric | None:
        return self.session.get(Metric, metric_id)

    def list(self, connection_id: UUID | None = None) -> list[Metric]:
        statement = select(Metric).order_by(Metric.name, Metric.id)
        if connection_id is not None:
            table_ids = (
                select(DatabaseTable.id)
                .join(DatabaseSchema)
                .where(DatabaseSchema.connection_id == connection_id)
            )
            database_ids = select(SupersetDatabase.id).where(
                SupersetDatabase.connection_id == connection_id
            )
            statement = statement.where(
                (Metric.table_id.in_(table_ids))
                | (Metric.source_database_id.in_(database_ids))
            )
        return list(self.session.scalars(statement))

    def find_manual(self, table_id: UUID, name: str) -> Metric | None:
        return self.session.scalar(
            select(Metric).where(
                Metric.origin == "manual",
                Metric.table_id == table_id,
                Metric.name == name,
            )
        )

    def users_for_source(self, source_url: str) -> dict[int, SupersetUser]:
        return {
            row.source_id: row
            for row in self.session.scalars(
                select(SupersetUser).where(SupersetUser.source_url == source_url)
            )
        }

    def databases_for_source(self, source_url: str) -> dict[int, SupersetDatabase]:
        return {
            row.source_id: row
            for row in self.session.scalars(
                select(SupersetDatabase).where(
                    SupersetDatabase.source_url == source_url
                )
            )
        }

    def metrics_for_source(self, source_url: str) -> dict[int, Metric]:
        return {
            row.source_metric_id: row
            for row in self.session.scalars(
                select(Metric).where(
                    Metric.source_url == source_url, Metric.origin == "superset"
                )
            )
            if row.source_metric_id is not None
        }

    def database(self, database_id: UUID) -> SupersetDatabase | None:
        return self.session.get(SupersetDatabase, database_id)

    def databases(self) -> list[SupersetDatabase]:
        return list(
            self.session.scalars(
                select(SupersetDatabase).order_by(
                    SupersetDatabase.name, SupersetDatabase.id
                )
            )
        )

    def users(self) -> list[SupersetUser]:
        return list(
            self.session.scalars(
                select(SupersetUser).order_by(SupersetUser.username, SupersetUser.id)
            )
        )

    def local_table(
        self, connection_id: UUID, schema: str | None, table: str
    ) -> DatabaseTable | None:
        return self.session.scalar(
            select(DatabaseTable)
            .join(DatabaseSchema)
            .where(
                DatabaseSchema.connection_id == connection_id,
                DatabaseSchema.name == (schema or "public"),
                DatabaseTable.name == table,
            )
        )
