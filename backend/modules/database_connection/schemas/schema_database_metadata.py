from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SyncOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    last_synced_at: datetime
    schema_count: int
    table_count: int
    column_count: int


class SchemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    last_synced_at: datetime


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    table_type: str
    description: str | None
    last_synced_at: datetime


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    is_primary_key: bool
    default_value: str | None
    description: str | None
