import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlglot import exp
from sqlglot.dialects.postgres import Postgres

from ..common.errors import Text2SqlInvalidRequest
from ..query.compiler import (
    GROUPABLE,
    ORDERED,
    OutputColumn,
    _Builder,
    _condition,
    _is_pii,
    coerce,
    quote,
    type_category,
)
from ..query.schemas import ResultColumn
from ..vector_store.ingestion.documents.context import CatalogContext, ColumnEntry
from .expression import aggregate_nodes, parse_dataset_expression, reject
from .join_schemas import JoinOption, JoinStep
from .schemas import MAX_ALIAS_LENGTH, DatasetFilter, DatasetQueryPlan, SelectItem

STEP_ALIAS = re.compile(r"^t[1-9]\d{0,2}$")
INTEGER_LITERAL = re.compile(r"^\d+$")
ROOT_ALIAS = "t1"
BASE = quote("base")
TIME_ALIAS = "time_bucket"
INVALID_JOIN = "Phương án nối không hợp lệ; hãy gọi lại plan_join để lấy phương án mới."


class _BoundPostgres(Postgres):
    class Generator(Postgres.Generator):
        def placeholder_sql(self, expression: exp.Placeholder) -> str:
            return f":{expression.name}"


def _render(tree: exp.Expression) -> str:
    return tree.sql(dialect=_BoundPostgres)


@dataclass
class DatasetCompiledQuery:
    connection_id: UUID
    join_signature: str
    root_table: str
    sql: str
    parameters: dict[str, Any]
    expanding: frozenset[str]
    columns: list[OutputColumn]
    limit: int
    grouped: bool
    pii_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Item:
    kind: str
    alias: str
    column_id: UUID | None = None
    entry: ColumnEntry | None = None
    table_alias: str | None = None
    tree: exp.Expression | None = None
    flagged: bool = False
    scan: bool = True
    aggregation: str | None = None


