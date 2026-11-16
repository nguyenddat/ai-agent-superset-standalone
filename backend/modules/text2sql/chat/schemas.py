from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from ..query.schemas import QueryPlan, QueryResult


class NamedItem(BaseModel):
    id: UUID
    name: str


class RewriteInfo(BaseModel):
    original_question: str
    rewritten_question: str
    glossary_terms: list[NamedItem] = Field(default_factory=list)
    rules: list[NamedItem] = Field(default_factory=list)
    own_knowledge: list[NamedItem] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)


class RuleUse(BaseModel):
    id: UUID
    name: str
    filters: list[str] = Field(default_factory=list)
    overridden: list[str] = Field(default_factory=list)


class MetricChoice(BaseModel):
    id: UUID
    name: str
    label: str | None
    source: Literal["glossary_link", "rule_link", "search"]


class CandidateTable(BaseModel):
    table_id: UUID
    name: str
    display_name: str
    description: str | None


class Text2SqlFallback(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str
    candidate_tables: list[CandidateTable] = Field(default_factory=list)


class QueryOutcome(BaseModel):
    metric: MetricChoice
    plan: QueryPlan
    rules: list[RuleUse] = Field(default_factory=list)
    result: QueryResult | None = None


class AskResult(BaseModel):
    status: Literal["answered", "needs_clarification", "no_metric"]
    message: str
    rewrite: RewriteInfo
    queries: list[QueryOutcome] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    plan_analysis: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    text2sql: Text2SqlFallback | None = None
