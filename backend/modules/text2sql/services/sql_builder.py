import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from backend.agent_package.tool_agent import ToolError

from .agent_catalog import (
    AgentCatalog,
    ColumnInfo,
    MetricInfo,
    RuleCondition,
    TableInfo,
)
from .sql_guard import DIALECT

Operator = Literal[
    "equals", "not_equals", "contains", "not_contains", "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal", "in", "not_in", "is_null", "is_not_null",
]
Grain = Literal["day", "week", "month", "quarter", "year"]

MAX_EXPRESSION_NODES = 200
MAX_IN_VALUES = 200
NUMERIC_TYPES = re.compile(
    r"^(?:(?:small|big)?int(?:eger)?\d*|(?:small|big)?serial\d*|numeric|decimal|double|real|float|money)\b"
)
COMPARISONS: dict[str, type[exp.Binary]] = {
    "equals": exp.EQ, "not_equals": exp.NEQ, "greater_than": exp.GT, "greater_than_or_equal": exp.GTE,
    "less_than": exp.LT, "less_than_or_equal": exp.LTE,
}
ALLOWED_EXPRESSION_NODES: tuple[type[exp.Expression], ...] = (
    exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean, exp.Paren, exp.Neg, exp.Star, exp.Distinct,
    exp.AggFunc, exp.Filter, exp.Where, exp.Binary, exp.Not, exp.In, exp.Between, exp.Case, exp.If, exp.Coalesce,
    exp.Nullif, exp.Round, exp.Abs, exp.Ceil, exp.Floor, exp.Greatest, exp.Least, exp.Cast, exp.DataType,
    exp.Tuple, exp.Extract, exp.Var,
)


class FilterArg(BaseModel):
    column: str = Field(description="Tên cột thuộc bảng của metric")
    operator: Operator
    value: Any = Field(default=None, description="Ngày dạng YYYY-MM-DD; danh sách cho in/not_in; bỏ trống cho is_null")


class TimeGrainArg(BaseModel):
    column: str = Field(description="Cột ngày hoặc ngày giờ")
    grain: Grain


class OrderArg(BaseModel):
    field: str = Field(description="'value' (giá trị metric) hoặc một cột trong group_by/time_grain")
    direction: Literal["asc", "desc"] = "desc"


class QueryMetricArgs(BaseModel):
    metric: str = Field(description="Tên hoặc id của metric")
    filters: list[FilterArg] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list, description="Các cột để phân nhóm")
    time_grain: TimeGrainArg | None = Field(default=None, description="Gom theo ngày/tuần/tháng/quý/năm")
    order_by: list[OrderArg] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=1000)
    skip_rules: list[str] = Field(
        default_factory=list, description="Tên quy tắc chuyên gia không áp dụng, chỉ khi câu hỏi yêu cầu rõ"
    )
    assumption: str | None = Field(
        default=None, max_length=300,
        description="Giả định đã chọn khi câu hỏi thiếu thông tin, viết bằng lời thường cho người dùng",
    )
    chart: dict[str, Any] | None = Field(
        default=None,
        description="Biểu đồ cho kết quả (tùy chọn), cùng dạng như make_chart, dùng tên cột sẽ trả về",
    )


@dataclass(frozen=True)
class RuleUse:
    name: str
    status: Literal["applied", "yielded", "built_in", "skipped"]
    columns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BuiltQuery:
    sql: str
    notes: list[str]
    rules: list[RuleUse] = field(default_factory=list)


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
    if any(word in text for word in ("char", "text", "citext", "uuid")):
        return "text"
    return "other"


def _column(column: ColumnInfo) -> exp.Column:
    return exp.column(column.name, quoted=True)


