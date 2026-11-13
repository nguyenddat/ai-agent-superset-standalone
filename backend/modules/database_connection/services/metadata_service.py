from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.common.base_model import utc_now
from backend.core.setting import config

from ..models import DatabaseColumn, DatabaseSchema, DatabaseTable
from ..repositories import (
    DatabaseColumnRepository,
    DatabaseConnectionRepository,
    DatabaseSchemaRepository,
    DatabaseTableRepository,
)
from ..utils.exceptions import (
    ConnectionNotFoundError,
    InactiveConnectionError,
    MetadataNotFoundError,
    SourceDatabaseUnavailableError,
)


@dataclass(frozen=True)
class SourceColumn:
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    is_primary_key: bool
    default_value: str | None
    description: str | None


@dataclass(frozen=True)
class SourceTable:
    name: str
    table_type: str
    description: str | None
    columns: tuple[SourceColumn, ...]


@dataclass(frozen=True)
class SourceSchema:
    name: str
    tables: tuple[SourceTable, ...]


@dataclass(frozen=True)
class SyncResult:
    status: str
    last_synced_at: datetime
    schema_count: int
    table_count: int
    column_count: int


def scan_source_database(url: URL) -> list[SourceSchema]:
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            schemas = []
            for schema_name in sorted(inspector.get_schema_names()):
                if schema_name == "information_schema" or schema_name.startswith("pg_"):
                    continue
                names = [
                    (name, "TABLE") for name in inspector.get_table_names(schema=schema_name)
                ] + [
                    (name, "VIEW") for name in inspector.get_view_names(schema=schema_name)
                ] + [
                    (name, "MATERIALIZED_VIEW")
                    for name in inspector.get_materialized_view_names(schema=schema_name)
                ]
                tables = []
                for table_name, table_type in sorted(names):
                    primary_keys = set(
                        inspector.get_pk_constraint(table_name, schema=schema_name).get("constrained_columns") or []
                    )
                    columns = tuple(
                        SourceColumn(
                            name=column["name"],
                            data_type=str(column["type"]),
                            ordinal_position=index,
                            is_nullable=bool(column.get("nullable", True)),
                            is_primary_key=column["name"] in primary_keys,
                            default_value=None if column.get("default") is None else str(column["default"]),
                            description=column.get("comment"),
                        )
                        for index, column in enumerate(inspector.get_columns(table_name, schema=schema_name), start=1)
                    )
                    comment = inspector.get_table_comment(table_name, schema=schema_name).get("text")
                    tables.append(SourceTable(table_name, table_type, comment, columns))
                schemas.append(SourceSchema(schema_name, tuple(tables)))
            return schemas
    finally:
        engine.dispose()


class MetadataService:
    def __init__(
        self,
        session: Session,
        *,
        encryption_key: str | None = None,
        scanner: Callable[[URL], list[SourceSchema]] = scan_source_database,
    ) -> None:
        key = encryption_key if encryption_key is not None else config.require_connection_encryption_key()
        self.cipher = Fernet(key.encode())
        self.connections = DatabaseConnectionRepository(session)
        self.schemas = DatabaseSchemaRepository(session)
        self.tables = DatabaseTableRepository(session)
        self.columns = DatabaseColumnRepository(session)
        self.session = session
        self.scanner = scanner

    def read_schemas(self, connection_id: UUID) -> list[DatabaseSchema]:
        if self.connections.read_by_id(connection_id) is None:
            raise ConnectionNotFoundError()
        return self.schemas.read_by_connection_id(connection_id)

    def read_tables(self, schema_id: UUID) -> list[DatabaseTable]:
        if self.schemas.read_by_id(schema_id) is None:
            raise MetadataNotFoundError()
        return self.tables.read_by_schema_id(schema_id)

    def read_columns(self, table_id: UUID) -> list[DatabaseColumn]:
        if self.tables.read_by_id(table_id) is None:
            raise MetadataNotFoundError()
        return self.columns.read_by_table_id(table_id)

    def sync(self, connection_id: UUID) -> SyncResult:
        source = self.connections.read_by_id(connection_id)
        if source is None:
            raise ConnectionNotFoundError()
        if not source.is_active:
            raise InactiveConnectionError()
        try:
            uri = self.cipher.decrypt(source.uri_ciphertext.encode()).decode("utf-8")
            snapshot = self.scanner(make_url(uri))
        except (InvalidToken, UnicodeError, SQLAlchemyError, OSError, TimeoutError):
            raise SourceDatabaseUnavailableError() from None

        synced_at = utc_now()
        table_count = 0
        column_count = 0
        for source_schema in snapshot:
            schema = self.schemas.read_by_connection_and_name(connection_id, source_schema.name)
            if schema is None:
                schema = self.schemas.create(DatabaseSchema(
                    connection_id=connection_id, name=source_schema.name, last_synced_at=synced_at
                ))
            else:
                self.schemas.update(schema, {"last_synced_at": synced_at}, flush=False)
            for source_table in source_schema.tables:
                table = self.tables.read_by_schema_and_name(schema.id, source_table.name)
                values = {
                    "table_type": source_table.table_type,
                    "description": source_table.description,
                    "last_synced_at": synced_at,
                }
                if table is None:
                    table = self.tables.create(DatabaseTable(schema_id=schema.id, name=source_table.name, **values))
                else:
                    self.tables.update(table, values, flush=False)
                table_count += 1
                for source_column in source_table.columns:
                    column = self.columns.read_by_table_and_name(table.id, source_column.name)
                    column_values = {
                        "data_type": source_column.data_type,
                        "ordinal_position": source_column.ordinal_position,
                        "is_nullable": source_column.is_nullable,
                        "is_primary_key": source_column.is_primary_key,
                        "default_value": source_column.default_value,
                        "description": source_column.description,
                    }
                    if column is None:
                        self.columns.create(DatabaseColumn(table_id=table.id, name=source_column.name, **column_values))
                    else:
                        self.columns.update(column, column_values, flush=False)
                    column_count += 1
                self.columns.delete_missing(table.id, [c.name for c in source_table.columns])
            self.tables.delete_missing(schema.id, [t.name for t in source_schema.tables])
        self.schemas.delete_missing(connection_id, [s.name for s in snapshot])
        self.session.flush()
        return SyncResult("completed", synced_at, len(snapshot), table_count, column_count)
