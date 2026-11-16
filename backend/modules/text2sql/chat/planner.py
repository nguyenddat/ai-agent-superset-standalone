from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from pydantic import ValidationError

from backend.agent_package.agents.query_plan_agent import DraftQuery, PlanDraft
from backend.modules.metric_management.models import Metric

from ..common.errors import (
    Text2SqlEntityNotFound,
    Text2SqlInvalidRequest,
    Text2SqlMetricNotRunnable,
)
from ..query.compiler import CompiledQuery, compile_query, type_category
from ..query.schemas import QueryFilter, QueryOrder, QueryPlan, QueryTime
from ..vector_store.ingestion.documents.context import ColumnEntry
from .context import AskContext, RuleCandidate
from .rewrite import RewriteOutcome
from .schemas import MetricChoice, RuleUse

DEFAULT_LIMIT = 100
MAX_PROMPT_COLUMNS = 80


@dataclass(frozen=True)
class MetricCandidate:
    metric: Metric
    source: str


@dataclass
class PlannedQuery:
    metric: MetricChoice
    plan: QueryPlan
    compiled: CompiledQuery
    rules: list[RuleUse] = field(default_factory=list)


def linked_metrics(context: AskContext, rewrite: RewriteOutcome) -> list[MetricCandidate]:
    found: dict[UUID, str] = {}
    for term in context.terms:
        if term.id in rewrite.term_ids:
            for metric_id in term.metric_ids:
                found.setdefault(metric_id, "glossary_link")
    for rule in context.rules:
        if rule.id in rewrite.rule_ids:
            for metric_id in rule.metric_ids:
                found.setdefault(metric_id, "rule_link")
    candidates = []
    for metric_id, source in found.items():
        metric = context.catalog.metrics_by_id.get(metric_id)
        if metric is not None and metric.table_id is not None and not metric.source_sql:
            candidates.append(MetricCandidate(metric, source))
    return candidates


def _column_payload(entry: ColumnEntry) -> dict:
    dictionary = entry.dictionary
    return {
        "name": entry.column.name, "label": entry.label, "type": entry.column.data_type,
        "role": dictionary.semantic_role if dictionary else None,
        "description": (dictionary.description if dictionary else None) or entry.column.description,
        "unit": dictionary.unit if dictionary else None, "synonyms": entry.synonyms,
        "is_personal_data": bool(dictionary and dictionary.contains_pii),
    }


def _rule_payload(rule: RuleCandidate) -> dict:
    return {
        "id": str(rule.id), "name": rule.name, "description": rule.description, "conditions": rule.conditions_text,
        "exceptions": [{"when": item["when"], "outcome": item["outcome"]} for item in rule.exceptions],
    }


def build_plan_context(
    original_question: str, rewritten_question: str, today: date, candidates: list[MetricCandidate],
    context: AskContext,
) -> dict:
    payload = []
    for candidate in candidates:
        metric = candidate.metric
        table = context.catalog.tables[metric.table_id]
        columns = [entry for entry in context.catalog.columns if entry.column.table_id == metric.table_id]
        payload.append({
            "id": str(metric.id), "label": metric.label or metric.name, "name": metric.name,
            "source": candidate.source, "description": metric.description, "expression": metric.expression,
            "table": f"{table.label} ({table.qualified_name})",
            "columns": [_column_payload(entry) for entry in columns[:MAX_PROMPT_COLUMNS]],
            "rules": [_rule_payload(rule) for rule in context.rules_for_metric(metric.id, metric.table_id)],
        })
    return {
        "original_question": original_question, "question": rewritten_question, "today": today.isoformat(),
        "metric_candidates": payload,
    }


def _columns_by_name(context: AskContext, table_id: UUID) -> dict[str, ColumnEntry]:
    columns = [entry for entry in context.catalog.columns if entry.column.table_id == table_id]
    named = {entry.column.name.lower(): entry for entry in columns}
    labels: dict[str, list[ColumnEntry]] = {}
    for entry in columns:
        labels.setdefault(entry.label.lower(), []).append(entry)
    for label, entries in labels.items():
        if len(entries) == 1:
            named.setdefault(label, entries[0])
    return named


