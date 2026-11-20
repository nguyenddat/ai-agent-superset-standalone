import math
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlglot import exp

from backend.agent_package.tool_agent import AgentPause, ToolError
from backend.common.charts import (
    ChartField,
    ChartSpecError,
    chart_display,
    compatible_types,
    spec_summary,
    suggest_chart,
    type_names,
    validate_chart,
)
from backend.core.setting import config

from ..repositories.source_query_repository import QueryRows
from ..schemas import AgentStepOut, ExplanationOut, FieldOut
from .agent_catalog import AgentCatalog, ColumnInfo, MetricInfo, TableInfo, normalized
from .display_format import llm_fields, llm_rows, metric_fields, sql_fields, unique_columns
from .explanations import DataRange, ValueMatch, metric_explanations, sql_explanations
from .sql_builder import FilterArg, QueryMetricArgs, build_metric_query, type_category
from .sql_guard import DIALECT, validate_select

QueryRunner = Callable[[str, int], QueryRows]

MAX_VALUE_SAMPLES = 50
MAX_KNOWN_VALUES = 500
MAX_VALUE_HINTS = 8
MAX_RELATED_COLUMNS = 5
VALUE_OPERATORS = ("equals", "not_equals", "in", "not_in", "contains", "not_contains")
MAX_CLARIFICATIONS = 2
MAX_OPTIONS = 8
RESULT_TOOLS = ("query_metric", "run_sql")
CHART_ARGUMENT = "Biểu đồ cho kết quả (tùy chọn), cùng dạng như make_chart, dùng tên cột sẽ trả về"

Describe = Callable[[list[str], list[tuple], bool], tuple[list[FieldOut], list[ExplanationOut], list[str]]]


def json_cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "<binary>"
    if isinstance(value, (list, tuple)):
        return [json_cell(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool, dict)):
        return value
    return str(value)


def extends(text: str, key: str) -> bool:
    return text != key and f" {key} " in f" {text} "


def table_has(table: TableInfo, name: str) -> bool:
    return any(column.name.lower() == name.lower() for column in table.columns)


@dataclass
class QueryCache:
    runner: QueryRunner
    max_rows: int
    results: dict[str, QueryRows] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def run(self, sql: str) -> QueryRows:
        with self.lock:
            cached = self.results.get(sql)
        if cached is not None:
            return cached
        result = self.runner(sql, self.max_rows)
        with self.lock:
            self.results[sql] = result
        return result


class MetricRef(BaseModel):
    metric: str = Field(description="Tên hoặc id của metric")


class TableRef(BaseModel):
    table: str = Field(description="schema.bảng, tên bảng hoặc id")


class RuleRef(BaseModel):
    rule: str = Field(description="Tên hoặc id của quy tắc chuyên gia")


class ColumnValuesArgs(BaseModel):
    table: str = Field(description="schema.bảng, tên bảng hoặc id")
    column: str = Field(description="Tên cột")
    search: str | None = Field(default=None, description="Chuỗi cần tìm, không phân biệt hoa thường")
    limit: int = Field(default=20, ge=1, le=MAX_VALUE_SAMPLES)


class RunSqlArgs(BaseModel):
    sql: str = Field(description="Một câu SELECT PostgreSQL trên các bảng của connection")
    purpose: str = Field(
        description="Câu này tính gì, viết bằng lời thường cho người dùng đọc (hiện trong phần Cách tính)"
    )
    assumption: str | None = Field(
        default=None, max_length=300,
        description="Giả định đã chọn khi câu hỏi thiếu thông tin, viết bằng lời thường cho người dùng",
    )
    rules_applied: list[str] = Field(
        default_factory=list, max_length=10, description="Tên các quy tắc chuyên gia đã tự áp trong SQL",
    )
    labels: dict[str, Annotated[str, Field(max_length=80)]] = Field(
        default_factory=dict, max_length=20,
        description="Nhãn tiếng Việt có dấu cho các cột tự đặt tên: {tên cột: nhãn}",
    )
    chart: dict[str, Any] | None = Field(default=None, description=CHART_ARGUMENT)


