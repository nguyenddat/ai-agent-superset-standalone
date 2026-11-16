import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from ..common.errors import Text2SqlEntityNotFound, Text2SqlInvalidRequest, Text2SqlMetricNotRunnable
from ..vector_store.ingestion.documents.context import CatalogContext, ColumnEntry
from .expression import compile_metric_expression
from .schemas import MAX_IN_VALUES, QueryFilter, QueryPlan, ResultColumn

NUMERIC_TYPES = re.compile(
    r"^(?:(?:small|big)?int(?:eger)?\d*|(?:small|big)?serial\d*|numeric|decimal|double|real|float|money)\b"
)
GROUPABLE = frozenset({"text", "numeric", "boolean", "date", "timestamp", "uuid"})
FILTERABLE = frozenset({"text", "numeric", "boolean", "date", "timestamp"})
ORDERED = frozenset({"numeric", "date", "timestamp"})
COMPARISONS = {
    "equals": "=", "not_equals": "<>", "greater_than": ">", "greater_than_or_equal": ">=",
    "less_than": "<", "less_than_or_equal": "<=",
}


def type_category(data_type: str) -> str:
    text = data_type.strip().lower()
    if text.startswith("interval"):
        return "other"
    if "bool" in text:
        return "boolean"
    if NUMERIC_TYPES.match(text):
        return "numeric"
    if text.startswith("timestamp"):
        return "timestamp"
    if text == "date":
        return "date"
    if text == "uuid":
        return "uuid"
    if any(word in text for word in ("char", "text", "citext")):
        return "text"
    return "other"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class OutputColumn:
    alias: str
    spec: ResultColumn
    name: str
    scan: bool


@dataclass
class CompiledQuery:
    connection_id: UUID
    metric_id: UUID
    metric_name: str
    metric_label: str | None
    metric_format: str | None
    metric_currency: str | None
    metric_warning: str | None
    table_label: str
    sql: str
    parameters: dict[str, Any]
    expanding: frozenset[str]
    columns: list[OutputColumn]
    limit: int
    pii_columns: list[str] = field(default_factory=list)


def _is_pii(entry: ColumnEntry) -> bool:
    return bool(entry.dictionary and entry.dictionary.contains_pii)


def _number(value: Any, label: str) -> int | float | Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise Text2SqlInvalidRequest(f"Giá trị lọc theo cột số '{label}' phải là số.")
    try:
        return value if isinstance(value, (int, float, Decimal)) else Decimal(value.strip())
    except InvalidOperation:
        raise Text2SqlInvalidRequest(f"Giá trị '{value}' không phải số hợp lệ cho cột '{label}'.") from None


def _temporal(value: Any, category: str, label: str) -> date | datetime:
    try:
        if isinstance(value, datetime):
            return value if category == "timestamp" else value.date()
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day) if category == "timestamp" else value
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.strip())
            return parsed if category == "timestamp" else parsed.date()
    except ValueError:
        pass
    raise Text2SqlInvalidRequest(f"Giá trị lọc theo cột thời gian '{label}' phải là ngày ISO (YYYY-MM-DD).")


def coerce(value: Any, category: str, label: str) -> Any:
    if category == "numeric":
        return _number(value, label)
    if category in ("date", "timestamp"):
        return _temporal(value, category, label)
    if category == "boolean":
        if not isinstance(value, bool):
            raise Text2SqlInvalidRequest(f"Giá trị lọc theo cột '{label}' phải là true hoặc false.")
        return value
    if not isinstance(value, str):
        raise Text2SqlInvalidRequest(f"Giá trị lọc theo cột văn bản '{label}' phải là chuỗi.")
    return value