def normalize_alias(raw: str) -> str:
    text = unicodedata.normalize("NFKD", raw.replace("đ", "d").replace("Đ", "D"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_").lower()
    return text[:MAX_ALIAS_LENGTH].strip("_")


def _column_node(alias: str, entry: ColumnEntry) -> exp.Column:
    return exp.Column(this=exp.to_identifier(entry.column.name, quoted=True), table=exp.to_identifier(alias))


def _inside_aggregate(node: exp.Expression) -> bool:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.AggFunc):
            return True
        parent = parent.parent
    return False


class _Scope:
    def __init__(self, context: CatalogContext, join: JoinOption) -> None:
        self.context = context
        self.join = join
        self.alias_of: dict[UUID, str] = {join.root_table_id: ROOT_ALIAS}
        self.table_of: dict[str, UUID] = {ROOT_ALIAS: join.root_table_id}
        self.steps: dict[str, JoinStep] = {}
        for step in join.steps:
            if not STEP_ALIAS.match(step.alias) or step.alias in self.table_of or step.table_id in self.alias_of \
                    or step.joined_from not in self.table_of:
                raise Text2SqlInvalidRequest(INVALID_JOIN)
            self.alias_of[step.table_id] = step.alias
            self.table_of[step.alias] = step.table_id
            self.steps[step.alias] = step
        if set(join.table_ids) != set(self.alias_of) or any(item not in context.tables for item in self.alias_of):
            raise Text2SqlInvalidRequest(INVALID_JOIN)
        self.by_name: dict[str, list[str]] = {}
        for table_id, alias in self.alias_of.items():
            self.by_name.setdefault(context.tables[table_id].table.name.lower(), []).append(alias)
        self.columns_of: dict[UUID, list[ColumnEntry]] = {}
        for entry in context.columns:
            if entry.column.table_id in self.alias_of:
                self.columns_of.setdefault(entry.column.table_id, []).append(entry)

    def label(self, alias: str) -> str:
        return self.context.tables[self.table_of[alias]].qualified_name

    def source(self, alias: str) -> str:
        entry = self.context.tables[self.table_of[alias]]
        return f"{quote(entry.schema.name)}.{quote(entry.table.name)} AS {alias}"

    def entry(self, column_id: UUID) -> tuple[str, ColumnEntry]:
        entry = self.context.columns_by_id.get(column_id)
        if entry is None or entry.column.table_id not in self.alias_of:
            raise Text2SqlInvalidRequest(f"Cột {column_id} không thuộc các bảng của phương án nối.")
        return self.alias_of[entry.column.table_id], entry

    def column_sql(self, alias: str, entry: ColumnEntry) -> str:
        return f"{alias}.{quote(entry.column.name)}"

    def resolve(self, table: str, column: str) -> exp.Column:
        aliases = self.by_name.get(table.lower(), [])
        if not aliases:
            raise reject(f"bảng '{table}' không nằm trong phương án nối.")
        if len(aliases) > 1:
            raise reject(f"tên bảng '{table}' trùng giữa nhiều bảng đã nối (khác schema) nên mơ hồ.")
        column_id = self.context.columns_by_table.get(self.table_of[aliases[0]], {}).get(column.lower())
        if column_id is None:
            raise reject(f"cột '{table}.{column}' không tồn tại.")
        entry = self.context.columns_by_id[column_id]
        if _is_pii(entry):
            raise reject(f"không dùng cột dữ liệu cá nhân '{entry.label}' trong biểu thức.")
        return _column_node(aliases[0], entry)

    def path(self, alias: str) -> list[str]:
        chain = [alias]
        while chain[-1] != ROOT_ALIAS:
            chain.append(self.steps[chain[-1]].joined_from)
        return list(reversed(chain))

    def covered(self, aliases: set[str]) -> set[str]:
        return {item for alias in aliases for item in self.path(alias)}

    def multiplying_outside(self, aliases: set[str]) -> list[str]:
        covered = self.covered(aliases)
        return [alias for alias, step in self.steps.items() if step.multiplies_rows and alias not in covered]

    def multiplying_beyond(self, alias: str, others: set[str]) -> list[str]:
        if not others:
            return []
        shared = self.covered(others)
        return [item for item in self.path(alias)[1:] if self.steps[item].multiplies_rows and item not in shared]

    def check_fan_out(self, aliases: set[str], item_alias: str, safe: bool) -> None:
        beyond = {alias: self.multiplying_beyond(alias, aliases - {alias}) for alias in aliases}
        fanned = [alias for alias in sorted(aliases) if beyond[alias]]
        if len(fanned) > 1:
            branches = " và ".join(self.label(alias) for alias in fanned)
            raise Text2SqlInvalidRequest(
                f"Không tính '{item_alias}' vì một hàm tổng hợp dùng cột của {branches}, là các nhánh nối cùng làm "
                "nhân dòng: kết quả sẽ là phép nhân chéo giữa các nhánh và sai số liệu. Hãy tách thành các hàm tổng "
                "hợp riêng cho từng bảng (ví dụ SUM(a.x) + SUM(b.y)) hoặc bỏ bớt một bảng."
            )
        if fanned and not safe:
            deepest = fanned[0]
            others = ", ".join(self.label(alias) for alias in sorted(aliases - {deepest}))
            multiplied = ", ".join(self.label(alias) for alias in beyond[deepest])
            raise Text2SqlInvalidRequest(
                f"Không tính '{item_alias}' chính xác: hàm tổng hợp dùng cột của {others} cùng cột của "
                f"{self.label(deepest)}, nhưng nối {multiplied} làm nhân dòng nên mỗi giá trị của {others} bị lặp "
                f"theo số dòng của {self.label(deepest)}. Hãy chọn {self.label(deepest)} làm bảng gốc, tách thành "
                "các hàm tổng hợp riêng cho từng bảng, hoặc dùng MIN/MAX/COUNT(DISTINCT ...)."
            )

    def through_many_to_one(self, aliases: set[str]) -> list[str]:
        return sorted(
            alias for alias in aliases if any(not self.steps[item].multiplies_rows for item in self.path(alias)[1:])
        )

    def keys(self, alias: str, item_alias: str, fanned_by: list[str]) -> list[str]:
        entries = self.columns_of.get(self.table_of[alias], [])
        primary = [entry for entry in entries if entry.dictionary and entry.dictionary.is_primary_key]
        if not primary:
            primary = [
                entry for entry in entries
                if entry.dictionary and entry.dictionary.is_unique and not entry.column.is_nullable
            ][:1]
        if not primary:
            multiplied = ", ".join(self.label(item) for item in fanned_by)
            raise Text2SqlInvalidRequest(
                f"Không thể tính '{item_alias}' chính xác: nối {multiplied} làm nhân dòng nhưng bảng "
                f"{self.label(alias)} chưa khai báo khóa chính hoặc cột duy nhất NOT NULL trong data dictionary để "
                "khử trùng lặp (cột duy nhất cho phép NULL không dùng làm khóa được). Hãy chọn bảng chứa cột cần "
                "tổng hợp làm bảng gốc, bỏ bảng gây nhân dòng, dùng count_distinct/min/max, hoặc khai báo khóa chính."
            )
        return [self.column_sql(alias, entry) for entry in primary]

    def from_sql(self, on_conditions: dict[str, list[str]]) -> str:
        sql = f"FROM {self.source(ROOT_ALIAS)}"
        for alias, step in self.steps.items():
            extra = "".join(f" AND ({condition})" for condition in on_conditions.get(alias, []))
            sql += f" LEFT JOIN {self.source(alias)} ON {step.on}{extra}"
        return sql


def _number_literal(text: str) -> int | Decimal:
    if INTEGER_LITERAL.match(text):
        return int(text)
    try:
        return Decimal(text)
    except InvalidOperation:
        raise reject(f"số '{text}' không hợp lệ.") from None


class _DatasetCompiler:
    def __init__(
        self, context: CatalogContext, connection_id: UUID, join: JoinOption, plan: DatasetQueryPlan, max_rows: int,
    ) -> None:
        self.connection_id = connection_id
        self.join = join
        self.plan = plan
        self.max_rows = max_rows
        self.scope = _Scope(context, join)
        self.builder = _Builder()
        self.used_aliases: set[str] = {TIME_ALIAS}
        self.warnings: list[str] = []

    def unique_alias(self, wanted: str | None, fallback: str) -> str:
        base = (normalize_alias(wanted) if wanted else "") or normalize_alias(fallback) or "col"
        alias, suffix = base, 2
        while alias in self.used_aliases:
            alias = f"{base[:MAX_ALIAS_LENGTH - 4]}_{suffix}"
            suffix += 1
        self.used_aliases.add(alias)
        return alias

    def bind_literals(self, tree: exp.Expression) -> exp.Expression:
        for literal in list(tree.find_all(exp.Literal)):
            value = literal.this if literal.is_string else _number_literal(literal.this)
            placeholder = exp.Placeholder(this=self.builder.bind(value)[1:])
            if literal is tree:
                tree = placeholder
            else:
                literal.replace(placeholder)
        return tree

    def select_item(self, index: int, item: SelectItem) -> _Item:
        if item.expression is not None:
            tree = self.bind_literals(parse_dataset_expression(item.expression, self.scope.resolve))
            alias = self.unique_alias(item.alias, f"expr_{index}")
            if not aggregate_nodes(tree):
                return _Item("row", alias, tree=tree)
            if any(not _inside_aggregate(column) for column in tree.find_all(exp.Column)):
                raise reject(f"'{alias}' có cột nằm ngoài hàm tổng hợp; hãy nhóm theo cột đó bằng group_by.")
            return _Item("aggregate", alias, tree=tree)
        assert item.column_id is not None
        table_alias, entry = self.scope.entry(item.column_id)
        flagged = _is_pii(entry)
        table_name = self.scope.context.tables[entry.column.table_id].table.name
        if item.aggregation is None:
            alias = self.unique_alias(item.alias, f"{table_name}_{entry.column.name}")
            return _Item("column", alias, item.column_id, entry, table_alias, flagged=flagged)
        alias = self.unique_alias(item.alias, f"{item.aggregation}_{table_name}_{entry.column.name}")
        return _Item(
            "aggregate", alias, item.column_id, entry, table_alias,
            tree=self.aggregate_tree(table_alias, entry, item.aggregation),
            flagged=flagged and item.aggregation in ("min", "max"),
            scan=item.aggregation in ("min", "max"), aggregation=item.aggregation,
        )

    def aggregate_tree(self, alias: str, entry: ColumnEntry, aggregation: str) -> exp.Expression:
        category = type_category(entry.column.data_type)
        if aggregation in ("sum", "avg"):
            if _is_pii(entry):
                raise Text2SqlInvalidRequest(f"Không tính {aggregation} trên cột dữ liệu cá nhân '{entry.label}'.")
            if category != "numeric":
                raise Text2SqlInvalidRequest(f"{aggregation} chỉ dùng cho cột số ('{entry.label}').")
        if aggregation in ("min", "max") and category not in ORDERED | {"text"}:
            raise Text2SqlInvalidRequest(f"{aggregation} không dùng được cho cột '{entry.label}'.")
        column = _column_node(alias, entry)
        if aggregation == "count_distinct":
            return exp.Count(this=exp.Distinct(expressions=[column]))
        functions = {"sum": exp.Sum, "avg": exp.Avg, "min": exp.Min, "max": exp.Max, "count": exp.Count}
        return functions[aggregation](this=column)

    def time_entry(self) -> tuple[str, ColumnEntry] | None:
        time = self.plan.time
        if time is None:
            return None
        alias, entry = self.scope.entry(time.column_id)
        if type_category(entry.column.data_type) not in ("date", "timestamp"):
            raise Text2SqlInvalidRequest(f"Cột '{entry.label}' không phải cột ngày hoặc ngày giờ.")
        if _is_pii(entry):
            raise Text2SqlInvalidRequest(f"Không dùng cột dữ liệu cá nhân '{entry.label}' làm cột thời gian.")
        if time.granularity is None and time.start is None and time.end is None:
            raise Text2SqlInvalidRequest("time cần ít nhất một trong granularity, start, end.")
        if time.start is not None and time.end is not None and time.start >= time.end:
            raise Text2SqlInvalidRequest("time.start phải nhỏ hơn time.end.")
        return alias, entry

    def condition(self, filter_: DatasetFilter) -> tuple[str, str]:
        alias, entry = self.scope.entry(filter_.column_id)
        if _is_pii(entry):
            raise Text2SqlInvalidRequest(
                f"Không lọc theo cột dữ liệu cá nhân '{entry.label}' để tránh truy vết một cá nhân cụ thể."
            )
        if filter_.placement == "join" and alias == ROOT_ALIAS:
            raise Text2SqlInvalidRequest(
                f"placement=join chỉ dùng cho cột của bảng được nối; '{entry.label}' thuộc bảng gốc nên hãy dùng "
                "placement=where."
            )
        text = _condition(self.builder, entry, filter_)
        if not text.startswith(quote(entry.column.name)):
            raise Text2SqlInvalidRequest(f"Không dựng được điều kiện lọc cho cột '{entry.label}'.")
        return alias, f"{alias}.{text}"

    def compile(self) -> DatasetCompiledQuery:
        plan = self.plan
        time = self.time_entry()
        bucket: str | None = None
        if time is not None and plan.time is not None and plan.time.granularity is not None:
            bucket = f"date_trunc('{plan.time.granularity}', {self.scope.column_sql(*time)})"
            if type_category(time[1].column.data_type) == "date":
                bucket = f"CAST({bucket} AS date)"

        groups: list[tuple[UUID, str, ColumnEntry]] = []
        for column_id in plan.group_by:
            if any(column_id == item[0] for item in groups):
                raise Text2SqlInvalidRequest("group_by có cột bị trùng.")
            alias, entry = self.scope.entry(column_id)
            if type_category(entry.column.data_type) not in GROUPABLE:
                raise Text2SqlInvalidRequest(
                    f"Không hỗ trợ nhóm theo cột '{entry.label}' (kiểu {entry.column.data_type})."
                )
            groups.append((column_id, alias, entry))

        items = [self.select_item(index, item) for index, item in enumerate(plan.select, start=1)]
        grouped = bool(groups) or bucket is not None or any(item.kind == "aggregate" for item in items)
        group_ids = {column_id for column_id, _, _ in groups}
        if grouped:
            for item in items:
                if item.kind == "row":
                    raise reject(f"'{item.alias}' không có hàm tổng hợp nên không dùng được khi truy vấn có nhóm.")
                if item.kind == "column" and item.column_id not in group_ids:
                    raise Text2SqlInvalidRequest(
                        f"Cột '{item.alias}' phải nằm trong group_by hoặc được áp dụng hàm tổng hợp."
                    )

        where: list[str] = []
        on_conditions: dict[str, list[str]] = {}
        if time is not None and plan.time is not None:
            column = self.scope.column_sql(*time)
            category = type_category(time[1].column.data_type)
            if plan.time.start is not None:
                where.append(f"{column} >= {self.builder.bind(coerce(plan.time.start, category, time[1].label))}")
            if plan.time.end is not None:
                where.append(f"{column} < {self.builder.bind(coerce(plan.time.end, category, time[1].label))}")
        for filter_ in plan.filters:
            alias, text = self.condition(filter_)
            if filter_.placement == "join":
                on_conditions.setdefault(alias, []).append(text)
            else:
                where.append(text)

        source = self.scope.from_sql(on_conditions)
        if where:
            source += " WHERE " + " AND ".join(f"({condition})" for condition in where)
        limit = min(plan.limit, self.max_rows)
        if grouped:
            sql, columns = self.grouped_sql(source, items, groups, bucket, time)
        else:
            sql, columns = self.raw_sql(source, items)
            self.warnings.extend(self.join.warnings)
        sql += f" LIMIT {self.builder.bind(limit + 1)}"
        return DatasetCompiledQuery(
            connection_id=self.connection_id, join_signature=self.join.signature,
            root_table=self.scope.label(ROOT_ALIAS), sql=sql, parameters=self.builder.parameters,
            expanding=frozenset(self.builder.expanding), columns=columns, limit=limit, grouped=grouped,
            pii_columns=[column.spec.name for column in columns if column.spec.contains_pii],
            warnings=list(dict.fromkeys(self.warnings)),
        )

    def output(self, item: _Item, role: str) -> OutputColumn:
        return OutputColumn(item.alias, ResultColumn(
            name=item.alias, role=role, column_id=item.column_id, contains_pii=item.flagged,
            aggregation=item.aggregation,
        ), item.entry.column.name if item.entry is not None else item.alias, item.scan)

    def raw_sql(self, source: str, items: list[_Item]) -> tuple[str, list[OutputColumn]]:
        select: list[str] = []
        for item in items:
            if item.kind == "column":
                assert item.table_alias is not None and item.entry is not None
                expression = self.scope.column_sql(item.table_alias, item.entry)
            else:
                assert item.tree is not None
                expression = _render(item.tree)
            select.append(f"{expression} AS {quote(item.alias)}")
        columns = [self.output(item, "dimension") for item in items]
        order = self.order_by(items, None, default=[])
        sql = f"SELECT {', '.join(select)} {source}"
        if order:
            sql += " ORDER BY " + ", ".join(order)
        return sql, columns

    def grouped_sql(
        self, source: str, items: list[_Item], groups: list[tuple[UUID, str, ColumnEntry]], bucket: str | None,
        time: tuple[str, ColumnEntry] | None,
    ) -> tuple[str, list[OutputColumn]]:
        base: list[str] = []
        dimensions: list[str] = []
        outer: list[str] = []
        columns: list[OutputColumn] = []
        group_names: dict[UUID, str] = {}
        bucket_item: _Item | None = None
        if bucket is not None and time is not None and self.plan.time is not None:
            base.append(f"{bucket} AS {quote('_g0')}")
            dimensions.append(bucket)
            bucket_item = _Item("time", TIME_ALIAS, time[1].column.id, time[1], scan=False)
            outer.append(f"{quote('_g0')} AS {quote(TIME_ALIAS)}")
            columns.append(OutputColumn(TIME_ALIAS, ResultColumn(
                name=TIME_ALIAS, role="time", column_id=time[1].column.id,
            ), time[1].column.name, False))
        for position, (column_id, alias, entry) in enumerate(groups, start=1):
            expression = self.scope.column_sql(alias, entry)
            group_names[column_id] = f"_g{position}"
            base.append(f"{expression} AS {quote(group_names[column_id])}")
            dimensions.append(expression)
        selected = {item.column_id for item in items if item.kind == "column"}
        extra = [
            _Item("column", self.unique_alias(None, f"{self.scope.context.tables[entry.column.table_id].table.name}_"
                                              f"{entry.column.name}"), column_id, entry, alias, flagged=_is_pii(entry))
            for column_id, alias, entry in groups if column_id not in selected
        ]
        partitions: dict[tuple[str, ...], str] = {}
        values = 0
        for item in [*extra, *items]:
            if item.kind == "column":
                assert item.column_id is not None
                outer.append(f"{quote(group_names[item.column_id])} AS {quote(item.alias)}")
                columns.append(self.output(item, "dimension"))
                continue
            assert item.tree is not None
            for node in aggregate_nodes(item.tree):
                values += 1
                self.rewrite_aggregate(node, item.alias, f"_v{values}", base, dimensions, partitions)
            outer.append(f"{_render(item.tree)} AS {quote(item.alias)}")
            columns.append(self.output(item, "metric"))
        if not base:
            base.append(f"1 AS {quote('_row')}")
        sql = f"WITH {BASE} AS (SELECT {', '.join(base)} {source}) SELECT {', '.join(outer)} FROM {BASE}"
        names = ([quote("_g0")] if bucket_item is not None else []) + [quote(name) for name in group_names.values()]
        if names:
            sql += " GROUP BY " + ", ".join(names)
        metrics = [item for item in items if item.kind == "aggregate"]
        if bucket_item is not None:
            default = [f"{quote(TIME_ALIAS)} ASC NULLS LAST"]
        elif metrics:
            default = [f"{quote(metrics[0].alias)} DESC NULLS LAST"]
        else:
            default = [f"{quote(columns[0].alias)} ASC NULLS LAST"]
        order = self.order_by([*extra, *items], bucket_item, default)
        sql += " ORDER BY " + ", ".join(order)
        return sql, columns

    def rewrite_aggregate(
        self, node: exp.AggFunc, item_alias: str, value_name: str, base: list[str], dimensions: list[str],
        partitions: dict[tuple[str, ...], str],
    ) -> None:
        inner = node.this
        distinct = isinstance(inner, exp.Distinct)
        value = inner.expressions[0] if distinct else inner
        star = isinstance(value, exp.Star)
        tables = {column.table for column in value.find_all(exp.Column)} or {ROOT_ALIAS}
        safe = distinct or isinstance(node, (exp.Min, exp.Max))
        self.scope.check_fan_out(tables, item_alias, safe)
        fanned_by = self.scope.multiplying_outside(tables)
        needs_dedup = bool(fanned_by) and not safe
        if not safe:
            through = [alias for alias in self.scope.through_many_to_one(tables) if alias != ROOT_ALIAS]
            if through:
                labels = ", ".join(self.scope.label(alias) for alias in through)
                self.warnings.append(
                    f"'{item_alias}': cột của {labels} được tính một lần cho mỗi dòng của bảng gốc "
                    f"{self.scope.label(ROOT_ALIAS)}; nếu muốn mỗi dòng của {labels} chỉ tính một lần, hãy chọn bảng "
                    "đó làm bảng gốc hoặc dùng count_distinct."
                )
        replacement: exp.Expression
        if star:
            replacement = exp.Literal.number(1) if needs_dedup else value
        else:
            base.append(f"{_render(value)} AS {quote(value_name)}")
            replacement = exp.column(value_name, quoted=True)
        if needs_dedup:
            keys = tuple(
                key for alias in sorted(self.scope.covered(tables), key=lambda item: int(item[1:]))
                for key in self.scope.keys(alias, item_alias, fanned_by)
            )
            own = [key for alias in sorted(tables) for key in self.scope.keys(alias, item_alias, fanned_by)]
            name = partitions.get(keys)
            if name is None:
                name = f"_r{len(partitions) + 1}"
                partitions[keys] = name
                present = " AND ".join(f"{key} IS NOT NULL" for key in own)
                base.append(
                    f"CASE WHEN {present} THEN ROW_NUMBER() OVER (PARTITION BY {', '.join([*dimensions, *keys])}) "
                    f"END AS {quote(name)}"
                )
            replacement = exp.Case(ifs=[exp.If(
                this=exp.EQ(this=exp.column(name, quoted=True), expression=exp.Literal.number(1)), true=replacement,
            )])
            self.warnings.append(
                f"'{item_alias}': đã khử trùng lặp theo khóa chính vì nối "
                f"{', '.join(self.scope.label(alias) for alias in fanned_by)} làm nhân dòng."
            )
        if distinct:
            inner.set("expressions", [replacement])
        else:
            node.set("this", replacement)

    def order_by(self, items: list[_Item], bucket: _Item | None, default: list[str]) -> list[str]:
        if not self.plan.order_by:
            return default
        order: list[str] = []
        for request in self.plan.order_by:
            key = request.by.strip()
            alias: str | None = None
            if key == "time" and bucket is not None:
                alias = TIME_ALIAS
            for item in ([bucket] if bucket is not None else []) + items:
                if alias is None and (key == item.alias or normalize_alias(key) == item.alias
                                      or (item.kind == "column" and key == str(item.column_id))):
                    alias = item.alias
            if alias is None:
                raise Text2SqlInvalidRequest(
                    f"order_by '{request.by}' phải là alias một cột kết quả, \"time\" (khi có granularity) hoặc "
                    "column_id một cột được chọn."
                )
            order.append(f"{quote(alias)} {request.direction.upper()} NULLS LAST")
        return order


def compile_dataset_query(
    context: CatalogContext, connection_id: UUID, join: JoinOption, plan: DatasetQueryPlan, max_rows: int,
) -> DatasetCompiledQuery:
    return _DatasetCompiler(context, connection_id, join, plan, max_rows).compile()