class MakeChartArgs(BaseModel):
    result_id: str = Field(min_length=1, max_length=32, description="Mã kết quả cần vẽ, ví dụ 1-2")
    chart: dict[str, Any] = Field(description="Biểu đồ JSON theo mô tả của công cụ")


class AskUserArgs(BaseModel):
    question: str = Field(min_length=1, max_length=500, description="Câu hỏi lại ngắn gọn bằng tiếng Việt")
    options: list[str] = Field(
        default_factory=list, max_length=MAX_OPTIONS,
        description="Các lựa chọn cụ thể lấy từ dữ liệu hoặc knowledge (nhãn metric, giá trị cột); có thể để trống",
    )


def make_chart_description(enabled: frozenset[str] | None) -> str:
    return (
        'Đặt hoặc đổi biểu đồ cho một kết quả đã có (result_id). chart là JSON: {"type", "title", "encoding": '
        '{"x": {"field"}, "y": [{"field", "aggregate"?, "mark"?}], "series"?: {"field"}, "row"?, "path"?, "size"?, '
        '"color"?, "goal"?, "compare"?, "source"?, "target"?, "label"?}, "transform"?: {"sort": {"by", "order"}, '
        '"top_n": {"n", "other"}, "filter", "index_to"}, "orientation"?, "axes"?: {"x"|"y": {"title", "scale", '
        '"min", "max", "zero"}}, "reference_lines"?: [{"axis", "value", "label"}], "annotations"?: [{"x", "text"}], '
        '"colors"?: {"scheme", "highlight", "assign"}, "facet"?: {"by", "columns"}, "options"?}. field là tên trong '
        "columns. Màu chỉ dùng series-1 … series-8, muted. Loại: "
        f"{', '.join(type_names(enabled))}. Chỉ chọn loại có trong chart_types của kết quả."
    )


def _field_data(item: Any) -> dict[str, Any]:
    data = item.model_dump() if isinstance(item, BaseModel) else dict(item)
    return {key: value for key, value in data.items() if key in ChartField.model_fields}