class _Builder:
    def __init__(self) -> None:
        self.parameters: dict[str, Any] = {}
        self.expanding: set[str] = set()

    def bind(self, value: Any, expanding: bool = False) -> str:
        name = f"p{len(self.parameters)}"
        self.parameters[name] = value
        if expanding:
            self.expanding.add(name)
        return f":{name}"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _condition(builder: _Builder, entry: ColumnEntry, filter_: QueryFilter) -> str:
    column = quote(entry.column.name)
    category = type_category(entry.column.data_type)
    operator, value, label = filter_.operator, filter_.value, entry.label
    if category not in FILTERABLE:
        raise Text2SqlInvalidRequest(f"Không hỗ trợ lọc theo cột '{label}' (kiểu {entry.column.data_type}).")
    if operator in ("is_null", "is_not_null"):
        if value is not None:
            raise Text2SqlInvalidRequest(f"Toán tử {operator} không nhận giá trị.")
        return f"{column} IS {'NOT ' if operator == 'is_not_null' else ''}NULL"
    if value is None:
        raise Text2SqlInvalidRequest(f"Toán tử {operator} cần một giá trị.")
    if operator in ("in", "not_in"):
        if not isinstance(value, list) or not 0 < len(value) <= MAX_IN_VALUES:
            raise Text2SqlInvalidRequest(f"Toán tử {operator} cần danh sách từ 1 đến {MAX_IN_VALUES} giá trị.")
        marker = builder.bind([coerce(item, category, label) for item in value], expanding=True)
        return f"{column} {'NOT ' if operator == 'not_in' else ''}IN {marker}"
    if isinstance(value, list):
        raise Text2SqlInvalidRequest(f"Toán tử {operator} chỉ nhận một giá trị.")
    if operator in ("contains", "not_contains"):
        if category != "text":
            raise Text2SqlInvalidRequest(f"Toán tử {operator} chỉ dùng cho cột văn bản ('{label}').")
        marker = builder.bind(f"%{_escape_like(coerce(value, category, label))}%")
        return f"{column} {'NOT ' if operator == 'not_contains' else ''}ILIKE {marker} ESCAPE '\\'"
    if operator in ("greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal") \
            and category not in ORDERED:
        raise Text2SqlInvalidRequest(f"Toán tử {operator} chỉ dùng cho cột số hoặc thời gian ('{label}').")
    return f"{column} {COMPARISONS[operator]} {builder.bind(coerce(value, category, label))}"


