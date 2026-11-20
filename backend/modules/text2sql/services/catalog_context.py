from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modules.data_dictionary.models import (
    ColumnDictionary,
    ColumnSynonym,
    TableDictionary,
)
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.metric_management.models import Metric


@dataclass(frozen=True)
class TableEntry:
    table: DatabaseTable
    schema: DatabaseSchema
    dictionary: TableDictionary | None

    @property
    def label(self) -> str:
        return self.dictionary.display_name if self.dictionary else self.table.name

    @property
    def qualified_name(self) -> str:
        return f"{self.schema.name}.{self.table.name}"


@dataclass(frozen=True)
class ColumnEntry:
    column: DatabaseColumn
    dictionary: ColumnDictionary | None
    synonyms: list[str]

    @property
    def label(self) -> str:
        return self.dictionary.display_name if self.dictionary else self.column.name


@dataclass
class CatalogContext:
    connection_id: UUID
    tables: dict[UUID, TableEntry]
    columns: list[ColumnEntry]
    metrics: list[Metric]
    columns_by_id: dict[UUID, ColumnEntry] = field(default_factory=dict)
    columns_by_table: dict[UUID, dict[str, UUID]] = field(default_factory=dict)
    metrics_by_id: dict[UUID, Metric] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for entry in self.columns:
            self.columns_by_id[entry.column.id] = entry
            self.columns_by_table.setdefault(entry.column.table_id, {})[entry.column.name.lower()] = entry.column.id
        self.metrics_by_id = {metric.id: metric for metric in self.metrics}

    def table_label(self, table_id: UUID | None) -> str | None:
        entry = self.tables.get(table_id) if table_id is not None else None
        return entry.label if entry else None

    def column_label(self, column_id: UUID) -> str | None:
        entry = self.columns_by_id.get(column_id)
        return entry.label if entry else None

    def metric_label(self, metric_id: UUID) -> str | None:
        metric = self.metrics_by_id.get(metric_id)
        return (metric.label or metric.name) if metric else None


def load_context(session: Session, connection_id: UUID) -> CatalogContext:
    table_rows = session.execute(
        select(DatabaseTable, DatabaseSchema, TableDictionary)
        .join(DatabaseSchema, DatabaseTable.schema_id == DatabaseSchema.id)
        .outerjoin(TableDictionary, TableDictionary.table_id == DatabaseTable.id)
        .where(DatabaseSchema.connection_id == connection_id)
        .order_by(DatabaseSchema.name, DatabaseTable.name)
    ).all()
    tables = {table.id: TableEntry(table, schema, dictionary) for table, schema, dictionary in table_rows}
    column_rows = session.execute(
        select(DatabaseColumn, ColumnDictionary)
        .outerjoin(ColumnDictionary, ColumnDictionary.column_id == DatabaseColumn.id)
        .where(DatabaseColumn.table_id.in_(tables))
        .order_by(DatabaseColumn.table_id, DatabaseColumn.ordinal_position)
    ).all() if tables else []
    dictionary_ids = [dictionary.id for _, dictionary in column_rows if dictionary is not None]
    synonyms: dict[UUID, list[str]] = {}
    if dictionary_ids:
        for row in session.scalars(select(ColumnSynonym).where(ColumnSynonym.column_dictionary_id.in_(dictionary_ids))):
            synonyms.setdefault(row.column_dictionary_id, []).append(row.synonym)
    columns = [
        ColumnEntry(column, dictionary, synonyms.get(dictionary.id, []) if dictionary is not None else [])
        for column, dictionary in column_rows
    ]
    metrics = list(session.scalars(
        select(Metric).where(Metric.table_id.in_(tables), Metric.is_active.is_(True))
    ).all()) if tables else []
    return CatalogContext(connection_id=connection_id, tables=tables, columns=columns, metrics=metrics)
