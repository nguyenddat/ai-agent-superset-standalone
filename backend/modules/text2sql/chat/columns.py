import re
from typing import Any

from ..query.schemas import ResultColumn
from ..vector_store.ingestion.documents.context import CatalogContext, ColumnEntry

GRANULARITY_LABELS = {"day": "ngày", "week": "tuần", "month": "tháng", "quarter": "quý", "year": "năm"}
AGGREGATION_LABELS = {
    "sum": "tổng", "avg": "trung bình", "min": "nhỏ nhất", "max": "lớn nhất", "count": "số lượng",
    "count_distinct": "số giá trị khác nhau",
}
COUNTING = frozenset({"count", "count_distinct"})
INTEGER_TYPES = re.compile(r"^(?:smallint|integer|bigint|int\d*|smallserial|serial\d*|bigserial)\b")
DECIMAL_TYPES = re.compile(r"^(?:numeric|decimal|money)\b")
FLOAT_TYPES = re.compile(r"^(?:real|double|float)")
COUNT_EXPRESSION = re.compile(r"^\s*count\s*\([^()]*\)\s*$", re.IGNORECASE)
ANALYSIS_KEYS = ("name", "label", "role", "data_type", "unit")


def source_data_type(data_type: str) -> str:
    text = data_type.strip().lower()
    if text.startswith("timestamp"):
        return "datetime"
    if text == "date":
        return "date"
    if text.startswith("bool"):
        return "boolean"
    if INTEGER_TYPES.match(text):
        return "integer"
    if DECIMAL_TYPES.match(text):
        return "decimal"
    if FLOAT_TYPES.match(text):
        return "float"
    return "text"


def _time_column(column: ResultColumn, entry: ColumnEntry | None, observed: str | None, granularity: str | None):
    if entry is None:
        return column.name, observed, None, None
    label = entry.label
    if granularity in GRANULARITY_LABELS:
        label = f"{label} (theo {GRANULARITY_LABELS[granularity]})"
    kind = source_data_type(entry.column.data_type)
    return label, kind if kind in ("date", "datetime") else observed, None, None


def _aggregate_column(column: ResultColumn, entry: ColumnEntry, observed: str | None):
    aggregation = column.aggregation or ""
    dictionary = entry.dictionary
    if dictionary is None:
        label = column.name
    elif aggregation in AGGREGATION_LABELS:
        label = f"{dictionary.display_name} ({AGGREGATION_LABELS[aggregation]})"
    else:
        label = dictionary.display_name
    if aggregation in COUNTING:
        return label, observed or "integer", None, None
    kind = observed or source_data_type(entry.column.data_type)
    return label, kind, dictionary.format if dictionary else None, dictionary.unit if dictionary else None


def describe_column(
    column: ResultColumn, observed: str | None, catalog: CatalogContext | None, granularity: str | None = None,
    metric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = catalog.columns_by_id.get(column.column_id) if catalog and column.column_id else None
    if column.role == "time":
        label, kind, format_, unit = _time_column(column, entry, observed, granularity)
    elif column.role == "metric" and column.column_id is None and metric is not None:
        label, kind = metric.get("label") or column.name, observed or metric.get("data_type")
        format_, unit = metric.get("format"), metric.get("currency")
    elif column.role == "metric" and entry is not None:
        label, kind, format_, unit = _aggregate_column(column, entry, observed)
    elif entry is not None:
        dictionary = entry.dictionary
        label = dictionary.display_name if dictionary else column.name
        kind = source_data_type(entry.column.data_type)
        format_, unit = (dictionary.format, dictionary.unit) if dictionary else (None, None)
    else:
        label, kind, format_, unit = column.name, observed, None, None
    return {
        "name": column.name, "column_id": str(column.column_id) if column.column_id else None, "label": label,
        "role": column.role, "data_type": kind, "format": format_, "unit": unit, "contains_pii": column.contains_pii,
    }


def describe_columns(
    columns: list[ResultColumn], observed: list[str | None], catalog: CatalogContext | None,
    granularity: str | None = None, metric: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        describe_column(column, observed[index] if index < len(observed) else None, catalog, granularity, metric)
        for index, column in enumerate(columns)
    ]


def metric_value_type(expression: str | None) -> str | None:
    return "integer" if expression and COUNT_EXPRESSION.match(expression) else None


def analysis_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: column[key] for key in ANALYSIS_KEYS if column.get(key) is not None} for column in columns]
