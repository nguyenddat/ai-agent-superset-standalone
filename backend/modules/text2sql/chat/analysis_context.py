from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from ..dataset.schemas import DatasetResult
from ..query.schemas import PiiReport, QueryResult
from ..vector_store.ingestion.documents.context import CatalogContext
from .columns import analysis_columns, describe_columns, metric_value_type
from .planner import PlannedQuery
from .schemas import RewriteInfo

PII_NOTE = "Các cột đánh dấu dữ liệu cá nhân và giá trị nhận diện được đã được thay bằng placeholder."


@dataclass
class QueryReport:
    kind: str
    sql: str
    parameters: dict[str, Any]
    columns: list[dict[str, Any]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    pii: PiiReport
    metric: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    filters_overridden: list[str] = field(default_factory=list)

    def event_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.metric is not None:
            payload["metric"] = self.metric
        payload.update({
            "sql": self.sql, "parameters": self.parameters, "columns": self.columns, "rows": self.rows,
            "row_count": self.row_count, "truncated": self.truncated, "warnings": self.warnings,
            "rules_applied": self.rules_applied, "filters_overridden": self.filters_overridden,
            "pii": self.pii.model_dump(),
        })
        return payload

    def analysis_payload(self, max_rows: int) -> dict[str, Any]:
        return {
            "kind": self.kind, "metric": self.metric, "sql": self.sql, "parameters": self.parameters,
            "columns": analysis_columns(self.columns), "rows": self.rows[:max_rows], "row_count": self.row_count,
            "truncated": self.truncated, "warnings": self.warnings, "rules_applied": self.rules_applied,
            "filters_overridden": self.filters_overridden,
        }


def metric_report(planned: PlannedQuery, result: QueryResult, catalog: CatalogContext | None = None) -> QueryReport:
    info = result.metric
    warnings = [info.warning_text] if info.warning_text else []
    metric = {
        "name": info.name, "label": info.label or planned.metric.label or info.name, "format": info.format,
        "currency": info.currency,
    }
    source = catalog.metrics_by_id.get(info.metric_id) if catalog else None
    time = planned.plan.time
    columns = describe_columns(
        result.columns, result.value_types, catalog, time.granularity if time else None,
        {**metric, "data_type": metric_value_type(source.expression if source else None)},
    )
    return QueryReport(
        kind="metric", sql=result.sql, parameters=result.parameters, columns=columns, rows=result.rows,
        row_count=result.row_count, truncated=result.truncated, pii=result.pii, warnings=warnings, metric=metric,
        rules_applied=[f"{rule.name}: {'; '.join(rule.filters)}" for rule in planned.rules if rule.filters],
        filters_overridden=[
            f"{rule.name}: {condition}" for rule in planned.rules for condition in rule.overridden
        ],
    )


def dataset_report(
    result: DatasetResult, warnings: list[str], catalog: CatalogContext | None = None, granularity: str | None = None,
) -> QueryReport:
    columns = describe_columns(result.columns, result.value_types, catalog, granularity)
    return QueryReport(
        kind="dataset", sql=result.sql, parameters=result.parameters, columns=columns, rows=result.rows,
        row_count=result.row_count, truncated=result.truncated, pii=result.pii,
        warnings=list(dict.fromkeys([*result.warnings, *warnings])),
    )


@dataclass
class ChatAnswer:
    question: str
    today: date
    flow: str = "none"
    status: str = "error"
    rewrite: RewriteInfo | None = None
    queries: list[QueryReport] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    message: str = ""
    join: dict[str, Any] | None = None
    clarification_question: str | None = None
    clarification_options: list[str] = field(default_factory=list)
    dataset_id: UUID | None = None
    continuation: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def finish(
        self, status: str, message: str = "", clarification_question: str | None = None,
        clarification_options: list[str] | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.clarification_question = clarification_question
        self.clarification_options = list(clarification_options or [])


def build_analysis_context(answer: ChatAnswer, max_rows: int) -> dict[str, Any]:
    rewrite = answer.rewrite
    masked = list(dict.fromkeys(name for query in answer.queries for name in query.pii.masked_columns))
    detected = any(query.pii.detected for query in answer.queries)
    return {
        "question": answer.question,
        "rewritten_question": rewrite.rewritten_question if rewrite else answer.question,
        "today": answer.today.isoformat(),
        "flow": answer.flow,
        "status": answer.status,
        "rewrite": {
            "changes": rewrite.changes if rewrite else [],
            "glossary_terms": [item.name for item in rewrite.glossary_terms] if rewrite else [],
            "rules": [item.name for item in rewrite.rules] if rewrite else [],
            "own_knowledge": [item.name for item in rewrite.own_knowledge] if rewrite else [],
        },
        "queries": [query.analysis_payload(max_rows) for query in answer.queries],
        "assumptions": answer.assumptions,
        "pii": {"masked_columns": masked, "note": PII_NOTE if masked or detected else None},
        "message": answer.message,
        "join": answer.join,
        "clarification_question": answer.clarification_question,
    }
