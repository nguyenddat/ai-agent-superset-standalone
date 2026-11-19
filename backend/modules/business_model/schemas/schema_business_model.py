from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LayerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=16)
    level: int = Field(default=0, ge=0)
    sort_order: int = Field(default=0, ge=0)


class LayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    color: str | None
    level: int
    sort_order: int


class LayerOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    levels: list[list[UUID]] = Field(max_length=100)


class DomainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=16)
    table_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class DomainOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    color: str | None
    table_ids: list[UUID]


class DomainRef(BaseModel):
    id: UUID
    name: str
    color: str | None


class TableLayerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer_id: UUID | None


class TableLayerOut(BaseModel):
    table_id: UUID
    layer_id: UUID | None


class ModelTableOut(BaseModel):
    table_id: UUID
    schema_name: str
    table_name: str
    table_type: str
    display_name: str
    table_kind: str | None
    layer_id: UUID | None
    is_saved: bool


class CanvasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: dict[str, Any]


class CanvasOut(BaseModel):
    connection_id: UUID
    view: Literal["business", "lineage"]
    layout: dict[str, Any]


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_table_id: UUID
    target_table_id: UUID
    kind: Literal["flow", "relation"]
    label: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)
    is_hidden: bool = False
    is_manual: bool = True


class EdgeOut(BaseModel):
    id: UUID | None
    source_table_id: UUID
    target_table_id: UUID
    kind: Literal["flow", "relation"]
    origin: Literal["dictionary", "manual", "override"]
    label: str | None
    color: str | None


class BusinessModelOut(BaseModel):
    connection_id: UUID
    layers: list[LayerOut]
    domains: list[DomainOut]
    tables: list[ModelTableOut]
    business_canvas: dict[str, Any]
    lineage_canvas: dict[str, Any]
    lineage_edges: list[EdgeOut]
