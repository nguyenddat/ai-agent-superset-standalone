import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from backend.agent_package.tool_agent import ToolError
from backend.common.charts import humanize, is_non_finite, is_plain_name

from ..schemas import FieldOut
from .agent_catalog import AgentCatalog, ColumnInfo, MetricInfo, TableInfo
from .sql_builder import type_category
from .sql_guard import DIALECT

WEEKDAYS = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")
CURRENCY_UNITS = {"VND": "đồng", "USD": "USD", "EUR": "EUR"}
TRAILING_UNIT = re.compile(r"^(.*\S)\s*\(([^()]{1,16})\)\s*$")
D3_FORMAT = re.compile(r"^[^.%dfe]*?(,)?(?:\.(\d+))?~?([dfe%sgr])?$")
TIME_UNITS = ("day", "week", "month", "quarter", "year")
CATEGORY_TYPES = {"numeric": "number", "date": "date", "timestamp": "datetime", "text": "text", "boolean": "boolean"}


@dataclass(frozen=True)
class NumberStyle:
    decimals: int | None
    percent: bool


def vi_number(value: Any, decimals: int | None, grouped: bool = True) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError("cần số")
    number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if not number.is_finite():
        raise ValueError("số không hữu hạn")
    places = decimals
    if places is None:
        places = max(0, 2 - number.adjusted()) if number and abs(number) < 1 else 2
    rounded = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) + 0
    if rounded == 0:
        rounded = abs(rounded)
    text = f"{rounded:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    if grouped:
        whole = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{whole},{fraction}" if fraction else f"{sign}{whole}"


def parse_d3_format(text: str | None) -> NumberStyle:
    if not text:
        return NumberStyle(None, False)
    found = D3_FORMAT.match(text.strip())
    if not found or (found.group(2) is None and found.group(3) not in ("d", "%")):
        return NumberStyle(None, False)
    kind = found.group(3)
    if kind == "d":
        return NumberStyle(0, False)
    if kind not in ("f", "%", "e", None):
        return NumberStyle(None, False)
    decimals = int(found.group(2)) if found.group(2) is not None else None
    return NumberStyle(decimals, kind == "%")


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) and math.isfinite(value)


def number_display(value: Any, field: FieldOut) -> str | None:
    if not _finite(value):
        return None
    if field.format_hint == "plain":
        return vi_number(value, 0, grouped=False)
    if field.percent:
        return f"{vi_number(Decimal(repr(value)) * 100 if isinstance(value, float) else value * 100, field.decimals)}%"
    if field.decimals is not None:
        return vi_number(value, field.decimals)
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return vi_number(value, 0)
    return vi_number(value, None)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _year(day: date, today: date) -> str:
    return f"/{day.year}" if day.year != today.year else ""


def date_display(value: Any, today: date, weekday: bool = True) -> str | None:
    day = _as_date(value)
    if day is None:
        return None
    text = f"{day.day}/{day.month}{_year(day, today)}"
    return f"{WEEKDAYS[day.weekday()]}, {text}" if weekday else text


def datetime_display(value: Any, today: date) -> str | None:
    parsed = value if isinstance(value, datetime) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if parsed is None:
        return None
    return f"{parsed.hour:02d}:{parsed.minute:02d} {date_display(parsed.date(), today)}"