def _literal(value: Any, column: ColumnInfo) -> exp.Expression:
    category = type_category(column.data_type)
    if category == "numeric":
        if isinstance(value, bool):
            raise ToolError(f"Cột '{column.name}' là cột số, không nhận true/false.")
        try:
            return exp.Literal.number(str(Decimal(str(value).strip())))
        except InvalidOperation:
            raise ToolError(f"Giá trị '{value}' không phải số hợp lệ cho cột '{column.name}'.") from None
    if category in ("date", "timestamp"):
        try:
            parsed = datetime.fromisoformat(str(value).strip())
        except ValueError:
            raise ToolError(
                f"Cột '{column.name}' là cột thời gian; giá trị phải là ngày ISO như {date.today().isoformat()}."
            ) from None
        return exp.Literal.string(parsed.date().isoformat() if category == "date" else parsed.isoformat(sep=" "))
    if category == "boolean":
        if not isinstance(value, bool):
            raise ToolError(f"Cột '{column.name}' chỉ nhận true hoặc false.")
        return exp.Boolean(this=value)
    if category == "other":
        raise ToolError(f"Không lọc được theo cột '{column.name}' (kiểu {column.data_type}); hãy dùng run_sql.")
    return exp.Literal.string(str(value))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def condition(column: ColumnInfo, operator: str, value: Any) -> exp.Expression:
    target = _column(column)
    if operator in ("is_null", "is_not_null"):
        node: exp.Expression = exp.Is(this=target, expression=exp.Null())
        return exp.Not(this=node) if operator == "is_not_null" else node
    if value is None:
        raise ToolError(f"Toán tử {operator} trên cột '{column.name}' cần một giá trị.")
    if operator in ("in", "not_in"):
        if not isinstance(value, list) or not 0 < len(value) <= MAX_IN_VALUES:
            raise ToolError(f"Toán tử {operator} cần danh sách từ 1 đến {MAX_IN_VALUES} giá trị.")
        node = target.isin(*(_literal(item, column) for item in value))
        return exp.Not(this=node) if operator == "not_in" else node
    if isinstance(value, list):
        raise ToolError(f"Toán tử {operator} chỉ nhận một giá trị; dùng 'in' cho danh sách.")
    if operator in ("contains", "not_contains"):
        if type_category(column.data_type) != "text":
            raise ToolError(f"Toán tử {operator} chỉ dùng cho cột văn bản ('{column.name}').")
        node = exp.ILike(this=target, expression=exp.Literal.string(f"%{_escape_like(str(value))}%"))
        return exp.Not(this=node) if operator == "not_contains" else node
    if operator not in ("equals", "not_equals") and type_category(column.data_type) not in (
        "numeric", "date", "timestamp",
    ):
        raise ToolError(f"Toán tử {operator} chỉ dùng cho cột số hoặc thời gian ('{column.name}').")
    return COMPARISONS[operator](this=target, expression=_literal(value, column))


def metric_expression(metric: MetricInfo, table: TableInfo) -> exp.Expression:
    advice = "hãy dùng get_metric để xem biểu thức rồi tự viết bằng run_sql."
    try:
        statements = parse(metric.expression, read=DIALECT)
    except (SqlglotError, RecursionError):
        raise ToolError(f"Không đọc được biểu thức của metric '{metric.name}'; {advice}") from None
    if len(statements) != 1 or statements[0] is None:
        raise ToolError(f"Biểu thức của metric '{metric.name}' phải là đúng một biểu thức; {advice}")
    tree = statements[0]
    nodes = list(tree.walk())
    unsupported = next((node for node in nodes if not isinstance(node, ALLOWED_EXPRESSION_NODES)), None)
    if len(nodes) > MAX_EXPRESSION_NODES or unsupported is not None or not any(
        isinstance(node, exp.AggFunc) for node in nodes
    ):
        raise ToolError(f"Biểu thức của metric '{metric.name}' không dựng tự động được; {advice}")
    for column in list(tree.find_all(exp.Column)):
        column.replace(_column(table.column(column.name)))
    return tree


def conditioned_columns(expression: exp.Expression) -> set[str]:
    conditions: list[exp.Expression] = []
    for node in expression.walk():
        if isinstance(node, exp.If):
            conditions.append(node.this)
        elif isinstance(node, exp.Filter):
            conditions.append(node.expression)
    return {column.name.lower() for condition in conditions for column in condition.find_all(exp.Column)}


