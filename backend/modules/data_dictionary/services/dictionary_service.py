from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.modules.database_connection.models import DatabaseColumn, DatabaseTable
from backend.modules.database_connection.repositories import (
    DatabaseColumnRepository,
    DatabaseSchemaRepository,
    DatabaseTableRepository,
)

from ..models import (
    ColumnAggregation,
    ColumnDictionary,
    ColumnSynonym,
    IndicatorAggregation,
    TableColumnRole,
    TableDictionary,
    TableTimeGrain,
)
from ..repositories import (
    ColumnAggregationRepository,
    ColumnDictionaryRepository,
    ColumnSynonymRepository,
    IndicatorAggregationRepository,
    TableColumnRoleRepository,
    TableDictionaryRepository,
    TableTimeGrainRepository,
)
from ..utils.exceptions import (
    DataDictionaryValidationError,
    DictionaryTableNotFoundError,
)
from . import semantics


def _text(value: str | None, field: str, max_length: int) -> str | None:
    if value is None or not value.strip():
        return None
    if len(value.strip()) > max_length:
        raise DataDictionaryValidationError(f"{field} tối đa {max_length} ký tự.")
    return value.strip()


def _required_text(value: str, field: str, max_length: int) -> str:
    text = _text(value, field, max_length)
    if text is None:
        raise DataDictionaryValidationError(f"{field} không được để trống.")
    return text


def _choice(value: str | None, field: str, choices: tuple[str, ...]) -> str | None:
    if value is not None and value not in choices:
        raise DataDictionaryValidationError(f"{field} phải là một trong: {', '.join(choices)}.")
    return value


class DataDictionaryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.schemas = DatabaseSchemaRepository(session)
        self.tables = DatabaseTableRepository(session)
        self.columns = DatabaseColumnRepository(session)
        self.table_dictionaries = TableDictionaryRepository(session)
        self.column_roles = TableColumnRoleRepository(session)
        self.time_grains = TableTimeGrainRepository(session)
        self.indicator_aggregations = IndicatorAggregationRepository(session)
        self.column_dictionaries = ColumnDictionaryRepository(session)
        self.column_aggregations = ColumnAggregationRepository(session)
        self.column_synonyms = ColumnSynonymRepository(session)

    def get_table_dictionary(self, table_id: UUID) -> dict[str, Any]:
        return self._describe(self._table(table_id))

    def save_table_dictionary(self, table_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        table = self._table(table_id)
        columns_by_id = {column.id: column for column in self.columns.read_by_table_id(table.id)}
        layout = _choice(values.get("layout", "wide"), "layout", semantics.LAYOUTS) or "wide"
        roles = self._checked_roles(values.get("column_roles", []), layout, columns_by_id)
        has_row_kind = any(role["role"] == "row_kind" for role in roles)
        grains = self._checked_time_grains(values.get("time_grains", []), has_row_kind)
        aggregations = self._checked_indicator_aggregations(values.get("indicator_aggregations", []), layout, roles)
        fields = {
            "display_name": _required_text(values["display_name"], "display_name", 255),
            "description": _text(values.get("description"), "description", semantics.MAX_DESCRIPTION_LENGTH),
            "grain_description": _text(
                values.get("grain_description"), "grain_description", semantics.MAX_DESCRIPTION_LENGTH
            ),
            "table_kind": _choice(values.get("table_kind"), "table_kind", semantics.TABLE_KINDS),
            "layout": layout,
            "contains_pii": bool(values.get("contains_pii", False)),
        }

        dictionary = self.table_dictionaries.read_by_table_id(table.id)
        fields["indicator_catalog_id"] = self._checked_catalog(
            table, layout, values.get("indicator_catalog_table_id"), dictionary
        )
        if dictionary is None:
            dictionary = self.table_dictionaries.create(TableDictionary(table_id=table.id, **fields))
        else:
            if dictionary.layout == "indicator_catalog" and layout != "indicator_catalog":
                self.table_dictionaries.clear_catalog_references(dictionary.id)
            self.table_dictionaries.update(dictionary, fields)

        self.column_roles.delete_by_parent_id(dictionary.id)
        self.time_grains.delete_by_parent_id(dictionary.id)
        self.indicator_aggregations.delete_by_parent_id(dictionary.id)
        self.column_roles.create_many(TableColumnRole(table_dictionary_id=dictionary.id, **role) for role in roles)
        self.time_grains.create_many(TableTimeGrain(table_dictionary_id=dictionary.id, **grain) for grain in grains)
        self.indicator_aggregations.create_many(
            IndicatorAggregation(table_dictionary_id=dictionary.id, **item) for item in aggregations
        )
        return self._describe(table)

    def save_column_dictionaries(self, table_id: UUID, items: list[dict[str, Any]]) -> dict[str, Any]:
        table = self._table(table_id)
        connection_id = self._connection_id(table)
        columns_by_id = {column.id: column for column in self.columns.read_by_table_id(table.id)}
        table_dictionary = self.table_dictionaries.read_by_table_id(table.id)
        row_kind_ids = self._row_kind_column_ids(table_dictionary)
        referenced = self._columns_in_connection(
            {item["referenced_column_id"] for item in items if item.get("referenced_column_id")}, connection_id
        )
        stored = {entry.column_id: entry for entry in self.column_dictionaries.read_by_column_ids(columns_by_id)}

        checked = []
        seen: set[UUID] = set()
        for index, item in enumerate(items):
            column = columns_by_id.get(item["column_id"])
            if column is None:
                raise DataDictionaryValidationError(f"columns[{index}].column_id không thuộc bảng này.")
            if column.id in seen:
                raise DataDictionaryValidationError(f"columns[{index}].column_id bị lặp.")
            seen.add(column.id)
            checked.append(self._checked_column(index, item, column, row_kind_ids, referenced))

        for column, fields, aggregations, synonyms in checked:
            entry = stored.get(column.id)
            if entry is None:
                entry = self.column_dictionaries.create(ColumnDictionary(column_id=column.id, **fields))
            else:
                self.column_dictionaries.update(entry, fields)
                self.column_aggregations.delete_by_parent_id(entry.id)
                self.column_synonyms.delete_by_parent_id(entry.id)
            self.column_aggregations.create_many(
                ColumnAggregation(column_dictionary_id=entry.id, aggregation=value) for value in aggregations
            )
            self.column_synonyms.create_many(
                ColumnSynonym(column_dictionary_id=entry.id, synonym=value) for value in synonyms
            )
        return self._describe(table)

    def _table(self, table_id: UUID) -> DatabaseTable:
        table = self.tables.read_by_id(table_id)
        if table is None:
            raise DictionaryTableNotFoundError()
        return table

    def _connection_id(self, table: DatabaseTable) -> UUID:
        return self.schemas.read_by_id(table.schema_id).connection_id

    def _row_kind_column_ids(self, dictionary: TableDictionary | None) -> set[UUID]:
        if dictionary is None:
            return set()
        roles = self.column_roles.read_by_parent_ids([dictionary.id])
        return {role.column_id for role in roles if role.role == "row_kind"}

    def _columns_in_connection(self, column_ids: set[UUID], connection_id: UUID) -> dict[UUID, DatabaseColumn]:
        columns = self.columns.read_by_ids(column_ids)
        tables = {table.id: table for table in self.tables.read_by_ids({column.table_id for column in columns})}
        schemas = {schema.id: schema for schema in self.schemas.read_by_ids({t.schema_id for t in tables.values()})}
        found = {
            column.id: column for column in columns
            if schemas[tables[column.table_id].schema_id].connection_id == connection_id
        }
        if missing := column_ids - found.keys():
            raise DataDictionaryValidationError(
                f"Cột tham chiếu {next(iter(missing))} không tồn tại trong cùng kết nối database."
            )
        return found

    def _checked_roles(
        self, items: list[dict[str, Any]], layout: str, columns_by_id: dict[UUID, DatabaseColumn],
    ) -> list[dict[str, Any]]:
        allowed = semantics.LAYOUT_ROLES[layout]
        roles = []
        seen: set[tuple[str, str | None]] = set()
        for index, item in enumerate(items):
            role, qualifier, column_id = item["role"], item.get("qualifier"), item["column_id"]
            if role not in allowed:
                raise DataDictionaryValidationError(
                    f"column_roles[{index}].role với layout {layout} phải là một trong: {', '.join(allowed)}."
                )
            if role == "value":
                _choice(qualifier, f"column_roles[{index}].qualifier", semantics.VALUE_KINDS)
                if qualifier is None:
                    raise DataDictionaryValidationError(f"column_roles[{index}].qualifier cần kiểu giá trị.")
            elif qualifier is not None:
                raise DataDictionaryValidationError(f"column_roles[{index}].qualifier chỉ dùng với vai trò value.")
            if column_id not in columns_by_id:
                raise DataDictionaryValidationError(f"column_roles[{index}].column_id không thuộc bảng này.")
            if (role, qualifier) in seen:
                raise DataDictionaryValidationError(f"column_roles[{index}] gán trùng vai trò {role}.")
            seen.add((role, qualifier))
            roles.append({"role": role, "qualifier": qualifier, "column_id": column_id})

        assigned = {role["role"] for role in roles}
        if missing := [role for role in semantics.REQUIRED_ROLES[layout] if role not in assigned]:
            raise DataDictionaryValidationError(f"Layout {layout} cần các vai trò: {', '.join(missing)}.")
        indicator_columns = {role["column_id"] for role in roles if role["role"] == "indicator_key"}
        if any(role["role"] == "value" and role["column_id"] in indicator_columns for role in roles):
            raise DataDictionaryValidationError("Cột chỉ số không thể đồng thời là cột giá trị.")
        return roles

    def _checked_time_grains(self, items: list[dict[str, Any]], has_row_kind: bool) -> list[dict[str, Any]]:
        grains = []
        seen: set[str | None] = set()
        for index, item in enumerate(items):
            row_kind_value = _text(item.get("row_kind_value"), f"time_grains[{index}].row_kind_value", 255)
            if has_row_kind and row_kind_value is None:
                raise DataDictionaryValidationError(f"time_grains[{index}].row_kind_value không được để trống.")
            if not has_row_kind and row_kind_value is not None:
                raise DataDictionaryValidationError(
                    f"time_grains[{index}].row_kind_value cần một cột có vai trò row_kind."
                )
            if row_kind_value in seen:
                raise DataDictionaryValidationError(f"time_grains[{index}] bị lặp loại dòng.")
            seen.add(row_kind_value)
            grains.append({
                "row_kind_value": row_kind_value,
                "label": _text(item.get("label"), f"time_grains[{index}].label", 255),
                "time_grain": _choice(item["time_grain"], f"time_grains[{index}].time_grain", semantics.TIME_GRAINS),
            })
        return grains

    def _checked_indicator_aggregations(
        self, items: list[dict[str, Any]], layout: str, roles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not items:
            return []
        if layout != "indicator_catalog" or not any(role["role"] == "catalog_aggregation" for role in roles):
            raise DataDictionaryValidationError(
                "indicator_aggregations chỉ dùng cho bảng danh mục chỉ số có cột vai trò catalog_aggregation."
            )
        if len(items) > semantics.MAX_INDICATOR_CODES:
            raise DataDictionaryValidationError(
                f"indicator_aggregations tối đa {semantics.MAX_INDICATOR_CODES} mã."
            )
        checked = []
        seen: set[str] = set()
        for index, item in enumerate(items):
            source_code = _required_text(item["source_code"], f"indicator_aggregations[{index}].source_code", 64)
            if source_code in seen:
                raise DataDictionaryValidationError(f"indicator_aggregations[{index}].source_code bị lặp.")
            seen.add(source_code)
            aggregation = _choice(
                item["aggregation"], f"indicator_aggregations[{index}].aggregation", semantics.INDICATOR_AGGREGATIONS
            )
            checked.append({"source_code": source_code, "aggregation": aggregation})
        return checked

    def _checked_catalog(
        self, table: DatabaseTable, layout: str, catalog_table_id: UUID | None, dictionary: TableDictionary | None,
    ) -> UUID | None:
        if catalog_table_id is None:
            return None
        if layout != "indicator_values":
            raise DataDictionaryValidationError("indicator_catalog_table_id chỉ dùng cho layout indicator_values.")
        if catalog_table_id == table.id:
            raise DataDictionaryValidationError("Bảng không thể là danh mục chỉ số của chính nó.")
        catalog_table = self.tables.read_by_id(catalog_table_id)
        catalog = self.table_dictionaries.read_by_table_id(catalog_table_id) if catalog_table else None
        if (
            catalog is None
            or catalog.layout != "indicator_catalog"
            or self._connection_id(catalog_table) != self._connection_id(table)
        ):
            raise DataDictionaryValidationError(
                "indicator_catalog_table_id phải là bảng cùng kết nối đã được mô tả với layout indicator_catalog."
            )
        return catalog.id

    def _checked_column(
        self,
        index: int,
        item: dict[str, Any],
        column: DatabaseColumn,
        row_kind_ids: set[UUID],
        referenced: dict[UUID, DatabaseColumn],
    ) -> tuple[DatabaseColumn, dict[str, Any], list[str], list[str]]:
        prefix = f"columns[{index}]"
        temporal_kind = _choice(item.get("temporal_kind"), f"{prefix}.temporal_kind", semantics.TEMPORAL_KINDS)
        semantic_role = _choice(item.get("semantic_role"), f"{prefix}.semantic_role", semantics.SEMANTIC_ROLES)
        is_primary_key = item.get("is_primary_key")
        referenced_column_id = item.get("referenced_column_id")
        effective_role = semantic_role or semantics.default_semantic_role(
            column.data_type,
            temporal_kind,
            is_key=self._is_key(column, is_primary_key, referenced_column_id),
            is_row_kind=column.id in row_kind_ids,
        )
        if referenced_column_id == column.id:
            raise DataDictionaryValidationError(f"{prefix}.referenced_column_id không được trỏ vào chính cột đó.")

        aggregations = list(dict.fromkeys(item.get("aggregations", [])))
        for value in aggregations:
            _choice(value, f"{prefix}.aggregations", semantics.COLUMN_AGGREGATIONS)
        if aggregations and effective_role != "measure":
            raise DataDictionaryValidationError(f"{prefix}.aggregations chỉ dùng cho cột có vai trò measure.")

        fields = {
            "display_name": _required_text(item["display_name"], f"{prefix}.display_name", 255),
            "description": _text(item.get("description"), f"{prefix}.description", semantics.MAX_DESCRIPTION_LENGTH),
            "business_term": _text(
                item.get("business_term"), f"{prefix}.business_term", semantics.MAX_DESCRIPTION_LENGTH
            ),
            "semantic_role": semantic_role,
            "temporal_kind": temporal_kind,
            "unit": _text(item.get("unit"), f"{prefix}.unit", 128),
            "format": _text(item.get("format"), f"{prefix}.format", 128),
            "is_primary_key": is_primary_key,
            "is_unique": bool(item.get("is_unique", False)),
            "referenced_column_id": referenced_column_id if referenced_column_id in referenced else None,
            "contains_pii": bool(item.get("contains_pii", False)),
        }
        return column, fields, aggregations, self._checked_synonyms(prefix, item.get("synonyms", []))

    @staticmethod
    def _is_key(column: DatabaseColumn, is_primary_key: bool | None, referenced_column_id: UUID | None) -> bool:
        if is_primary_key is not None:
            return is_primary_key or referenced_column_id is not None
        return column.is_primary_key or referenced_column_id is not None or semantics.looks_like_key(column.name)

    @staticmethod
    def _checked_synonyms(prefix: str, values: Iterable[str]) -> list[str]:
        synonyms: dict[str, str] = {}
        for value in values:
            synonym = _text(value, f"{prefix}.synonyms", semantics.MAX_SYNONYM_LENGTH)
            if synonym is not None:
                synonyms.setdefault(synonym.casefold(), synonym)
        if len(synonyms) > semantics.MAX_SYNONYMS:
            raise DataDictionaryValidationError(f"{prefix}.synonyms tối đa {semantics.MAX_SYNONYMS} từ.")
        return list(synonyms.values())

    def _describe(self, table: DatabaseTable) -> dict[str, Any]:
        schema = self.schemas.read_by_id(table.schema_id)
        columns = self.columns.read_by_table_id(table.id)
        column_names = {column.id: column.name for column in columns}
        dictionary = self.table_dictionaries.read_by_table_id(table.id)
        dictionary_ids = [dictionary.id] if dictionary else []
        roles = self.column_roles.read_by_parent_ids(dictionary_ids)
        row_kind_ids = {role.column_id for role in roles if role.role == "row_kind"}

        entries = {entry.column_id: entry for entry in self.column_dictionaries.read_by_column_ids(column_names)}
        aggregations: dict[UUID, list[str]] = defaultdict(list)
        for row in self.column_aggregations.read_by_parent_ids(entry.id for entry in entries.values()):
            aggregations[row.column_dictionary_id].append(row.aggregation)
        synonyms: dict[UUID, list[str]] = defaultdict(list)
        for row in self.column_synonyms.read_by_parent_ids(entry.id for entry in entries.values()):
            synonyms[row.column_dictionary_id].append(row.synonym)
        references = self._column_labels(
            {entry.referenced_column_id for entry in entries.values() if entry.referenced_column_id}
        )

        catalog = None
        if dictionary and dictionary.indicator_catalog_id:
            catalog_dictionary = self.table_dictionaries.read_by_id(dictionary.indicator_catalog_id)
            catalog_table = self.tables.read_by_id(catalog_dictionary.table_id)
            catalog = {
                "table_id": catalog_table.id,
                "schema_name": self.schemas.read_by_id(catalog_table.schema_id).name,
                "table_name": catalog_table.name,
                "display_name": catalog_dictionary.display_name,
            }

        return {
            "table_id": table.id,
            "connection_id": schema.connection_id,
            "schema_name": schema.name,
            "table_name": table.name,
            "table_type": table.table_type,
            "is_saved": dictionary is not None,
            "display_name": dictionary.display_name if dictionary else table.name,
            "description": dictionary.description if dictionary else table.description,
            "grain_description": dictionary.grain_description if dictionary else None,
            "table_kind": dictionary.table_kind if dictionary else None,
            "layout": dictionary.layout if dictionary else "wide",
            "indicator_catalog": catalog,
            "contains_pii": dictionary.contains_pii if dictionary else False,
            "updated_at": dictionary.updated_at if dictionary else None,
            "column_roles": [
                {
                    "role": role.role,
                    "qualifier": role.qualifier,
                    "column_id": role.column_id,
                    "column_name": column_names.get(role.column_id),
                }
                for role in roles
            ],
            "time_grains": [
                {"row_kind_value": grain.row_kind_value, "label": grain.label, "time_grain": grain.time_grain}
                for grain in self.time_grains.read_by_parent_ids(dictionary_ids)
            ],
            "indicator_aggregations": [
                {"source_code": item.source_code, "aggregation": item.aggregation}
                for item in self.indicator_aggregations.read_by_parent_ids(dictionary_ids)
            ],
            "columns": [
                self._describe_column(column, entries.get(column.id), row_kind_ids, aggregations, synonyms, references)
                for column in columns
            ],
        }

    @staticmethod
    def _describe_column(
        column: DatabaseColumn,
        entry: ColumnDictionary | None,
        row_kind_ids: set[UUID],
        aggregations: dict[UUID, list[str]],
        synonyms: dict[UUID, list[str]],
        references: dict[UUID, dict[str, Any]],
    ) -> dict[str, Any]:
        temporal_kind = entry.temporal_kind if entry else semantics.default_temporal_kind(column.data_type)
        is_key = DataDictionaryService._is_key(
            column, entry.is_primary_key if entry else None, entry.referenced_column_id if entry else None
        )
        semantic_role = (entry.semantic_role if entry else None) or semantics.default_semantic_role(
            column.data_type, temporal_kind, is_key=is_key, is_row_kind=column.id in row_kind_ids
        )
        return {
            "column_id": column.id,
            "name": column.name,
            "data_type": column.data_type,
            "ordinal_position": column.ordinal_position,
            "is_nullable": column.is_nullable,
            "source_is_primary_key": column.is_primary_key,
            "default_value": column.default_value,
            "is_saved": entry is not None,
            "display_name": entry.display_name if entry else column.name,
            "description": entry.description if entry else column.description,
            "business_term": entry.business_term if entry else None,
            "semantic_role": semantic_role,
            "temporal_kind": temporal_kind,
            "unit": entry.unit if entry else None,
            "format": entry.format if entry else None,
            "is_primary_key": entry.is_primary_key if entry else None,
            "is_unique": entry.is_unique if entry else False,
            "referenced_column": references.get(entry.referenced_column_id) if entry else None,
            "contains_pii": entry.contains_pii if entry else False,
            "aggregations": aggregations.get(entry.id, []) if entry else [],
            "synonyms": synonyms.get(entry.id, []) if entry else [],
            "updated_at": entry.updated_at if entry else None,
        }

    def _column_labels(self, column_ids: set[UUID]) -> dict[UUID, dict[str, Any]]:
        columns = self.columns.read_by_ids(column_ids)
        tables = {table.id: table for table in self.tables.read_by_ids({column.table_id for column in columns})}
        schemas = {schema.id: schema for schema in self.schemas.read_by_ids({t.schema_id for t in tables.values()})}
        return {
            column.id: {
                "column_id": column.id,
                "table_id": column.table_id,
                "schema_name": schemas[tables[column.table_id].schema_id].name,
                "table_name": tables[column.table_id].name,
                "column_name": column.name,
            }
            for column in columns
        }