def week_label(start: date, today: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month and start.year == end.year:
        return f"tuần {start.day}–{end.day}/{end.month}{_year(end, today)}"
    head = f"{start.day}/{start.month}{_year(start, today) if start.year != end.year else ''}"
    return f"tuần {head}–{end.day}/{end.month}{_year(end, today)}"


def bucket_display(value: Any, unit: str, today: date) -> str | None:
    day = _as_date(value)
    if day is None:
        return None
    if unit == "day":
        return date_display(day, today)
    if unit == "week":
        return week_label(day - timedelta(days=day.weekday()), today)
    if unit == "month":
        return f"tháng {day.month}{_year(day, today)}"
    if unit == "quarter":
        return f"quý {(day.month - 1) // 3 + 1}{_year(day, today)}"
    return str(day.year)


def period_label(start: date, before: date, today: date) -> str:
    end = before - timedelta(days=1)
    if end <= start:
        return date_display(start, today) or start.isoformat()
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    if start.day == 1 and before == next_month:
        return f"tháng {start.month}{_year(start, today)}"
    show = start.year != today.year or end.year != today.year
    tail = f"/{end.year}" if show else ""
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day}/{end.month}{tail}"
    head_year = f"/{start.year}" if show and start.year != end.year else ""
    return f"{start.day}/{start.month}{head_year}–{end.day}/{end.month}{tail}"


def date_range(start: date, end: date) -> dict[str, str]:
    return {"from": start.isoformat(), "before": end.isoformat()}


def date_ranges(today: date) -> dict[str, dict[str, str]]:
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    previous_month = (month - timedelta(days=1)).replace(day=1)
    return {
        "yesterday": date_range(today - timedelta(days=1), today),
        "last_7_days": date_range(today - timedelta(days=7), today),
        "last_week": date_range(week - timedelta(days=7), week),
        "this_week": date_range(week, week + timedelta(days=7)),
        "this_month": date_range(month, next_month),
        "last_month": date_range(previous_month, month),
    }


DATE_WORDS = {
    "yesterday": "hôm qua", "last_7_days": "7 ngày qua", "last_week": "tuần trước", "this_week": "tuần này",
    "this_month": "tháng này", "last_month": "tháng trước",
}


def dates_context(today: date) -> dict[str, dict[str, str]]:
    context = {}
    for key, value in date_ranges(today).items():
        label = period_label(date.fromisoformat(value["from"]), date.fromisoformat(value["before"]), today)
        context[key] = {**value, "label": f"{DATE_WORDS[key]} ({label})"}
    return context


def today_label(today: date) -> str:
    return f"{today.isoformat()} ({WEEKDAYS[today.weekday()]})"


def cell_display(value: Any, field: FieldOut, today: date) -> Any:
    if value is None:
        return None
    if field.type == "number":
        return None if is_non_finite(value) else number_display(value, field) if _finite(value) else value
    if field.time_unit is not None and field.type in ("date", "datetime"):
        return bucket_display(value, field.time_unit, today) or value
    if field.type == "date":
        return date_display(value, today) or value
    if field.type == "datetime":
        return datetime_display(value, today) or value
    return value


def llm_rows(rows: list[list[Any]], fields: list[FieldOut], today: date) -> list[list[Any]]:
    return [
        [cell_display(value, fields[index], today) if index < len(fields) else value for index, value in enumerate(row)]
        for row in rows
    ]


def unique_columns(columns: list[str]) -> tuple[list[str], list[str]]:
    names: list[str] = []
    notes: list[str] = []
    seen: dict[str, int] = {}
    for position, name in enumerate(columns, start=1):
        if not name or name == "?column?":
            renamed = f"cot_{position}"
            notes.append(f"Cột thứ {position} không có tên nên đặt là '{renamed}'.")
        elif name in seen:
            seen[name] += 1
            renamed = f"{name}_{seen[name]}"
            while renamed in seen:
                seen[name] += 1
                renamed = f"{name}_{seen[name]}"
            notes.append(f"Cột trùng tên '{name}' đã đổi thành '{renamed}'.")
        else:
            renamed = name
        seen.setdefault(renamed, 1)
        names.append(renamed)
    return names, notes