def _resolve(name: str, columns: dict[str, ColumnEntry]) -> ColumnEntry:
    entry = columns.get(str(name).strip().lower())
    if entry is None:
        valid = ", ".join(sorted({item.column.name for item in columns.values()}))
        raise Text2SqlInvalidRequest(f"Cột '{name}' không tồn tại trong bảng của metric. Cột hợp lệ: {valid}.")
    return entry


def typed_value(raw: str | list[str] | None, operator: str, entry: ColumnEntry):
    is_boolean = type_category(entry.column.data_type) == "boolean"

    def convert(item: str):
        if is_boolean and isinstance(item, str) and item.strip().lower() in ("true", "false"):
            return item.strip().lower() == "true"
        return item

    if operator in ("in", "not_in"):
        items = raw if isinstance(raw, list) else ([] if raw is None else [raw])
        return [convert(item) for item in items]
    if isinstance(raw, list):
        raw = raw[0] if len(raw) == 1 else raw
    return convert(raw) if isinstance(raw, str) else raw



def _rule_filters_of(condition: dict) -> QueryFilter:
    return QueryFilter(
        column_id=UUID(condition["column_id"]), operator=condition["operator"], value=condition.get("value"),
    )


def _materialize_one(
    draft: DraftQuery, candidates: dict[UUID, MetricCandidate], context: AskContext, connection_id: UUID,
    max_rows: int,
) -> PlannedQuery:
    try:
        metric_id = UUID(draft.metric_id.strip())
    except ValueError:
        raise Text2SqlInvalidRequest(f"metric_id '{draft.metric_id}' không hợp lệ.") from None
    candidate = candidates.get(metric_id)
    if candidate is None:
        raise Text2SqlInvalidRequest(f"Metric {metric_id} không nằm trong danh sách ứng viên.")
    metric = candidate.metric
    columns = _columns_by_name(context, metric.table_id)

    filters = []
    for item in draft.filters:
        entry = _resolve(item.column, columns)
        filters.append(QueryFilter(
            column_id=entry.column.id, operator=item.operator, value=typed_value(item.value, item.operator, entry),
        ))
    question_columns = {item.column_id for item in filters}
    uses: list[RuleUse] = []
    for rule in context.rules_for_metric(metric.id, metric.table_id):
        use = RuleUse(id=rule.id, name=rule.name)
        for condition, text in zip(rule.conditions, rule.conditions_text, strict=True):
            rule_filter = _rule_filters_of(condition)
            if rule_filter.column_id in question_columns:
                use.overridden.append(text)
                continue
            filters.append(rule_filter)
            use.filters.append(text)
        uses.append(use)

    time = None
    if draft.time is not None:
        time = QueryTime(
            column_id=_resolve(draft.time.column, columns).column.id, start=draft.time.start, end=draft.time.end,
            granularity=draft.time.granularity,
        )
    order_by = []
    for item in draft.order_by:
        key = item.by.strip()
        order_by.append(QueryOrder(
            by=key if key.lower() in ("metric", "time") else str(_resolve(key, columns).column.id),
            direction=item.direction,
        ))
    plan = QueryPlan(
        metric_id=metric.id, group_by=[_resolve(name, columns).column.id for name in draft.group_by], time=time,
        filters=filters, order_by=order_by, limit=max(1, draft.limit or DEFAULT_LIMIT),
    )
    compiled = compile_query(context.catalog, connection_id, plan, max_rows)
    choice = MetricChoice(id=metric.id, name=metric.name, label=metric.label, source=candidate.source)
    return PlannedQuery(metric=choice, plan=plan, compiled=compiled, rules=uses)


def materialize(
    draft: PlanDraft, candidates: list[MetricCandidate], context: AskContext, connection_id: UUID, max_rows: int,
) -> list[PlannedQuery]:
    by_id = {candidate.metric.id: candidate for candidate in candidates}
    planned: list[PlannedQuery] = []
    errors: list[str] = []
    for position, item in enumerate(draft.queries, start=1):
        try:
            planned.append(_materialize_one(item, by_id, context, connection_id, max_rows))
        except (Text2SqlInvalidRequest, Text2SqlMetricNotRunnable, Text2SqlEntityNotFound) as error:
            errors.append(f"truy vấn {position}: {error}")
        except ValidationError as error:
            errors.append(f"truy vấn {position}: {error.errors()[0]['msg']}")
    if errors:
        raise Text2SqlInvalidRequest("Không lập được kế hoạch truy vấn hợp lệ: " + "; ".join(errors))
    return planned
