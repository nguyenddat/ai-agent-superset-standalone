from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MetricIn(BaseModel):
    table_id: UUID
    name: str = Field(min_length=1, max_length=255)
    expression: str = Field(min_length=1, max_length=10000)
    label: str | None = Field(default=None, max_length=255)
    description: str | None = None
    format: str | None = Field(default=None, max_length=128)
    currency: str | None = Field(default=None, max_length=16)
    metric_type: str | None = Field(default=None, max_length=64)
    warning_text: str | None = None


class MetricPatch(BaseModel):
    table_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    expression: str | None = Field(default=None, min_length=1, max_length=10000)
    label: str | None = Field(default=None, max_length=255)
    description: str | None = None
    format: str | None = Field(default=None, max_length=128)
    currency: str | None = Field(default=None, max_length=16)
    metric_type: str | None = Field(default=None, max_length=64)
    warning_text: str | None = None


class MetricOut(BaseModel):
    id: UUID
    origin: str
    name: str
    label: str | None
    expression: str
    description: str | None
    format: str | None
    currency: str | None
    metric_type: str | None
    warning_text: str | None
    is_active: bool
    table_id: UUID | None
    source_url: str | None
    source_metric_id: int | None
    source_dataset_id: int | None
    source_database_id: UUID | None
    source_user_id: UUID | None
    source_dataset_owner_id: UUID | None
    source_schema: str | None
    source_table: str | None
    source_sql: str | None
    created_at: datetime
    updated_at: datetime


class SupersetDatabaseOut(BaseModel):
    id: UUID
    source_url: str
    source_id: int
    name: str
    backend: str | None
    connection_id: UUID | None


class SupersetUserOut(BaseModel):
    id: UUID
    source_url: str
    source_id: int
    username: str
    first_name: str | None
    last_name: str | None
    email: str | None


class LinkDatabaseIn(BaseModel):
    connection_id: UUID | None


class SyncOut(BaseModel):
    users: int
    databases: int
    metrics: int
    deactivated: int