def value_type(values: list[Any]) -> str | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    if all(isinstance(value, bool) for value in present):
        return "boolean"
    if all(isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) for value in present):
        return "number"
    if all(isinstance(value, date) and not isinstance(value, datetime) for value in present):
        return "date"
    if all(isinstance(value, date) for value in present):
        stamps = [value for value in present if isinstance(value, datetime)]
        midnight = all(value.time() == time(0) for value in stamps)
        return "date" if midnight else "datetime"
    if all(isinstance(value, (str, time, UUID, bytes, bytearray, memoryview)) for value in present):
        return "text"
    return "text"


def split_unit(label: str) -> tuple[str, str | None]:
    found = TRAILING_UNIT.match(label)
    return (found.group(1), found.group(2).strip()) if found else (label, None)


def catalog_columns(catalog: AgentCatalog, name: str, tables: list[TableInfo] | None = None) -> list[ColumnInfo]:
    pool = tables if tables else list(catalog.tables.values())
    return [column for table in pool for column in table.columns if column.name.lower() == name.lower()]


def _single_column(catalog: AgentCatalog, name: str, tables: list[TableInfo] | None) -> ColumnInfo | None:
    found = catalog_columns(catalog, name, tables)
    if not found:
        return None
    if len({column.label for column in found}) == 1:
        return found[0]
    return None


def metric_unit(metric: MetricInfo, table: TableInfo) -> str | None:
    if metric.currency:
        return CURRENCY_UNITS.get(metric.currency.upper(), metric.currency)
    try:
        tree = parse_one(metric.expression, read=DIALECT)
    except (SqlglotError, RecursionError):
        return None
    units = set()
    for node in tree.find_all(exp.Column):
        try:
            units.add(table.column(node.name).unit)
        except ToolError:
            return None
    units.discard(None)
    return units.pop() if len(units) == 1 else None


def metric_additive(metric: MetricInfo) -> bool | None:
    try:
        tree = parse_one(metric.expression, read=DIALECT)
    except (SqlglotError, RecursionError):
        return None
    while isinstance(tree, exp.Paren):
        tree = tree.this
    return isinstance(tree, (exp.Sum, exp.Count))


def _column_field(name: str, column: ColumnInfo, kind: str, time_unit: str | None) -> FieldOut:
    style = parse_d3_format(column.format)
    plain = kind == "number"
    return FieldOut(
        name=name, label=column.label or humanize(name), type=kind, unit=column.unit, decimals=style.decimals,
        percent=style.percent, role="dimension", format_hint="plain" if plain else None, time_unit=time_unit,
        pii=column.contains_pii,
    )


def _kind(values: list[Any], column: ColumnInfo | None) -> str:
    found = value_type(values)
    if found is not None:
        return found
    if column is not None:
        return CATEGORY_TYPES.get(type_category(column.data_type), "other")
    return "other"


def metric_fields(
    catalog: AgentCatalog, args: Any, columns: list[str], rows: list[list[Any]],
) -> list[FieldOut]:
    metric = catalog.metric(args.metric)
    table = catalog.tables[metric.table_id]
    grain_column = table.column(args.time_grain.column).name if args.time_grain is not None else None
    fields = []
    for index, name in enumerate(columns):
        values = [row[index] for row in rows if index < len(row)]
        if name == metric.name:
            style = parse_d3_format(metric.format)
            fields.append(FieldOut(
                name=name, label=metric.label or metric.name, type=value_type(values) or "number",
                unit=metric_unit(metric, table),
                decimals=style.decimals, percent=style.percent, additive=metric_additive(metric), role="measure",
            ))
            continue
        try:
            column = table.column(name)
        except ToolError:
            column = None
        if column is None:
            fields.append(_generic_field(name, _kind(values, None), None, None))
            continue
        unit = args.time_grain.grain if grain_column == column.name else None
        fields.append(_column_field(name, column, _kind(values, column), unit))
    return fields


def _generic_field(name: str, kind: str, label: str | None, unit: str | None) -> FieldOut:
    text = label or humanize(name)
    plain = kind == "number" and is_plain_name(name, label)
    return FieldOut(
        name=name, label=text, type=kind, unit=unit, role="measure" if kind == "number" and not plain else "dimension",
        format_hint="plain" if plain else None,
    )


