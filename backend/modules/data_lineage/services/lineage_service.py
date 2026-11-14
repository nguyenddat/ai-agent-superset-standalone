from collections import defaultdict
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.core.setting import config
from backend.modules.business_model.models import LineageEdge
from backend.modules.data_dictionary.models import TableDictionary
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.database_connection.services.metadata_scope import MetadataScope
from backend.modules.database_connection.utils.exceptions import InactiveConnectionError, SourceDatabaseUnavailableError

from ..models import LineageTransformation
from ..repositories import LineageRepository
from ..utils.exceptions import LineageConflictError, LineageNotFoundError, LineageValidationError
from .sql_preview import preview_sql

MAX_SQL_BYTES = 1024 * 1024


class DataLineageService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LineageRepository(session)

    def list_transformations(self, connection_id: UUID) -> list[dict[str, Any]]:
        visible_tables = self._visible_tables(connection_id)
        rows = [
            row for row in self.repository.read_by_connection_id(connection_id)
            if row.target_table_id in visible_tables
        ]
        inputs, dependencies = self.repository.read_parts([row.id for row in rows])
        inputs_by_id: dict[UUID, list[UUID]] = defaultdict(list)
        dependencies_by_id: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for item in inputs:
            inputs_by_id[item.transformation_id].append(item.source_table_id)
        for item in dependencies:
            dependencies_by_id[item.transformation_id].append({
                "source_column_id": item.source_column_id,
                "target_column_id": item.target_column_id,
                "role": item.role,
            })
        return [
            self._out(row, inputs_by_id[row.id], dependencies_by_id[row.id]) for row in rows
            if set(inputs_by_id[row.id]) <= visible_tables.keys()
        ]

    def get_transformation(self, connection_id: UUID, transformation_id: UUID) -> dict[str, Any]:
        for row in self.list_transformations(connection_id):
            if row["id"] == transformation_id:
                return row
        raise LineageNotFoundError()

    def save_transformation(
        self, connection_id: UUID, values: dict[str, Any], transformation_id: UUID | None = None,
    ) -> dict[str, Any]:
        visible_tables = self._visible_tables(connection_id)
        target_id = values["target_table_id"]
        input_ids = values["source_table_ids"]
        dependencies = values["dependencies"]
        if target_id not in visible_tables or not input_ids or len(input_ids) != len(set(input_ids)):
            raise LineageValidationError("Bảng đích và danh sách bảng nguồn phải thuộc phạm vi kết nối.")
        if set(input_ids) - visible_tables.keys():
            raise LineageValidationError("Bảng nguồn không thuộc phạm vi kết nối.")
        name = values["name"].strip()
        if not name:
            raise LineageValidationError("Tên phép biến đổi không được để trống.")
        if values.get("origin", "manual") not in {"manual", "sql_job", "view_sql"}:
            raise LineageValidationError("Nguồn khai báo không hợp lệ.")
        sql_text = values.get("sql_text")
        if sql_text is not None and len(sql_text.encode("utf-8")) > MAX_SQL_BYTES:
            raise LineageValidationError("SQL vượt quá 1 MB.")
        if values.get("origin") in {"view_sql", "sql_job"} and not sql_text:
            raise LineageValidationError("Nguồn SQL phải có câu lệnh định nghĩa phép biến đổi.")
        if values.get("origin") == "view_sql" and visible_tables[target_id][1].table_type not in {
            "VIEW", "MATERIALIZED_VIEW",
        }:
            raise LineageValidationError("Nguồn view_sql chỉ dùng cho view hoặc materialized view.")
        checked_dependencies = self._check_dependencies(target_id, set(input_ids), dependencies)
        fields = {
            "target_table_id": target_id,
            "name": name,
            "description": values.get("description"),
            "sql_text": sql_text,
            "origin": values.get("origin", "manual"),
        }
        try:
            with self.session.begin_nested():
                if transformation_id is None:
                    row = self.repository.create(LineageTransformation(**fields))
                else:
                    row = self.repository.read_by_id(transformation_id)
                    if row is None or row.target_table_id not in visible_tables:
                        raise LineageNotFoundError()
                    self.repository.update(row, fields)
                self.repository.replace_parts(row.id, input_ids, checked_dependencies)
        except IntegrityError:
            raise LineageConflictError() from None
        return self.get_transformation(connection_id, row.id)

    def delete_transformation(self, connection_id: UUID, transformation_id: UUID) -> None:
        visible_tables = self._visible_tables(connection_id)
        row = self.repository.read_by_id(transformation_id)
        if row is None or row.target_table_id not in visible_tables:
            raise LineageNotFoundError()
        self.repository.delete(row)

    def graph(self, connection_id: UUID) -> dict[str, Any]:
        visible_tables = self._visible_tables(connection_id)
        transformations = self.list_transformations(connection_id)
        source_column_ids = {
            dependency["source_column_id"]
            for item in transformations for dependency in item["dependencies"]
        }
        column_table_ids = {
            column.id: column.table_id for column in self.session.scalars(
                select(DatabaseColumn).where(DatabaseColumn.id.in_(source_column_ids))
            )
        }
        edges = [
            {
                "transformation_id": item["id"],
                "source_table_id": source_id,
                "target_table_id": item["target_table_id"],
                "kind": "transform",
                "origin": item["origin"],
                "dependencies": [
                    dependency for dependency in item["dependencies"]
                    if column_table_ids.get(dependency["source_column_id"]) == source_id
                ],
            }
            for item in transformations for source_id in item["source_table_ids"]
        ]
        dictionaries = {
            row.id: row.table_id for row in self.session.scalars(
                select(TableDictionary).where(TableDictionary.table_id.in_(visible_tables))
            )
        }
        if dictionaries:
            manual_edges = self.session.scalars(
                select(LineageEdge).where(
                    LineageEdge.source_table_dictionary_id.in_(dictionaries),
                    LineageEdge.target_table_dictionary_id.in_(dictionaries),
                    LineageEdge.kind == "flow", LineageEdge.is_manual.is_(True), LineageEdge.is_hidden.is_(False),
                )
            )
            edges.extend({
                "transformation_id": None,
                "source_table_id": dictionaries[edge.source_table_dictionary_id],
                "target_table_id": dictionaries[edge.target_table_dictionary_id],
                "kind": "flow", "origin": "manual_edge", "dependencies": [],
            } for edge in manual_edges)
        return {"connection_id": connection_id, "edges": edges}

    def preview(self, connection_id: UUID, target_table_id: UUID, sql_text: str) -> dict[str, Any]:
        tables = self._visible_tables(connection_id)
        if target_table_id not in tables:
            raise LineageNotFoundError("Không tìm thấy bảng đích trong phạm vi kết nối.")
        if not sql_text.strip() or len(sql_text.encode("utf-8")) > MAX_SQL_BYTES:
            raise LineageValidationError("SQL phải có nội dung và không vượt quá 1 MB.")
        columns = self._columns_by_table(list(tables))
        return preview_sql(sql_text, target_table_id, tables, columns)

    def read_view_sql(self, connection_id: UUID, target_table_id: UUID) -> dict[str, Any]:
        tables = self._visible_tables(connection_id)
        if target_table_id not in tables:
            raise LineageNotFoundError("Không tìm thấy view trong phạm vi kết nối.")
        schema_name, table = tables[target_table_id]
        if table.table_type not in {"VIEW", "MATERIALIZED_VIEW"}:
            raise LineageValidationError("Chỉ view và materialized view có SQL định nghĩa để đọc.")
        connection = self.session.get(DatabaseConnection, connection_id)
        if not connection.is_active:
            raise InactiveConnectionError()
        try:
            uri = Fernet(config.require_connection_encryption_key().encode()).decrypt(
                connection.uri_ciphertext.encode()
            ).decode("utf-8")
            engine = create_engine(make_url(uri), poolclass=NullPool, connect_args={"connect_timeout": 5})
            try:
                with engine.connect() as source:
                    sql_text = source.scalar(text("""
                        SELECT pg_catalog.pg_get_viewdef(c.oid, true)
                        FROM pg_catalog.pg_class AS c
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE n.nspname = :schema_name AND c.relname = :table_name
                          AND c.relkind IN ('v', 'm')
                          AND pg_catalog.has_schema_privilege(current_user, n.oid, 'USAGE')
                          AND pg_catalog.has_table_privilege(current_user, c.oid, 'SELECT')
                    """), {"schema_name": schema_name, "table_name": table.name})
            finally:
                engine.dispose()
        except (InvalidToken, UnicodeError, SQLAlchemyError, OSError, TimeoutError):
            raise SourceDatabaseUnavailableError() from None
        if not sql_text:
            raise LineageNotFoundError("Không đọc được SQL định nghĩa view bằng role kết nối.")
        return {"target_table_id": target_table_id, "sql_text": sql_text}

    def _visible_tables(self, connection_id: UUID) -> dict[UUID, tuple[str, DatabaseTable]]:
        connection = self.session.get(DatabaseConnection, connection_id)
        if connection is None:
            raise LineageNotFoundError("Không tìm thấy kết nối database.")
        scope = MetadataScope(connection)
        statement = (
            select(DatabaseSchema, DatabaseTable)
            .join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(DatabaseSchema.connection_id == connection_id)
        )
        return {
            table.id: (schema.name, table)
            for schema, table in self.session.execute(statement)
            if scope.schema(schema.name) and scope.table(schema.name, table.name)
        }

    def _columns_by_table(self, table_ids: list[UUID]) -> dict[UUID, list[DatabaseColumn]]:
        columns = self.session.scalars(select(DatabaseColumn).where(DatabaseColumn.table_id.in_(table_ids))).all()
        by_table: dict[UUID, list[DatabaseColumn]] = defaultdict(list)
        for column in columns:
            by_table[column.table_id].append(column)
        return by_table

    def _check_dependencies(
        self, target_id: UUID, input_ids: set[UUID], dependencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        column_ids = {
            item["source_column_id"] for item in dependencies
        } | {item["target_column_id"] for item in dependencies if item.get("target_column_id")}
        columns = {
            column.id: column for column in self.session.scalars(
                select(DatabaseColumn).where(DatabaseColumn.id.in_(column_ids))
            )
        }
        seen: set[tuple[UUID, UUID | None, str]] = set()
        for item in dependencies:
            source = columns.get(item["source_column_id"])
            target = columns.get(item.get("target_column_id"))
            role = item["role"]
            if role not in {"value", "group", "join", "filter"}:
                raise LineageValidationError("Vai trò cột không hợp lệ.")
            key = (item["source_column_id"], item.get("target_column_id"), role)
            if source is None or source.table_id not in input_ids:
                raise LineageValidationError("Cột nguồn phải thuộc một bảng nguồn đã chọn.")
            if item.get("target_column_id") and (target is None or target.table_id != target_id):
                raise LineageValidationError("Cột đích phải thuộc bảng đích.")
            if role == "value" and target is None:
                raise LineageValidationError("Liên kết value cần cột đích.")
            if key in seen:
                raise LineageValidationError("Liên kết cột bị lặp.")
            seen.add(key)
        return dependencies

    @staticmethod
    def _out(
        row: LineageTransformation, input_ids: list[UUID], dependencies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "id": row.id, "target_table_id": row.target_table_id, "name": row.name,
            "description": row.description, "sql_text": row.sql_text, "origin": row.origin,
            "source_table_ids": input_ids, "dependencies": dependencies,
            "created_at": row.created_at, "updated_at": row.updated_at,
        }

