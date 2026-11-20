from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from backend.agent_package.tool_agent import ToolError

from ..schemas import ExplanationOut
from .agent_catalog import AgentCatalog, ColumnInfo, TableInfo, normalized
from .display_format import date_display, period_label, vi_number
from .sql_builder import BuiltQuery, QueryMetricArgs, type_category
from .sql_guard import DIALECT

DESCRIPTION_LENGTH = 160
GRAIN_WORDS = {"day": "ngày", "week": "tuần", "month": "tháng", "quarter": "quý", "year": "năm"}
WORDS = {
    "not_equals": "khác", "greater_than": "trên", "greater_than_or_equal": "từ", "less_than": "dưới",
    "less_than_or_equal": "đến", "in": "là một trong", "not_in": "không thuộc", "contains": "chứa",
    "not_contains": "không chứa",
}
SQL_OPERATORS: dict[type[exp.Expression], str] = {
    exp.EQ: "equals", exp.NEQ: "not_equals", exp.GT: "greater_than", exp.GTE: "greater_than_or_equal",
    exp.LT: "less_than", exp.LTE: "less_than_or_equal",
}


@dataclass(frozen=True)
class ValueMatch:
    column: str
    requested: str
    matched: list[str]


@dataclass(frozen=True)
class DataRange:
    column: str
    start: Any
    end: Any


@dataclass(frozen=True)
class Condition:
    column: ColumnInfo
    operator: str
    value: Any


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _value_text(value: Any, column: ColumnInfo, today: date) -> str:
    category = type_category(column.data_type)
    if category in ("date", "timestamp"):
        day = _day(value)
        return date_display(day, today, weekday=False) if day else str(value)
    if category == "numeric" and not isinstance(value, bool):
        try:
            text = vi_number(float(value), None)
        except (TypeError, ValueError):
            return str(value)
        return f"{text} {column.unit}" if column.unit else text
    if isinstance(value, bool):
        return "có" if value else "không"
    return str(value)


def _filter_item(condition: Condition, today: date) -> ExplanationOut:
    column, operator, value = condition.column, condition.operator, condition.value
    label = column.label or column.name
    if column.contains_pii:
        return ExplanationOut(kind="filter", text=f"Lọc theo {label} (giá trị ẩn)", field=label)
    if operator == "is_null":
        return ExplanationOut(kind="filter", text=f"{label} không có giá trị", field=label)
    if operator == "is_not_null":
        return ExplanationOut(kind="filter", text=f"{label} có giá trị", field=label)
    values = value if isinstance(value, list) else [value]
    shown = [_value_text(item, column, today) for item in values]
    joined = ", ".join(shown)
    if operator == "equals":
        text = f"{label}: {joined}"
    elif operator in ("contains", "not_contains"):
        text = f"{label} {WORDS[operator]} «{joined}»"
    else:
        text = f"{label} {WORDS.get(operator, operator)} {joined}"
    return ExplanationOut(kind="filter", text=text, field=label, values=[str(item) for item in values])


def _conditions(conditions: list[Condition], today: date) -> list[ExplanationOut]:
    temporal: dict[str, dict[str, Any]] = {}
    others: list[Condition] = []
    for item in conditions:
        category = type_category(item.column.data_type)
        day = _day(item.value) if not isinstance(item.value, list) and item.value is not None else None
        if category in ("date", "timestamp") and day is not None and item.operator in (
            "equals", "greater_than_or_equal", "less_than", "less_than_or_equal",
        ):
            bounds = temporal.setdefault(item.column.name, {"column": item.column, "items": []})
            bounds["items"].append(item)
            if item.operator == "equals":
                bounds["start"], bounds["end"] = day, day
            elif item.operator == "greater_than_or_equal":
                bounds["start"] = day
            elif item.operator == "less_than":
                bounds["end"] = day - timedelta(days=1)
            else:
                bounds["end"] = day
            continue
        others.append(item)
    found: list[ExplanationOut] = []
    for bounds in temporal.values():
        start, end = bounds.get("start"), bounds.get("end")
        column = bounds["column"]
        if start is None or end is None or end < start:
            others.extend(bounds["items"])
            continue
        label = column.label or column.name
        found.append(ExplanationOut(
            kind="period", text=f"Thời gian: {period_label(start, end + timedelta(days=1), today)}", field=label,
            start=start.isoformat(), end=end.isoformat(),
        ))
    found.extend(_filter_item(item, today) for item in others)
    return found