@dataclass(frozen=True)
class Projection:
    grouped: bool
    extract: bool
    time_unit: str | None


def sql_projections(sql: str, count: int) -> list[Projection | None]:
    try:
        tree = parse_one(sql, read=DIALECT)
    except (SqlglotError, RecursionError):
        return [None] * count
    if not isinstance(tree, exp.Select) or any(isinstance(item, exp.Star) for item in tree.expressions):
        return [None] * count
    projections = tree.expressions
    if len(projections) != count:
        return [None] * count
    group = tree.args.get("group")
    keys = group.expressions if group is not None else []
    grouped_sql = set()
    grouped_index = set()
    aliases = {item.alias_or_name: position for position, item in enumerate(projections)}
    for key in keys:
        if isinstance(key, exp.Literal) and key.is_int:
            grouped_index.add(int(key.this) - 1)
        elif isinstance(key, exp.Column) and not key.table and key.name in aliases:
            grouped_index.add(aliases[key.name])
        grouped_sql.add(key.sql(dialect=DIALECT))
    found = []
    for position, item in enumerate(projections):
        inner = item.unalias()
        trunc = inner if isinstance(inner, (exp.TimestampTrunc, exp.DateTrunc)) else inner.find(
            exp.TimestampTrunc, exp.DateTrunc
        )
        unit = trunc.text("unit").lower() if trunc is not None else None
        found.append(Projection(
            grouped=position in grouped_index or inner.sql(dialect=DIALECT) in grouped_sql,
            extract=isinstance(inner, exp.Extract) or (
                isinstance(inner, exp.Anonymous) and inner.name.lower() == "date_part"
            ) or isinstance(inner, exp.Cast) and isinstance(inner.this, exp.Extract),
            time_unit=unit if unit in TIME_UNITS else None,
        ))
    return found


def sql_fields(
    catalog: AgentCatalog, sql: str, labels: dict[str, str], columns: list[str], rows: list[list[Any]],
) -> list[FieldOut]:
    projections = sql_projections(sql, len(columns))
    metrics = {metric.name.lower(): metric for metric in catalog.metrics.values()}
    fields = []
    for index, name in enumerate(columns):
        values = [row[index] for row in rows if index < len(row)]
        column = _single_column(catalog, name, None)
        kind = _kind(values, column)
        label = labels.get(name)
        unit = None
        decimals = None
        percent = False
        if column is not None:
            label = label or column.label
            unit = column.unit
            style = parse_d3_format(column.format)
            decimals, percent = style.decimals, style.percent
        elif name.lower() in metrics:
            metric = metrics[name.lower()]
            label = label or metric.label or metric.name
            table = catalog.tables.get(metric.table_id)
            unit = metric_unit(metric, table) if table is not None else None
            style = parse_d3_format(metric.format)
            decimals, percent = style.decimals, style.percent
        if label:
            label, inline = split_unit(label)
            unit = unit or inline
        projection = projections[index]
        time_unit = projection.time_unit if projection is not None and kind in ("date", "datetime") else None
        plain = kind == "number" and (
            is_plain_name(name, label) or (projection is not None and (projection.grouped or projection.extract))
        )
        fields.append(FieldOut(
            name=name, label=label or humanize(name), type=kind, unit=unit, decimals=decimals, percent=percent,
            role="dimension" if plain or kind != "number" else "measure", format_hint="plain" if plain else None,
            time_unit=time_unit, pii=bool(column and column.contains_pii),
        ))
    return fields


def llm_fields(fields: list[FieldOut]) -> list[dict[str, Any]]:
    compact = []
    for item in fields:
        data = item.model_dump(exclude={"pii"})
        compact.append({
            key: value for key, value in data.items()
            if value is not None and value is not False and value != "dimension"
        })
    return compact