def _rule_conditions(
    catalog: AgentCatalog, metric: MetricInfo, table: TableInfo, filtered: set[str], skipped: set[str],
    built_in: set[str],
) -> tuple[list[exp.Expression], list[str], list[RuleUse]]:
    conditions: list[exp.Expression] = []
    notes: list[str] = []
    uses: list[RuleUse] = []
    for rule in catalog.metric_rules(metric.id):
        if rule.name.lower() in skipped:
            notes.append(f"Bỏ qua quy tắc '{rule.name}' theo yêu cầu.")
            uses.append(RuleUse(rule.name, "skipped"))
            continue
        applied: list[RuleCondition] = []
        yielded: list[str] = []
        inside: list[str] = []
        for item in rule.conditions:
            if item.column.lower() in filtered:
                notes.append(
                    f"Quy tắc '{rule.name}': không áp điều kiện trên cột {item.column} vì câu hỏi đã lọc cột này."
                )
                yielded.append(item.column)
                continue
            if item.column.lower() in built_in:
                notes.append(
                    f"Quy tắc '{rule.name}': điều kiện trên cột {item.column} đã nằm trong biểu thức metric nên không "
                    "lọc thêm."
                )
                inside.append(item.column)
                continue
            conditions.append(condition(table.column(item.column), item.operator, item.value))
            applied.append(item)
        if applied:
            rendered = "; ".join(f"{item.column} {item.operator} {item.value}" for item in applied)
            notes.append(f"Đã áp quy tắc '{rule.name}': {rendered}.")
            uses.append(RuleUse(rule.name, "applied", [item.column for item in applied]))
        if yielded:
            uses.append(RuleUse(rule.name, "yielded", yielded))
        if inside:
            uses.append(RuleUse(rule.name, "built_in", inside))
        notes.extend(f"Ngoại lệ của quy tắc '{rule.name}': khi {item['when']} thì {item['outcome']}."
                     for item in rule.exceptions)
    return conditions, notes, uses


def build_metric_query(catalog: AgentCatalog, args: QueryMetricArgs) -> BuiltQuery:
    metric = catalog.metric(args.metric)
    table = catalog.tables[metric.table_id]
    if metric.source_sql:
        raise ToolError(
            f"Metric '{metric.name}' được định nghĩa trên một truy vấn riêng (source_sql), không dựng tự động được. "
            f"Dùng run_sql với truy vấn con: ({metric.source_sql}) và biểu thức {metric.expression}."
        )
    value_alias = metric.name
    projections: list[exp.Expression] = []
    groups: list[exp.Expression] = []
    outputs = {"value": value_alias, metric.name.lower(): value_alias}
    if args.time_grain is not None:
        column = table.column(args.time_grain.column)
        if type_category(column.data_type) not in ("date", "timestamp"):
            raise ToolError(f"Cột '{column.name}' không phải cột ngày hoặc ngày giờ.")
        bucket: exp.Expression = exp.func("DATE_TRUNC", exp.Literal.string(args.time_grain.grain), _column(column))
        if type_category(column.data_type) == "date":
            bucket = exp.cast(bucket, "date")
        projections.append(exp.alias_(bucket, column.name, quoted=True))
        groups.append(bucket.copy())
        outputs[column.name.lower()] = column.name
    for reference in args.group_by:
        column = table.column(reference)
        if column.name.lower() in outputs:
            continue
        projections.append(_column(column))
        groups.append(_column(column))
        outputs[column.name.lower()] = column.name
    expression = metric_expression(metric, table)
    projections.append(exp.alias_(expression, value_alias, quoted=True))
    query = exp.select(*projections).from_(exp.table_(table.name, db=table.schema, quoted=True))
    filtered = set()
    where = []
    for item in args.filters:
        column = table.column(item.column)
        filtered.add(column.name.lower())
        where.append(condition(column, item.operator, item.value))
    rule_conditions, notes, uses = _rule_conditions(
        catalog, metric, table, filtered, {name.strip().lower() for name in args.skip_rules},
        conditioned_columns(expression),
    )
    if where or rule_conditions:
        query = query.where(exp.and_(*where, *rule_conditions))
    if groups:
        query = query.group_by(*groups)
    for item in args.order_by:
        alias = outputs.get(item.field.lower()) or outputs.get(table.column(item.field).name.lower())
        if alias is None:
            raise ToolError(f"Chỉ sắp xếp được theo 'value' hoặc cột có trong group_by/time_grain, không theo "
                            f"'{item.field}'.")
        query = query.order_by(exp.Ordered(this=exp.column(alias, quoted=True), desc=item.direction == "desc"))
    if args.limit is not None:
        query = query.limit(args.limit)
    if metric.warning_text:
        notes.append(f"Lưu ý của metric: {metric.warning_text}")
    return BuiltQuery(sql=query.sql(dialect=DIALECT), notes=notes, rules=uses)