def metric_explanations(
    catalog: AgentCatalog, args: QueryMetricArgs, built: BuiltQuery, matches: list[ValueMatch],
    data_range: DataRange | None, aggregated: bool, truncated: bool, row_count: int, today: date,
) -> list[ExplanationOut]:
    metric = catalog.metric(args.metric)
    table = catalog.tables[metric.table_id]
    label = metric.label or metric.name
    items: list[ExplanationOut] = []
    description = f" – {_clip(metric.description, DESCRIPTION_LENGTH)}" if metric.description else ""
    items.append(ExplanationOut(kind="metric", text=f"Chỉ số: {label}{description}", name=metric.name))
    grain = f" (mỗi dòng: {table.grain})" if table.grain else ""
    items.append(ExplanationOut(kind="source", text=f"Nguồn: {table.label}{grain}"))
    conditions = [Condition(table.column(item.column), item.operator, item.value) for item in args.filters]
    items.extend(_conditions(conditions, today))
    if args.group_by:
        names = ", ".join(dict.fromkeys(table.column(item).label for item in args.group_by))
        items.append(ExplanationOut(kind="group", text=f"Chia theo: {names}"))
    if args.time_grain is not None:
        items.append(ExplanationOut(kind="group", text=f"Gộp theo: {GRAIN_WORDS[args.time_grain.grain]}"))
    order = _order_text(table, args, label)
    if order:
        items.append(ExplanationOut(kind="order", text=order))
    items.extend(_rule_items(built, table))
    for match in matches:
        column = table.column(match.column)
        shown = ", ".join(f"«{value}»" for value in match.matched)
        items.append(ExplanationOut(
            kind="value_match", text=f"«{match.requested}» được hiểu là {shown} trong dữ liệu",
            field=column.label, values=None if column.contains_pii else list(match.matched),
        ))
    if data_range is not None:
        column = table.column(data_range.column)
        start, end = _day(data_range.start), _day(data_range.end)
        if start is not None and end is not None:
            items.append(ExplanationOut(
                kind="data_range", field=column.label, start=start.isoformat(), end=end.isoformat(),
                text=(f"Không giới hạn thời gian: tính trên toàn bộ dữ liệu từ {date_display(start, today, False)} "
                      f"đến {date_display(end, today, False)}"),
            ))
    if aggregated:
        items.append(ExplanationOut(kind="scope", text="Số gộp chung, không chia theo đối tượng"))
    items.extend(_common(args.assumption, truncated, row_count))
    if metric.warning_text:
        items.append(ExplanationOut(kind="warning", text=metric.warning_text))
    return items


def _order_text(table: TableInfo, args: QueryMetricArgs, metric_label: str) -> str | None:
    parts = []
    for item in args.order_by:
        if item.field.lower() in ("value", args.metric.lower()):
            name = metric_label
        else:
            try:
                name = table.column(item.field).label
            except ToolError:
                name = item.field
        parts.append(f"{'giảm' if item.direction == 'desc' else 'tăng'} dần theo {name}")
    text = f"Sắp xếp {', '.join(parts)}" if parts else ""
    if args.limit is not None:
        text = f"{text}, lấy {args.limit} dòng đầu" if text else f"Lấy {args.limit} dòng đầu"
    return text or None


def _label(table: TableInfo, name: str) -> str:
    try:
        return table.column(name).label or name
    except ToolError:
        return name


def _rule_items(built: BuiltQuery, table: TableInfo) -> list[ExplanationOut]:
    items = []
    for use in built.rules:
        if use.status == "applied":
            text = f"Áp dụng quy tắc «{use.name}»"
        elif use.status == "yielded":
            columns = ", ".join(_label(table, name) for name in use.columns)
            text = f"Quy tắc «{use.name}» không lọc {columns} vì câu hỏi đã lọc"
        elif use.status == "skipped":
            text = f"Không áp quy tắc «{use.name}» theo yêu cầu"
        else:
            continue
        items.append(ExplanationOut(kind="rule", text=text, name=use.name, status=use.status))
    return items


def _common(assumption: str | None, truncated: bool, row_count: int) -> list[ExplanationOut]:
    items = []
    if assumption and assumption.strip():
        items.append(ExplanationOut(kind="assumption", text=assumption.strip()))
    if truncated:
        items.append(ExplanationOut(kind="truncated", text=f"Chỉ lấy {row_count} dòng đầu theo giới hạn truy vấn"))
    return items


