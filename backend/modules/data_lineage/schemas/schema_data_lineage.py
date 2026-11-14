from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ColumnDependencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_column_id: UUID
    target_column_id: UUID | None = None
    role: Literal["value", "group", "join", "filter"]


class TransformationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_table_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sql_text: str | None = None
    origin: Literal["manual", "sql_job", "view_sql"] = "manual"
    source_table_ids: list[UUID] = Field(min_length=1, max_length=500)
    dependencies: list[ColumnDependencyIn] = Field(default_factory=list, max_length=5000)


class TransformationOut(TransformationIn):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_table_id: UUID
    sql_text: str = Field(min_length=1)


class PreviewOut(BaseModel):
    target_table_id: UUID
    source_table_ids: list[UUID]
    dependencies: list[ColumnDependencyIn]
    warnings: list[str]
    complete: bool


class ViewSqlOut(BaseModel):
    target_table_id: UUID
    sql_text: str


class GraphEdgeOut(BaseModel):
    transformation_id: UUID | None
    source_table_id: UUID
    target_table_id: UUID
    kind: Literal["transform", "flow"]
    origin: Literal["manual", "sql_job", "view_sql", "manual_edge"]
    dependencies: list[ColumnDependencyIn]


class GraphOut(BaseModel):
    connection_id: UUID
    edges: list[GraphEdgeOut]