def compile_query(
    context: CatalogContext, connection_id: UUID, plan: QueryPlan, max_rows: int,
) -> CompiledQuery:
    metric = context.metrics_by_id.get(plan.metric_id)
    if metric is None or metric.table_id is None:
        raise Text2SqlEntityNotFound()
    if metric.source_sql:
        raise Text2SqlMetricNotRunnable("Metric thuộc dataset ảo nên chưa thể truy vấn.")
    table = context.tables[metric.table_id]
    table_columns = {
        entry.column.id: entry for entry in context.columns if entry.column.table_id == metric.table_id
    }
    by_name = {entry.column.name.lower(): (column_id, entry.column.name) for column_id, entry in table_columns.items()}
    metric_sql = compile_metric_expression(metric.expression, by_name)

    def entry_of(column_id: UUID) -> ColumnEntry:
        entry = table_columns.get(column_id)
        if entry is None:
            raise Text2SqlInvalidRequest(f"Cột {column_id} không thuộc bảng của metric.")
        return entry

    builder = _Builder()
    select: list[str] = []
    group: list[str] = []
    columns: list[OutputColumn] = []
    pii_columns: list[str] = []
    aliases: dict[str, str] = {}

    time_entry: ColumnEntry | None = None
    if plan.time is not None:
        time_entry = entry_of(plan.time.column_id)
        time_category = type_category(time_entry.column.data_type)
        if time_category not in ("date", "timestamp"):
            raise Text2SqlInvalidRequest(f"Cột '{time_entry.label}' không phải cột ngày hoặc ngày giờ.")
        if _is_pii(time_entry):
            raise Text2SqlInvalidRequest(f"Không dùng cột dữ liệu cá nhân '{time_entry.label}' làm cột thời gian.")
        if plan.time.granularity is None and plan.time.start is None and plan.time.end is None:
            raise Text2SqlInvalidRequest("time cần ít nhất một trong granularity, start, end.")
        if plan.time.granularity is not None:
            bucket = f"date_trunc('{plan.time.granularity}', {quote(time_entry.column.name)})"
            if time_category == "date":
                bucket = f"CAST({bucket} AS date)"
            select.append(f'{bucket} AS "time_bucket"')
            group.append(str(len(select)))
            aliases["time"] = "time_bucket"
            columns.append(OutputColumn("time_bucket", ResultColumn(
                name=f"{time_entry.label} ({plan.time.granularity})", role="time", column_id=time_entry.column.id,
            ), time_entry.column.name, False))

    seen: set[UUID] = set()
    for position, column_id in enumerate(plan.group_by, start=1):
        if column_id in seen:
            raise Text2SqlInvalidRequest("group_by có cột bị trùng.")
        seen.add(column_id)
        entry = entry_of(column_id)
        if type_category(entry.column.data_type) not in GROUPABLE:
            raise Text2SqlInvalidRequest(f"Không hỗ trợ nhóm theo cột '{entry.label}' (kiểu {entry.column.data_type}).")
        alias = f"dim_{position}"
        select.append(f"{quote(entry.column.name)} AS {quote(alias)}")
        group.append(str(len(select)))
        aliases[str(column_id)] = alias
        flagged = _is_pii(entry)
        if flagged:
            pii_columns.append(entry.label)
        columns.append(OutputColumn(alias, ResultColumn(
            name=entry.label, role="dimension", column_id=column_id, contains_pii=flagged,
        ), entry.column.name, True))

    select.append(f"{metric_sql} AS \"metric_value\"")
    columns.append(OutputColumn("metric_value", ResultColumn(
        name=metric.label or metric.name, role="metric"), "metric_value", False,
    ))

    where: list[str] = []
    if plan.time is not None and time_entry is not None:
        category = type_category(time_entry.column.data_type)
        column = quote(time_entry.column.name)
        if plan.time.start is not None:
            where.append(f"{column} >= {builder.bind(coerce(plan.time.start, category, time_entry.label))}")
        if plan.time.end is not None:
            where.append(f"{column} < {builder.bind(coerce(plan.time.end, category, time_entry.label))}")
        if plan.time.start is not None and plan.time.end is not None and plan.time.start >= plan.time.end:
            raise Text2SqlInvalidRequest("time.start phải nhỏ hơn time.end.")
    for filter_ in plan.filters:
        entry = entry_of(filter_.column_id)
        if _is_pii(entry):
            raise Text2SqlInvalidRequest(
                f"Không lọc theo cột dữ liệu cá nhân '{entry.label}' để tránh truy vết một cá nhân cụ thể."
            )
        where.append(_condition(builder, entry, filter_))

    order = _order_by(plan, aliases, bool(group), plan.time is not None and plan.time.granularity is not None)
    limit = min(plan.limit, max_rows)
    sql = f"SELECT {', '.join(select)} FROM {quote(table.schema.name)}.{quote(table.table.name)}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if group:
        sql += " GROUP BY " + ", ".join(group)
        sql += " ORDER BY " + ", ".join(order)
    sql += f" LIMIT {builder.bind(limit + 1)}"
    return CompiledQuery(
        connection_id=connection_id, metric_id=metric.id, metric_name=metric.name, metric_label=metric.label,
        metric_format=metric.format, metric_currency=metric.currency, metric_warning=metric.warning_text,
        table_label=f"{table.qualified_name}", sql=sql, parameters=builder.parameters,
        expanding=frozenset(builder.expanding), columns=columns, limit=limit, pii_columns=pii_columns,
    )


def _order_by(plan: QueryPlan, aliases: dict[str, str], grouped: bool, has_bucket: bool) -> list[str]:
    if not grouped:
        return []
    if not plan.order_by:
        default = f"{quote('time_bucket')} ASC" if has_bucket else f"{quote('metric_value')} DESC"
        return [f"{default} NULLS LAST"]
    order: list[str] = []
    for item in plan.order_by:
        key = item.by.strip()
        alias = "metric_value" if key == "metric" else aliases.get(key)
        if alias is None:
            raise Text2SqlInvalidRequest(
                f"order_by '{item.by}' phải là \"metric\", \"time\" (khi có granularity) hoặc một cột trong group_by."
            )
        order.append(f"{quote(alias)} {item.direction.upper()} NULLS LAST")
    return order