class Text2SqlToolkit:
    def __init__(
        self, catalog: AgentCatalog, cache: QueryCache, max_rows_to_llm: int, steps: list[AgentStepOut] | None = None,
        position: int = 1, today: date | None = None, question_type: str | None = None,
        enabled: frozenset[str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.cache = cache
        self.max_rows_to_llm = max_rows_to_llm
        self.steps: list[AgentStepOut] = list(steps or [])
        self.position = position
        self.today = today or date.today()
        self.question_type = question_type
        self.enabled = enabled if enabled is not None else config.text2sql_chart_types

    def tools(self) -> list[BaseTool]:
        return [
            StructuredTool.from_function(
                self.get_metric, name="get_metric", args_schema=MetricRef,
                description="Xem định nghĩa metric: biểu thức, bảng, các cột của bảng, quy tắc chuyên gia gắn kèm.",
            ),
            StructuredTool.from_function(
                self.get_table, name="get_table", args_schema=TableRef,
                description="Xem bảng: mô tả, độ chi tiết một dòng, các cột (kiểu, ý nghĩa, đồng nghĩa) và metric.",
            ),
            StructuredTool.from_function(
                self.get_expert_rule, name="get_expert_rule", args_schema=RuleRef,
                description="Xem đầy đủ một quy tắc chuyên gia: điều kiện, ngoại lệ, ví dụ.",
            ),
            StructuredTool.from_function(
                self.get_column_values, name="get_column_values", args_schema=ColumnValuesArgs,
                description="Xem các giá trị thực có trong một cột để viết điều kiện lọc đúng chính tả.",
            ),
            StructuredTool.from_function(
                self.query_metric, name="query_metric", args_schema=QueryMetricArgs,
                description=(
                    "Tính một metric bằng SQL do hệ thống dựng: lọc, phân nhóm, gom theo thời gian, sắp xếp, giới "
                    "hạn. Tự áp quy tắc chuyên gia gắn với metric. Ưu tiên công cụ này khi có metric phù hợp. Chỉ "
                    "lọc và phân nhóm theo cột của bảng chứa metric; cần cột ở bảng khác thì dùng run_sql. "
                    "chart (tùy chọn): biểu đồ cho kết quả, cùng dạng như make_chart, dùng tên cột sẽ trả về (cột "
                    "group_by và tên metric)."
                ),
            ),
            StructuredTool.from_function(
                self.run_sql, name="run_sql", args_schema=RunSqlArgs,
                description=(
                    "Chạy một câu SELECT tự viết (PostgreSQL, chỉ đọc) khi query_metric không diễn đạt được: "
                    "nối bảng, so sánh kỳ, dẫn xuất, tương quan, không có metric phù hợp. chart (tùy chọn): biểu đồ "
                    "cho kết quả, cùng dạng như make_chart, dùng tên cột sẽ trả về."
                ),
            ),
            StructuredTool.from_function(
                self.make_chart, name="make_chart", args_schema=MakeChartArgs,
                description=make_chart_description(self.enabled),
            ),
            StructuredTool.from_function(
                self.ask_user, name="ask_user", args_schema=AskUserArgs,
                description=(
                    "Dừng và hỏi lại người dùng khi câu hỏi thiếu thông tin bắt buộc mà không có cách hiểu hợp lý. "
                    "Kết quả trả về là câu trả lời của người dùng (user_reply). Chỉ dùng khi thật cần."
                ),
            ),
        ]

    def ask_user(self, question: str, options: list[str] | None = None) -> dict[str, Any]:
        if sum(step.tool == "ask_user" for step in self.steps) >= MAX_CLARIFICATIONS:
            raise ToolError("Đã hỏi lại người dùng đủ số lần; hãy chọn cách hiểu hợp lý nhất và nói rõ giả định.")
        choices = list(dict.fromkeys(option.strip() for option in options or [] if option.strip()))
        raise AgentPause({"question": question.strip(), "options": choices})

    def get_metric(self, metric: str) -> dict[str, Any]:
        found = self.catalog.metric(metric)
        table = self.catalog.tables[found.table_id]
        return {
            **self._metric(found), "table": table.qualified_name,
            "columns": [column.name for column in table.columns],
            "expert_rules": [rule.describe(table) for rule in self.catalog.metric_rules(found.id)],
        }

    def get_table(self, table: str) -> dict[str, Any]:
        found = self.catalog.table(table)
        return {
            "table": found.qualified_name, "label": found.label, "description": found.description,
            "grain": found.grain, "columns": [column.describe() for column in found.columns],
            "metrics": [self._metric(metric) for metric in self.catalog.table_metrics(found.id)],
        }

    def get_expert_rule(self, rule: str) -> dict[str, Any]:
        found = self.catalog.rule(rule)
        return found.describe(self.catalog.tables.get(found.table_id))

    def get_column_values(self, table: str, column: str, search: str | None = None, limit: int = 20) -> dict[str, Any]:
        found = self.catalog.table(table)
        target = found.column(column)
        if target.contains_pii:
            raise ToolError(f"Cột '{target.name}' chứa dữ liệu cá nhân nên không liệt kê giá trị.")
        if type_category(target.data_type) not in ("text", "boolean"):
            raise ToolError(f"Chỉ liệt kê giá trị cho cột văn bản; '{target.name}' có kiểu {target.data_type}.")
        arguments = {"table": found.qualified_name, "column": target.name, "search": search, "limit": limit}
        query = self._distinct_query(found, target)
        if search and search.strip():
            column_sql = exp.column(target.name, quoted=True)
            pattern = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(exp.ILike(
                this=exp.cast(column_sql, "text"), expression=exp.Literal.string(f"%{pattern}%"),
            ))
            output = self._execute("get_column_values", arguments, query.limit(limit).sql(dialect=DIALECT), [])
            if output["row_count"]:
                return output
            return self._accent_insensitive_values(found, target, search, limit, arguments)
        return self._execute("get_column_values", arguments, query.limit(limit).sql(dialect=DIALECT), [])

    def query_metric(self, **arguments: Any) -> dict[str, Any]:
        args = QueryMetricArgs.model_validate(arguments)
        requested = args
        try:
            args, value_notes, matches = self._resolve_filter_values(args)
            built = build_metric_query(self.catalog, args)
            time_notes, data_range = self._time_scope_notes(args)
            entity_notes, aggregated = self._entity_scope_notes(args)
            value_notes.extend([*time_notes, *entity_notes, *self._related_dimension_notes(args)])
        except ToolError as error:
            self._record("query_metric", args.model_dump(mode="json"), error=str(error))
            raise

        def describe(columns: list[str], rows: list[tuple], truncated: bool) -> tuple[list, list, list[str]]:
            fields = metric_fields(self.catalog, args, columns, rows)
            explanations = metric_explanations(
                self.catalog, requested, built, matches, data_range, aggregated, truncated, len(rows), self.today,
            )
            return fields, explanations, []

        return self._execute(
            "query_metric", args.model_dump(mode="json"), built.sql, [*value_notes, *built.notes], describe, args.chart,
        )

    def make_chart(self, result_id: str, chart: dict[str, Any]) -> dict[str, Any]:
        arguments = {"result_id": result_id, "chart": chart}
        index = next((
            position for position, step in enumerate(self.steps)
            if step.result_id == result_id and step.error is None and step.tool in RESULT_TOOLS
        ), None)
        if index is None:
            known = ", ".join(
                step.result_id for step in self.steps if step.result_id and step.tool in RESULT_TOOLS
            ) or "chưa có kết quả nào"
            message = f"Không có kết quả '{result_id}'. Các result_id: {known}."
            self._record("make_chart", arguments, error=message)
            raise ToolError(message)
        step = self.steps[index]
        fields = [ChartField.model_validate(_field_data(item)) for item in step.fields]
        try:
            validated = validate_chart(chart, fields, step.rows, result_id, not step.truncated, self.enabled)
        except ChartSpecError as error:
            message = "\n".join(error.errors)
            self._record("make_chart", arguments, result_id=result_id, error=message)
            raise ToolError(message) from None
        spec = validated.json()
        display = chart_display(validated.spec, validated.stats.get("points", 0), "agent")
        types = list(step.chart_types or [])
        if spec["type"] not in types:
            types.insert(0, spec["type"])
        self.steps[index] = step.model_copy(update={
            "chart": spec, "chart_source": "agent", "display": display, "chart_types": types,
        })
        self._record(
            "make_chart", arguments, result_id=result_id, chart=spec, chart_source="agent", display=display,
            notes=validated.warnings,
        )
        output: dict[str, Any] = {"result_id": result_id, "chart": spec_summary(spec), "display": display}
        if validated.warnings:
            output["warnings"] = validated.warnings
        return output

    def _time_scope_notes(self, args: QueryMetricArgs) -> tuple[list[str], DataRange | None]:
        table = self.catalog.tables[self.catalog.metric(args.metric).table_id]
        temporal = [column for column in table.columns if type_category(column.data_type) in ("date", "timestamp")]
        used = {table.column(item.column).name for item in args.filters}
        if args.time_grain is not None:
            used.add(table.column(args.time_grain.column).name)
        if not temporal or any(column.name in used for column in temporal):
            return [], None
        column = next((item for item in temporal if type_category(item.data_type) == "date"), temporal[0])
        column_sql = exp.column(column.name, quoted=True)
        query = exp.select(exp.func("MIN", column_sql), exp.func("MAX", column_sql.copy())).from_(
            exp.table_(table.name, db=table.schema, quoted=True)
        )
        rows = self.cache.run(query.sql(dialect=DIALECT)).rows
        if not rows or len(rows[0]) < 2 or rows[0][0] is None:
            return [], None
        start, end = json_cell(rows[0][0]), json_cell(rows[0][1])
        note = f"Không lọc theo thời gian nên kết quả gộp toàn bộ dữ liệu: cột {column.name} từ {start} đến {end}."
        return [note], DataRange(column.name, rows[0][0], rows[0][1])

    def _related_dimension_notes(self, args: QueryMetricArgs) -> list[str]:
        table = self.catalog.tables[self.catalog.metric(args.metric).table_id]
        notes = []
        for reference in args.group_by:
            column = table.column(reference)
            keys = {normalized(column.name.replace("_", " ")), normalized(column.label)}
            related = [
                f"{other.qualified_name}.{candidate.name} ({candidate.label})"
                for other in self.catalog.tables.values() if other.id != table.id
                for candidate in other.columns
                if candidate.name.lower() != column.name.lower() and not table_has(table, candidate.name)
                and any(extends(normalized(text), key) for key in keys if key
                        for text in (candidate.name.replace("_", " "), candidate.label))
            ]
            if related:
                shown = ", ".join(list(dict.fromkeys(related))[:MAX_RELATED_COLUMNS])
                notes.append(
                    f"Đã phân nhóm theo {column.name} ({column.label}). Bảng khác có cột tên gần giống nhưng nghĩa hẹp "
                    f"hơn: {shown}. Câu hỏi hỏi đúng chiều đó thì nối bảng bằng run_sql thay vì dùng {column.name}."
                )
        return notes

    def _entity_scope_notes(self, args: QueryMetricArgs) -> tuple[list[str], bool]:
        table = self.catalog.tables[self.catalog.metric(args.metric).table_id]
        texts = [column for column in table.columns if type_category(column.data_type) == "text"]
        used = {table.column(item.column).name for item in args.filters}
        if args.group_by or not texts or any(column.name in used for column in texts):
            return [], False
        grain = f" (mỗi dòng: {table.grain})" if table.grain else ""
        note = (
            f"Không lọc và không phân nhóm theo cột văn bản nào, nên kết quả là một số gộp mọi dòng của bảng "
            f"{table.qualified_name}{grain}. Câu hỏi không nêu đối tượng thì trả theo từng đối tượng (group_by) "
            "hoặc nói rõ là số gộp."
        )
        return [note], True

    def run_sql(
        self, sql: str, purpose: str, assumption: str | None = None, rules_applied: list[str] | None = None,
        labels: dict[str, str] | None = None, chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"sql": sql, "purpose": purpose}
        extra = {"assumption": assumption, "rules_applied": rules_applied, "labels": labels, "chart": chart}
        arguments.update({key: value for key, value in extra.items() if value})
        try:
            checked = validate_select(sql, self.catalog.table_names)
        except ToolError as error:
            self._record("run_sql", arguments, sql=sql, error=str(error))
            raise

        def describe(columns: list[str], rows: list[tuple], truncated: bool) -> tuple[list, list, list[str]]:
            fields = sql_fields(self.catalog, checked, labels or {}, columns, rows)
            explanations, notes = sql_explanations(
                self.catalog, checked, purpose, assumption, rules_applied or [], truncated, len(rows), self.today,
            )
            return fields, explanations, notes

        return self._execute("run_sql", arguments, checked, [], describe, chart)

    def _next_result_id(self) -> str:
        done = sum(1 for step in self.steps if step.tool in RESULT_TOOLS and step.error is None)
        return f"{self.position}-{done + 1}"

    def _execute(
        self, tool: str, arguments: dict[str, Any], sql: str, notes: list[str], describe: Describe | None = None,
        chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.cache.run(sql)
        except ToolError as error:
            self._record(tool, arguments, sql=sql, notes=notes, error=str(error))
            raise
        rows = [[json_cell(value) for value in row] for row in result.rows]
        if describe is None:
            self._record(
                tool, arguments, sql=sql, columns=result.columns, rows=rows, row_count=len(rows),
                truncated=result.truncated, notes=notes,
            )
            shown = rows[:self.max_rows_to_llm]
            output: dict[str, Any] = {
                "sql": sql, "columns": result.columns, "rows": shown, "row_count": len(rows),
                "truncated": result.truncated or len(shown) < len(rows),
            }
            if notes:
                output["notes"] = notes
            return output
        return self._data_result(tool, arguments, sql, notes, result, describe, chart, rows)

    def _data_result(
        self, tool: str, arguments: dict[str, Any], sql: str, notes: list[str], result: QueryRows,
        describe: Describe, chart: dict[str, Any] | None, rows: list[list[Any]],
    ) -> dict[str, Any]:
        columns, renamed = unique_columns(list(result.columns))
        fields, explanations, extra = describe(columns, [tuple(row) for row in result.rows], result.truncated)
        notes = [*notes, *renamed, *extra]
        result_id = self._next_result_id()
        chart_fields = [ChartField.model_validate(_field_data(item)) for item in fields]
        complete = not result.truncated
        validated = suggest_chart(chart_fields, rows, self.question_type, self.enabled, complete)
        chart_types = compatible_types(chart_fields, rows, self.question_type, self.enabled, complete)
        source, chart_error = "auto", None
        if chart is not None:
            try:
                validated = validate_chart(chart, chart_fields, rows, result_id, complete, self.enabled)
                source = "agent"
                notes = [*notes, *validated.warnings]
            except ChartSpecError as error:
                chart_error = "; ".join(error.errors)
        spec = validated.json()
        if spec["type"] not in chart_types:
            chart_types.insert(0, spec["type"])
        display = chart_display(validated.spec, validated.stats.get("points", 0), source)
        self._record(
            tool, arguments, sql=sql, columns=columns, rows=rows, row_count=len(rows), truncated=result.truncated,
            notes=notes, result_id=result_id, fields=fields, explanations=explanations, chart=spec,
            chart_source=source, chart_types=chart_types, display=display,
        )
        shown = rows[:self.max_rows_to_llm]
        output: dict[str, Any] = {
            "result_id": result_id, "sql": sql, "columns": columns, "fields": llm_fields(fields),
            "rows": llm_rows(shown, fields, self.today), "row_count": len(rows),
            "truncated": result.truncated or len(shown) < len(rows),
        }
        if notes:
            output["notes"] = notes
        output.update({"chart": spec_summary(spec), "chart_types": chart_types, "display": display})
        if chart_error:
            output["chart_error"] = chart_error
        return output

    @staticmethod
    def _distinct_query(table: TableInfo, column: ColumnInfo) -> exp.Select:
        column_sql = exp.column(column.name, quoted=True)
        query = exp.select(column_sql).distinct().from_(exp.table_(table.name, db=table.schema, quoted=True))
        return query.where(exp.Not(this=exp.Is(this=column_sql.copy(), expression=exp.Null()))).order_by(
            column_sql.copy()
        )

    def _known_values(self, table: TableInfo, column: ColumnInfo) -> tuple[list[str], bool]:
        sql = self._distinct_query(table, column).limit(MAX_KNOWN_VALUES).sql(dialect=DIALECT)
        result = self.cache.run(sql)
        values = [str(row[0]) for row in result.rows]
        return values, result.truncated or len(values) >= MAX_KNOWN_VALUES

    def _accent_insensitive_values(
        self, table: TableInfo, column: ColumnInfo, search: str, limit: int, arguments: dict[str, Any],
    ) -> dict[str, Any]:
        wanted = normalized(search)
        values, _ = self._known_values(table, column)
        matches = [value for value in values if wanted in normalized(value)][:limit]
        note = f"Không có giá trị chứa đúng '{search.strip()}'; đã so khớp không phân biệt dấu."
        sql = self._distinct_query(table, column).limit(MAX_KNOWN_VALUES).sql(dialect=DIALECT)
        rows = [[value] for value in matches]
        self._record("get_column_values", arguments, sql=sql, columns=[column.name], rows=rows,
                     row_count=len(rows), notes=[note])
        return {"columns": [column.name], "rows": rows, "row_count": len(rows), "truncated": False, "notes": [note]}

    def _resolve_filter_values(
        self, args: QueryMetricArgs,
    ) -> tuple[QueryMetricArgs, list[str], list[ValueMatch]]:
        metric = self.catalog.metric(args.metric)
        table = self.catalog.tables[metric.table_id]
        notes: list[str] = []
        matches: list[ValueMatch] = []
        filters = []
        for item in args.filters:
            column = table.column(item.column)
            if type_category(column.data_type) != "text" or column.contains_pii or item.operator not in VALUE_OPERATORS:
                filters.append(item)
                continue
            values, partial = self._known_values(table, column)
            filters.append(self._resolved_filter(item, column, values, partial, notes, matches))
        return args.model_copy(update={"filters": filters}), notes, matches

    @staticmethod
    def _resolved_filter(
        item: FilterArg, column: ColumnInfo, values: list[str], partial: bool, notes: list[str],
        found: list[ValueMatch] | None = None,
    ) -> FilterArg:
        found = found if found is not None else []
        if item.operator in ("contains", "not_contains"):
            wanted = normalized(str(item.value))
            if item.value is None or any(str(item.value).casefold() in value.casefold() for value in values):
                return item
            matches = [value for value in values if wanted in normalized(value)]
            if not matches:
                return item
            operator = "in" if item.operator == "contains" else "not_in"
            notes.append(f"Lọc {column.name} theo {matches} (khớp '{item.value}' không phân biệt dấu).")
            found.append(ValueMatch(column.name, str(item.value), list(matches)))
            return item.model_copy(update={"operator": operator, "value": matches})
        requested = item.value if isinstance(item.value, list) else [item.value]
        by_key: dict[str, list[str]] = {}
        for value in values:
            by_key.setdefault(normalized(value), []).append(value)
        resolved = []
        for value in requested:
            text = str(value)
            if text in values:
                resolved.append(text)
                continue
            candidates = by_key.get(normalized(text), [])
            if len(candidates) == 1:
                notes.append(f"Đã đổi giá trị lọc '{text}' của cột {column.name} thành '{candidates[0]}' theo dữ liệu.")
                found.append(ValueMatch(column.name, text, [candidates[0]]))
                resolved.append(candidates[0])
                continue
            if partial:
                resolved.append(text)
                continue
            similar = [item for item in values if normalized(text) in normalized(item)][:MAX_VALUE_HINTS]
            hint = f" Giá trị gần giống: {similar}." if similar else f" Một số giá trị có: {values[:MAX_VALUE_HINTS]}."
            raise ToolError(f"Cột {column.name} không có giá trị '{text}'.{hint}")
        return item.model_copy(update={"value": resolved if isinstance(item.value, list) else resolved[0]})

    def _record(self, tool: str, arguments: dict[str, Any], **values: Any) -> None:
        self.steps.append(AgentStepOut(tool=tool, arguments=arguments, **values))

    @staticmethod
    def _metric(metric: MetricInfo) -> dict[str, Any]:
        return {
            "id": str(metric.id), "name": metric.name, "label": metric.label, "expression": metric.expression,
            "description": metric.description, "format": metric.format, "currency": metric.currency,
            "warning": metric.warning_text, "source_sql": metric.source_sql,
        }