def _literal(node: exp.Expression) -> tuple[bool, Any]:
    if isinstance(node, exp.Cast):
        node = node.this
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal) and not node.this.is_string:
        return True, -float(node.this.this)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return True, node.this
        return True, float(node.this) if "." in node.this else int(node.this)
    if isinstance(node, exp.Boolean):
        return True, node.this
    return False, None


def _sql_tables(tree: exp.Expression, catalog: AgentCatalog) -> list[TableInfo]:
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    found: list[TableInfo] = []
    for node in tree.find_all(exp.Table):
        if not node.name or (not node.db and node.name.lower() in ctes):
            continue
        qualified = catalog.table_names.get(f"{node.db}.{node.name}".lower() if node.db else node.name.lower())
        table = next((item for item in catalog.tables.values() if item.qualified_name == qualified), None)
        if table is not None and table not in found:
            found.append(table)
    return found


def _where_conditions(select: exp.Select, tables: list[TableInfo]) -> list[Condition] | None:
    where = select.args.get("where")
    if where is None:
        return []
    parts = list(where.this.flatten()) if isinstance(where.this, exp.And) else [where.this]
    conditions: list[Condition] = []
    for part in parts:
        found = _condition(part, tables)
        if found is None:
            return None
        conditions.extend(found)
    return conditions


def _column(node: exp.Expression, tables: list[TableInfo]) -> ColumnInfo | None:
    if not isinstance(node, exp.Column):
        return None
    matches = [column for table in tables for column in table.columns if column.name.lower() == node.name.lower()]
    return matches[0] if matches and len({item.label for item in matches}) == 1 else None


def _condition(part: exp.Expression, tables: list[TableInfo]) -> list[Condition] | None:
    while isinstance(part, exp.Paren):
        part = part.this
    if isinstance(part, exp.Not) and isinstance(part.this, exp.Is):
        column = _column(part.this.this, tables)
        if column is None or not isinstance(part.this.expression, exp.Null):
            return None
        return [Condition(column, "is_not_null", None)]
    if isinstance(part, exp.Is):
        column = _column(part.this, tables)
        if column is None or not isinstance(part.expression, exp.Null):
            return None
        return [Condition(column, "is_null", None)]
    if type(part) in SQL_OPERATORS:
        column = _column(part.this, tables)
        ok, value = _literal(part.expression)
        if column is None or not ok:
            return None
        return [Condition(column, SQL_OPERATORS[type(part)], value)]
    if isinstance(part, exp.Between):
        column = _column(part.this, tables)
        low_ok, low = _literal(part.args["low"])
        high_ok, high = _literal(part.args["high"])
        if column is None or not (low_ok and high_ok):
            return None
        return [Condition(column, "greater_than_or_equal", low), Condition(column, "less_than_or_equal", high)]
    if isinstance(part, exp.In) and not part.args.get("query"):
        column = _column(part.this, tables)
        values = [_literal(item) for item in part.expressions]
        if column is None or not values or not all(ok for ok, _ in values):
            return None
        return [Condition(column, "in", [value for _, value in values])]
    return None


def sql_explanations(
    catalog: AgentCatalog, sql: str, purpose: str, assumption: str | None, rules_applied: list[str],
    truncated: bool, row_count: int, today: date,
) -> tuple[list[ExplanationOut], list[str]]:
    items = [ExplanationOut(kind="method", text=purpose.strip())] if purpose and purpose.strip() else []
    notes: list[str] = []
    try:
        tree = parse_one(sql, read=DIALECT)
    except (SqlglotError, RecursionError, ValueError):
        tree = None
    if tree is not None:
        try:
            tables = _sql_tables(tree, catalog)
            if tables:
                items.append(ExplanationOut(
                    kind="source", text=f"Nguồn: {', '.join(table.label for table in tables)}",
                ))
            conditions = _where_conditions(tree, tables) if isinstance(tree, exp.Select) else None
            if conditions:
                items.extend(_conditions(conditions, today))
        except (SqlglotError, ValueError, TypeError, KeyError):
            pass
    seen: set[str] = set()
    for name in rules_applied:
        try:
            rule = catalog.rule(name)
        except ToolError:
            notes.append(f"Không có quy tắc '{name}'.")
            continue
        if normalized(rule.name) in seen:
            continue
        seen.add(normalized(rule.name))
        items.append(ExplanationOut(
            kind="rule", text=f"Áp dụng quy tắc «{rule.name}»", name=rule.name, status="applied",
        ))
    items.extend(_common(assumption, truncated, row_count))
    return items, notes
