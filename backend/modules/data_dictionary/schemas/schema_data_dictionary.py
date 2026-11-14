from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ColumnRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(max_length=32)
    qualifier: str | None = Field(default=None, max_length=32)
    column_id: UUID


class TimeGrainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_kind_value: str | None = Field(default=None, max_length=255)
    label: str | None = Field(default=None, max_length=255)
    time_grain: str = Field(max_length=16)


class IndicatorAggregationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(min_length=1, max_length=64)
    aggregation: str = Field(max_length=16)


class TableDictionaryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    grain_description: str | None = None
    table_kind: str | None = Field(default=None, max_length=32)
    layout: str = Field(default="wide", max_length=32)
    indicator_catalog_table_id: UUID | None = None
    contains_pii: bool = False
    column_roles: list[ColumnRoleIn] = Field(default_factory=list, max_length=50)
    time_grains: list[TimeGrainIn] = Field(default_factory=list, max_length=50)
    indicator_aggregations: list[IndicatorAggregationIn] = Field(default_factory=list, max_length=50)


class ColumnDictionaryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    business_term: str | None = None
    semantic_role: str | None = Field(default=None, max_length=16)
    temporal_kind: str | None = Field(default=None, max_length=16)
    unit: str | None = Field(default=None, max_length=128)
    format: str | None = Field(default=None, max_length=128)
    is_primary_key: bool | None = None
    is_unique: bool = False
    referenced_column_id: UUID | None = None
    contains_pii: bool = False
    aggregations: list[str] = Field(default_factory=list, max_length=10)
    synonyms: list[str] = Field(default_factory=list, max_length=50)


class ColumnDictionariesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[ColumnDictionaryIn] = Field(max_length=1000)


class ColumnRoleOut(BaseModel):
    role: str
    qualifier: str | None
    column_id: UUID
    column_name: str | None


class TimeGrainOut(BaseModel):
    row_kind_value: str | None
    label: str | None
    time_grain: str


class IndicatorAggregationOut(BaseModel):
    source_code: str
    aggregation: str


class IndicatorCatalogOut(BaseModel):
    table_id: UUID
    schema_name: str
    table_name: str
    display_name: str


class ReferencedColumnOut(BaseModel):
    column_id: UUID
    table_id: UUID
    schema_name: str
    table_name: str
    column_name: str


class ColumnDictionaryOut(BaseModel):
    column_id: UUID
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    source_is_primary_key: bool
    default_value: str | None
    is_saved: bool
    display_name: str
    description: str | None
    business_term: str | None
    semantic_role: str
    semantic_role_is_default: bool
    temporal_kind: str | None
    unit: str | None
    format: str | None
    is_primary_key: bool | None
    is_unique: bool
    referenced_column: ReferencedColumnOut | None
    contains_pii: bool
    aggregations: list[str]
    synonyms: list[str]
    updated_at: datetime | None


class TableDictionaryOut(BaseModel):
    table_id: UUID
    connection_id: UUID
    schema_name: str
    table_name: str
    table_type: str
    is_saved: bool
    display_name: str
    description: str | None
    grain_description: str | None
    table_kind: str | None
    layout: str
    indicator_catalog: IndicatorCatalogOut | None
    contains_pii: bool
    updated_at: datetime | None
    column_roles: list[ColumnRoleOut]
    time_grains: list[TimeGrainOut]
    indicator_aggregations: list[IndicatorAggregationOut]
    columns: list[ColumnDictionaryOut]


class DictionaryTableSummaryOut(BaseModel):
    table_id: UUID
    table_name: str
    table_type: str
    is_saved: bool
    display_name: str
    layout: str
    column_count: int
    described_column_count: int


class DictionarySchemaSummaryOut(BaseModel):
    schema_id: UUID
    schema_name: str
    tables: list[DictionaryTableSummaryOut]


class DictionarySummaryOut(BaseModel):
    connection_id: UUID
    table_count: int
    described_table_count: int
    schemas: list[DictionarySchemaSummaryOut]


class DictionaryStatsSchemaOut(BaseModel):
    schema_id: UUID
    schema_name: str
    table_count: int
    described_table_count: int


class DictionaryStatsTableOut(BaseModel):
    table_id: UUID
    schema_name: str
    table_name: str
    display_name: str
    is_saved: bool


class DictionaryColumnRankOut(DictionaryStatsTableOut):
    column_count: int
    described_column_count: int


class DictionaryReferenceRankOut(DictionaryStatsTableOut):
    referencing_table_count: int


class DictionaryStatsOut(BaseModel):
    connection_id: UUID
    table_count: int
    described_table_count: int
    column_count: int
    described_column_count: int
    schemas: list[DictionaryStatsSchemaOut]
    most_columns: list[DictionaryColumnRankOut]
    most_referenced: list[DictionaryReferenceRankOut]
