from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from backend.modules.data_dictionary.schemas.schema_data_dictionary import ColumnDictionaryOut, TableDictionaryOut


class TableRef(BaseModel):
    table_id: UUID
    schema_name: str
    table_name: str
    display_name: str


class NamedRef(BaseModel):
    id: UUID
    name: str


class LinkRef(BaseModel):
    kind: str
    id: UUID
    name: str
    table: TableRef | None = None


class ColumnRef(BaseModel):
    column_id: UUID
    name: str
    display_name: str


class TableDescription(BaseModel):
    table: TableDictionaryOut


class ColumnDescription(BaseModel):
    table: TableRef
    column: ColumnDictionaryOut


class MetricDetail(BaseModel):
    metric_id: UUID
    name: str
    label: str | None
    description: str | None
    expression: str
    format: str | None
    currency: str | None
    metric_type: str | None
    warning_text: str | None
    origin: str
    table: TableRef
    referenced_columns: list[ColumnRef]


class GlossaryTermDetail(BaseModel):
    term_id: UUID
    name: str
    business_domains: list[str]
    revision_number: int
    definition: str
    synonyms: list[str]
    links: list[LinkRef]


class RuleConditionDetail(BaseModel):
    column_id: UUID
    column_name: str | None
    operator: str
    value_type: str
    value: Any
    text: str


class RuleExceptionDetail(BaseModel):
    when: str
    outcome: str


class RuleExampleDetail(BaseModel):
    question: str
    intent: str


class ExpertRuleDetail(BaseModel):
    rule_id: UUID
    name: str
    business_domains: list[str]
    table: TableRef | None
    description: str | None
    conditions: list[RuleConditionDetail]
    exceptions: list[RuleExceptionDetail]
    examples: list[RuleExampleDetail]
    glossary_terms: list[NamedRef]
    metrics: list[NamedRef]


class OwnKnowledgeDetail(BaseModel):
    entry_id: UUID
    name: str
    kind: str
    concept: str | None
    definition: str
    table: TableRef | None
    review_status: str
    version: int
    updated_at: datetime
