import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.modules.data_dictionary.models import TableDictionary
from backend.modules.data_dictionary.repositories import (
    ColumnDictionaryRepository,
    TableDictionaryRepository,
)
from backend.modules.database_connection.models import DatabaseTable
from backend.modules.database_connection.repositories import (
    DatabaseConnectionRepository,
    DatabaseSchemaRepository,
    DatabaseTableRepository,
)
from backend.modules.database_connection.services.metadata_scope import MetadataScope

from ..models import (
    BusinessCanvas,
    BusinessDomain,
    DataLayer,
    LineageCanvas,
    LineageEdge,
)
from ..repositories import (
    BusinessCanvasRepository,
    BusinessDomainRepository,
    DataLayerRepository,
    LineageCanvasRepository,
    LineageEdgeRepository,
)
from ..utils.exceptions import (
    BusinessModelConflictError,
    BusinessModelNotFoundError,
    BusinessModelValidationError,
)

MAX_LAYOUT_BYTES = 1_000_000
EDGE_KINDS = {"flow", "relation"}
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _name(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > 255:
        raise BusinessModelValidationError("Tên phải có từ 1 đến 255 ký tự.")
    return clean


def _description(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _color(value: str | None) -> str | None:
    if value is not None and not COLOR_PATTERN.fullmatch(value):
        raise BusinessModelValidationError("Màu phải có dạng #RRGGBB.")
    return value


class BusinessModelService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.connections = DatabaseConnectionRepository(session)
        self.schemas = DatabaseSchemaRepository(session)
        self.tables = DatabaseTableRepository(session)
        self.dictionaries = TableDictionaryRepository(session)
        self.column_dictionaries = ColumnDictionaryRepository(session)
        self.layers = DataLayerRepository(session)
        self.domains = BusinessDomainRepository(session)
        self.business_canvases = BusinessCanvasRepository(session)
        self.lineage_canvases = LineageCanvasRepository(session)
        self.edges = LineageEdgeRepository(session)

    def list_layers(self) -> list[DataLayer]:
        return self.layers.read_ordered()

    def create_layer(self, values: dict[str, Any]) -> DataLayer:
        name = _name(values["name"])
        if self.layers.read_by_name(name):
            raise BusinessModelConflictError()
        layer = DataLayer(
            name=name, description=_description(values.get("description")), color=_color(values.get("color")),
            level=values.get("level", 0), sort_order=values.get("sort_order", 0),
        )
        try:
            return self.layers.create(layer)
        except IntegrityError:
            raise BusinessModelConflictError() from None

    def update_layer(self, layer_id: UUID, values: dict[str, Any]) -> DataLayer:
        layer = self._layer(layer_id)
        name = _name(values["name"])
        other = self.layers.read_by_name(name)
        if other is not None and other.id != layer_id:
            raise BusinessModelConflictError()
        try:
            return self.layers.update(layer, {
                "name": name, "description": _description(values.get("description")),
                "color": _color(values.get("color")), "level": values.get("level", 0),
                "sort_order": values.get("sort_order", 0),
            })
        except IntegrityError:
            raise BusinessModelConflictError() from None

    def delete_layer(self, layer_id: UUID) -> None:
        self.layers.delete(self._layer(layer_id))

    def reorder_layers(self, levels: list[list[UUID]]) -> list[DataLayer]:
        layers = self.layers.read_ordered()
        ordered = [layer_id for level in levels for layer_id in level]
        if len(ordered) != len(set(ordered)) or set(ordered) != {layer.id for layer in layers}:
            raise BusinessModelValidationError("Danh sách sắp xếp phải chứa mỗi tầng đúng một lần.")
        by_id = {layer.id: layer for layer in layers}
        for level_index, level in enumerate(levels):
            for sort_order, layer_id in enumerate(level):
                layer = by_id[layer_id]
                layer.level = level_index
                layer.sort_order = sort_order
        self.session.flush()
        return self.layers.read_ordered()

    def list_domains(self) -> list[dict[str, Any]]:
        memberships = self.domains.memberships()
        return [self._domain_out(domain, memberships) for domain in self.domains.read_ordered()]

    def create_domain(self, values: dict[str, Any]) -> dict[str, Any]:
        name = _name(values["name"])
        if self.domains.read_by_name(name):
            raise BusinessModelConflictError()
        dictionary_ids = self._dictionary_ids(values.get("table_ids", []))
        domain = BusinessDomain(
            name=name, description=_description(values.get("description")), color=_color(values.get("color"))
        )
        try:
            self.domains.create(domain)
        except IntegrityError:
            raise BusinessModelConflictError() from None
        self.domains.replace_memberships(domain.id, dictionary_ids)
        return self._domain_out(domain, {domain.id: values.get("table_ids", [])})

    def update_domain(self, domain_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        domain = self._domain(domain_id)
        name = _name(values["name"])
        other = self.domains.read_by_name(name)
        if other is not None and other.id != domain_id:
            raise BusinessModelConflictError()
        dictionary_ids = self._dictionary_ids(values.get("table_ids", []))
        try:
            self.domains.update(domain, {
                "name": name,
                "description": _description(values.get("description")),
                "color": _color(values.get("color")),
            })
        except IntegrityError:
            raise BusinessModelConflictError() from None
        self.domains.replace_memberships(domain.id, dictionary_ids)
        return self._domain_out(domain, {domain.id: values.get("table_ids", [])})

    def delete_domain(self, domain_id: UUID) -> None:
        self.domains.delete(self._domain(domain_id))

    def assign_layer(self, table_id: UUID, layer_id: UUID | None) -> dict[str, Any]:
        if layer_id is not None:
            self._layer(layer_id)
        dictionary = self._ensure_dictionary(table_id)
        dictionary.layer_id = layer_id
        self.session.flush()
        return {"table_id": table_id, "layer_id": layer_id}

    def get_model(self, connection_id: UUID) -> dict[str, Any]:
        table_rows = self._connection_tables(connection_id)
        table_ids = [table.id for _, table in table_rows]
        dictionaries = {row.table_id: row for row in self.dictionaries.read_by_table_ids(table_ids)}
        layers = self.layers.read_ordered()
        memberships = self.domains.memberships(connection_id)
        business_canvas = self.business_canvases.read_by_connection_id(connection_id)
        lineage_canvas = self.lineage_canvases.read_by_connection_id(connection_id)
        return {
            "connection_id": connection_id,
            "layers": layers,
            "domains": [self._domain_out(domain, memberships) for domain in self.domains.read_ordered()],
            "tables": [{
                "table_id": table.id, "schema_name": schema.name, "table_name": table.name,
                "table_type": table.table_type, "display_name": dictionaries[table.id].display_name
                if table.id in dictionaries else table.name,
                "table_kind": dictionaries[table.id].table_kind if table.id in dictionaries else None,
                "layer_id": dictionaries[table.id].layer_id if table.id in dictionaries else None,
                "is_saved": table.id in dictionaries,
            } for schema, table in table_rows],
            "business_canvas": json.loads(business_canvas.layout) if business_canvas else {},
            "lineage_canvas": json.loads(lineage_canvas.layout) if lineage_canvas else {},
            "lineage_edges": self._visible_edges(table_ids, dictionaries),
        }

    def save_canvas(self, connection_id: UUID, view: str, layout: dict[str, Any]) -> dict[str, Any]:
        self._connection(connection_id)
        if view not in {"business", "lineage"}:
            raise BusinessModelValidationError("Loại canvas không hợp lệ.")
        try:
            serialized = json.dumps(layout, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise BusinessModelValidationError("Bố cục canvas phải là JSON hợp lệ.") from None
        if len(serialized.encode("utf-8")) > MAX_LAYOUT_BYTES:
            raise BusinessModelValidationError("Bố cục canvas vượt quá 1 MB.")
        repository = self.business_canvases if view == "business" else self.lineage_canvases
        canvas = repository.read_by_connection_id(connection_id)
        if canvas is None:
            model = BusinessCanvas if view == "business" else LineageCanvas
            repository.create(model(connection_id=connection_id, layout=serialized))
        else:
            repository.update(canvas, {"layout": serialized})
        return {"connection_id": connection_id, "view": view, "layout": layout}

    def save_edge(self, connection_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        table_rows = self._connection_tables(connection_id)
        valid_table_ids = {table.id for _, table in table_rows}
        source_table_id = values["source_table_id"]
        target_table_id = values["target_table_id"]
        kind = values["kind"]
        if source_table_id == target_table_id or {source_table_id, target_table_id} - valid_table_ids:
            raise BusinessModelValidationError("Hai bảng của cạnh phải khác nhau và thuộc cùng kết nối.")
        if kind not in EDGE_KINDS:
            raise BusinessModelValidationError("Loại cạnh phải là flow hoặc relation.")
        color = _color(values.get("color"))
        label = _description(values.get("label"))
        if label and len(label) > 32:
            raise BusinessModelValidationError("Nhãn cạnh dài tối đa 32 ký tự.")
        source = self._ensure_dictionary(source_table_id)
        target = self._ensure_dictionary(target_table_id)
        edge = self.edges.read_by_key(source.id, target.id, kind)
        fields = {
            "label": label, "color": color, "is_hidden": values.get("is_hidden", False),
            "is_manual": values.get("is_manual", True),
        }
        if edge is None:
            edge = self.edges.create(LineageEdge(
                source_table_dictionary_id=source.id, target_table_dictionary_id=target.id, kind=kind, **fields,
            ))
        else:
            self.edges.update(edge, fields)
        return self._edge_out(edge, source_table_id, target_table_id, "manual" if edge.is_manual else "override")

    def delete_edge(self, connection_id: UUID, edge_id: UUID) -> None:
        table_ids = {table.id for _, table in self._connection_tables(connection_id)}
        dictionaries = self.dictionaries.read_by_table_ids(table_ids)
        valid_dictionary_ids = {dictionary.id for dictionary in dictionaries}
        edge = self.edges.read_by_id(edge_id)
        if edge is None or edge.source_table_dictionary_id not in valid_dictionary_ids or (
            edge.target_table_dictionary_id not in valid_dictionary_ids
        ):
            raise BusinessModelNotFoundError("Không tìm thấy cạnh lineage trong kết nối này.")
        self.edges.delete(edge)

    def _visible_edges(
        self, table_ids: list[UUID], dictionaries: dict[UUID, TableDictionary],
    ) -> list[dict[str, Any]]:
        by_dictionary = {dictionary.id: dictionary.table_id for dictionary in dictionaries.values()}
        inferred: dict[tuple[UUID, UUID, str], dict[str, Any]] = {}
        for referencing_id, referenced_id in self.column_dictionaries.read_table_references(table_ids):
            source_id, target_id, kind = referencing_id, referenced_id, "relation"
            inferred[(source_id, target_id, kind)] = {
                "id": None, "source_table_id": source_id, "target_table_id": target_id,
                "kind": kind, "origin": "dictionary", "label": None, "color": None,
            }
        for edge in self.edges.read_between(by_dictionary):
            source_id = by_dictionary[edge.source_table_dictionary_id]
            target_id = by_dictionary[edge.target_table_dictionary_id]
            key = (source_id, target_id, edge.kind)
            if edge.is_hidden:
                inferred.pop(key, None)
            elif key in inferred:
                inferred[key].update(id=edge.id, label=edge.label, color=edge.color)
            elif edge.is_manual:
                inferred[key] = self._edge_out(edge, source_id, target_id, "manual")
        return sorted(
            inferred.values(),
            key=lambda item: (str(item["source_table_id"]), str(item["target_table_id"]), item["kind"]),
        )

    @staticmethod
    def _edge_out(edge: LineageEdge, source_table_id: UUID, target_table_id: UUID, origin: str) -> dict[str, Any]:
        return {
            "id": edge.id, "source_table_id": source_table_id, "target_table_id": target_table_id,
            "kind": edge.kind, "origin": origin, "label": edge.label, "color": edge.color,
        }

    @staticmethod
    def _domain_out(domain: BusinessDomain, memberships: dict[UUID, list[UUID]]) -> dict[str, Any]:
        return {
            "id": domain.id, "name": domain.name, "description": domain.description, "color": domain.color,
            "table_ids": sorted(memberships.get(domain.id, [])),
        }

    def _dictionary_ids(self, table_ids: list[UUID]) -> list[UUID]:
        if len(table_ids) != len(set(table_ids)):
            raise BusinessModelValidationError("Một bảng không được lặp trong miền nghiệp vụ.")
        tables = self.tables.read_by_ids(table_ids)
        if len(tables) != len(table_ids):
            raise BusinessModelNotFoundError("Không tìm thấy bảng đã đồng bộ.")
        dictionaries = {
            dictionary.table_id: dictionary for dictionary in self.dictionaries.read_by_table_ids(table_ids)
        }
        missing = [TableDictionary(
            table_id=table.id, display_name=table.name, description=table.description, layout="wide",
        ) for table in tables if table.id not in dictionaries]
        for dictionary in self.dictionaries.create_many(missing):
            dictionaries[dictionary.table_id] = dictionary
        return [dictionaries[table_id].id for table_id in table_ids]

    def _ensure_dictionary(self, table_id: UUID) -> TableDictionary:
        table = self.tables.read_by_id(table_id)
        if table is None:
            raise BusinessModelNotFoundError("Không tìm thấy bảng đã đồng bộ.")
        dictionary = self.dictionaries.read_by_table_id(table_id)
        if dictionary is None:
            dictionary = self.dictionaries.create(TableDictionary(
                table_id=table.id, display_name=table.name, description=table.description, layout="wide",
            ))
        return dictionary

    def _connection_tables(self, connection_id: UUID) -> list[tuple[Any, DatabaseTable]]:
        self._connection(connection_id)
        scope = MetadataScope(self.connections.read_by_id(connection_id))
        schemas = [schema for schema in self.schemas.read_by_connection_id(connection_id) if scope.schema(schema.name)]
        tables = self.tables.read_by_schema_ids([schema.id for schema in schemas])
        schema_by_id = {schema.id: schema for schema in schemas}
        return [
            (schema_by_id[table.schema_id], table) for table in tables
            if scope.table(schema_by_id[table.schema_id].name, table.name)
        ]

    def _connection(self, connection_id: UUID) -> None:
        if self.connections.read_by_id(connection_id) is None:
            raise BusinessModelNotFoundError("Không tìm thấy kết nối database.")

    def _layer(self, layer_id: UUID) -> DataLayer:
        layer = self.layers.read_by_id(layer_id)
        if layer is None:
            raise BusinessModelNotFoundError("Không tìm thấy tầng dữ liệu.")
        return layer

    def _domain(self, domain_id: UUID) -> BusinessDomain:
        domain = self.domains.read_by_id(domain_id)
        if domain is None:
            raise BusinessModelNotFoundError("Không tìm thấy miền nghiệp vụ.")
        return domain
