import re
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from pydantic import ValidationError

from backend.agent_package.agents.dataset_plan_agent import DatasetPlanDraft

from ..dataset.field_service import FieldTable
from ..dataset.join_graph import MAX_TABLES
from ..dataset.join_schemas import JoinOption
from ..dataset.schemas import MAX_SELECT, DatasetFilter, DatasetOrder, DatasetQueryPlan, SelectItem
from ..query.schemas import QueryTime
from ..vector_store.ingestion.documents.context import CatalogContext, ColumnEntry
from .context import AskContext
from .planner import typed_value

DEFAULT_LIMIT = 100
MAX_LISTED_NAMES = 40
UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class PlanMappingError(Exception):
    pass


@dataclass
class MappedDatasetPlan:
    root_table_id: UUID
    table_ids: list[UUID]
    plan: DatasetQueryPlan
    added_tables: list[str] = field(default_factory=list)


def dataset_plan_context(
    question: str, rewritten_question: str, today: date, tables: list[FieldTable], context: AskContext,
) -> dict:
    return {
        "question": question,
        "rewritten_question": rewritten_question,
        "today": today.isoformat(),
        "tables": [
            {
                "name": table.name, "short_name": table.name.split(".", 1)[-1], "description": table.description,
                "grain": table.grain,
                "fields": [
                    {
                        "name": item.name, "display_name": item.display_name, "data_type": item.data_type,
                        "semantic_role": item.semantic_role, "description": item.description, "unit": item.unit,
                        "contains_pii": bool(item.contains_pii),
                    }
                    for item in table.fields
                ],
            }
            for table in tables
        ],
        "expert_rules": knowledge_texts(context),
        "own_knowledge": [f"{entry.name}: {entry.definition}" for entry in context.own],
    }


def knowledge_texts(context: AskContext) -> list[str]:
    texts = [f"Thuật ngữ '{term.name}': {term.definition}" for term in context.terms]
    for rule in context.rules:
        text = f"Quy tắc '{rule.name}'"
        if rule.description:
            text += f": {rule.description}"
        if rule.conditions_text:
            text += ". Điều kiện: " + "; ".join(rule.conditions_text)
        if rule.exceptions:
            text += ". Ngoại lệ: " + "; ".join(f"{item['when']} thì {item['outcome']}" for item in rule.exceptions)
        texts.append(text)
    return texts


class _Names:
    def __init__(self, catalog: CatalogContext, tables: list[FieldTable]) -> None:
        self.catalog = catalog
        self.allowed = [table.table_id for table in tables if table.table_id in catalog.tables]
        self.full: dict[str, UUID] = {}
        self.short: dict[str, list[UUID]] = {}
        for table_id in self.allowed:
            entry = catalog.tables[table_id]
            self.full[entry.qualified_name.lower()] = table_id
            self.short.setdefault(entry.table.name.lower(), []).append(table_id)
        self.errors: list[str] = []

    def valid_tables(self) -> str:
        return ", ".join(self.catalog.tables[table_id].qualified_name for table_id in self.allowed)

    def valid_columns(self, table_id: UUID) -> str:
        entry = self.catalog.tables[table_id]
        names = [f"{entry.table.name}.{column}" for column in self.catalog.columns_by_table.get(table_id, {})]
        listed = ", ".join(names[:MAX_LISTED_NAMES])
        return listed + (", ..." if len(names) > MAX_LISTED_NAMES else "")

    def table(self, raw: str) -> UUID | None:
        name = raw.strip().lower()
        if name in self.full:
            return self.full[name]
        matches = self.short.get(name, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            choices = ", ".join(self.catalog.tables[item].qualified_name for item in matches)
            self.errors.append(f"tên bảng '{raw}' trùng giữa nhiều schema ({choices}) nên không xác định được")
            return None
        self.errors.append(f"bảng '{raw}' không có trong các bảng tìm được (hợp lệ: {self.valid_tables()})")
        return None

    def short_table(self, raw: str, full_name: str) -> UUID | None:
        matches = self.short.get(raw.strip().lower(), [])
        if len(matches) > 1:
            choices = ", ".join(self.catalog.tables[item].qualified_name for item in matches)
            self.errors.append(
                f"tên bảng '{raw}' trong '{full_name}' trùng giữa nhiều schema ({choices}) nên không xác định được"
            )
            return None
        if not matches:
            self.errors.append(
                f"cột '{full_name}' thuộc bảng '{raw}' không có trong các bảng tìm được (hợp lệ: {self.valid_tables()})"
            )
            return None
        return matches[0]

    def column(self, raw: str) -> ColumnEntry | None:
        parts = [part.strip() for part in raw.strip().split(".")]
        if len(parts) not in (2, 3) or not all(parts):
            self.errors.append(f"cột '{raw}' phải viết dạng bảng.cột")
            return None
        if len(parts) == 3:
            table_id = self.full.get(f"{parts[0]}.{parts[1]}".lower())
            if table_id is None:
                self.errors.append(f"bảng của cột '{raw}' không có trong các bảng tìm được")
                return None
        else:
            table_id = self.short_table(parts[0], raw)
            if table_id is None:
                return None
        column_id = self.catalog.columns_by_table.get(table_id, {}).get(parts[-1].lower())
        if column_id is None:
            self.errors.append(f"cột '{raw}' không tồn tại (cột hợp lệ: {self.valid_columns(table_id)})")
            return None
        return self.catalog.columns_by_id[column_id]


def _time(draft: DatasetPlanDraft, names: _Names) -> QueryTime | None:
    if draft.time is None:
        return None
    entry = names.column(draft.time.column)
    if entry is None:
        return None
    return QueryTime(
        column_id=entry.column.id, start=draft.time.start or None, end=draft.time.end or None,
        granularity=draft.time.granularity,
    )


def _select(draft: DatasetPlanDraft, names: _Names) -> list[SelectItem]:
    items: list[SelectItem] = []
    for position, item in enumerate(draft.select, start=1):
        has_column, has_expression = bool(item.column and item.column.strip()), bool(
            item.expression and item.expression.strip()
        )
        if has_column == has_expression:
            names.errors.append(f"mục select {position} cần đúng một trong column hoặc expression")
            continue
        if has_expression and item.aggregation is not None:
            names.errors.append(f"mục select {position}: aggregation chỉ dùng với column")
            continue
        if has_expression:
            items.append(SelectItem(expression=item.expression, alias=item.alias))
            continue
        entry = names.column(item.column or "")
        if entry is not None:
            items.append(SelectItem(column_id=entry.column.id, aggregation=item.aggregation, alias=item.alias))
    return items


def _order(draft: DatasetPlanDraft, names: _Names, aliases: set[str], group_ids: set[UUID]) -> list[DatasetOrder]:
    order: list[DatasetOrder] = []
    for item in draft.order_by:
        key = item.by.strip()
        if key.lower() == "time" or key in aliases or "." not in key:
            order.append(DatasetOrder(by=key, direction=item.direction))
            continue
        entry = names.column(key)
        if entry is None:
            continue
        if entry.column.id not in group_ids:
            names.errors.append(f"order_by '{key}' phải là alias một cột kết quả hoặc cột trong group_by")
            continue
        order.append(DatasetOrder(by=str(entry.column.id), direction=item.direction))
    return order


def map_dataset_plan(draft: DatasetPlanDraft, catalog: CatalogContext, tables: list[FieldTable]) -> MappedDatasetPlan:
    try:
        return _map(draft, catalog, tables)
    except ValidationError as error:
        detail = error.errors()[0]
        raise PlanMappingError(f"Kế hoạch không hợp lệ: {detail['msg']}.") from None


def _map(draft: DatasetPlanDraft, catalog: CatalogContext, tables: list[FieldTable]) -> MappedDatasetPlan:
    names = _Names(catalog, tables)
    if not draft.select:
        raise PlanMappingError("Kế hoạch không có cột nào để chọn (select rỗng).")
    if len(draft.select) > MAX_SELECT:
        raise PlanMappingError(f"Kế hoạch chọn quá {MAX_SELECT} cột.")
    table_ids = [table_id for table_id in (names.table(name) for name in draft.tables) if table_id is not None]
    root_name = (draft.root_table or "").strip()
    root_id = names.table(root_name) if root_name else None
    if not root_name:
        if len(set(table_ids)) == 1:
            root_id = table_ids[0]
        else:
            names.errors.append("kế hoạch thiếu bảng gốc (root_table)")
    select = _select(draft, names)
    group_by = [entry.column.id for entry in (names.column(name) for name in draft.group_by) if entry is not None]
    time = _time(draft, names)
    filters: list[DatasetFilter] = []
    for item in draft.filters:
        entry = names.column(item.column)
        if entry is not None:
            filters.append(DatasetFilter(
                column_id=entry.column.id, operator=item.operator, placement=item.placement,
                value=typed_value(item.value, item.operator, entry),
            ))
    aliases = {item.alias.strip() for item in draft.select if item.alias and item.alias.strip()}
    order_by = _order(draft, names, aliases, set(group_by))
    if names.errors:
        raise PlanMappingError("Kế hoạch tham chiếu tên không hợp lệ: " + "; ".join(dict.fromkeys(names.errors)) + ".")
    assert root_id is not None
    used = [root_id, *table_ids]
    used += [catalog.columns_by_id[item.column_id].column.table_id for item in select if item.column_id is not None]
    used += [catalog.columns_by_id[column_id].column.table_id for column_id in group_by]
    used += [catalog.columns_by_id[item.column_id].column.table_id for item in filters]
    if time is not None:
        used.append(catalog.columns_by_id[time.column_id].column.table_id)
    ordered = list(dict.fromkeys(used))
    if len(ordered) > MAX_TABLES:
        raise PlanMappingError(f"Kế hoạch cần nối {len(ordered)} bảng, vượt giới hạn {MAX_TABLES} bảng.")
    plan = DatasetQueryPlan(
        select=select, group_by=group_by, time=time, filters=filters, order_by=order_by,
        limit=max(1, draft.limit or DEFAULT_LIMIT),
    )
    declared = set(table_ids) | {root_id}
    added = [catalog.tables[item].qualified_name for item in ordered if item not in declared]
    return MappedDatasetPlan(root_table_id=root_id, table_ids=ordered, plan=plan, added_tables=added)


def describe_option(catalog: CatalogContext, option: JoinOption) -> dict:
    table_ids = [option.root_table_id, *(item.table_id for item in option.steps)]
    tables = [catalog.tables[table_id].label for table_id in table_ids]
    joins: list[str] = []
    for step in option.steps:
        child = catalog.columns_by_id.get(step.edge_id)
        parent_id = child.dictionary.referenced_column_id if child and child.dictionary else None
        parent = catalog.columns_by_id.get(parent_id) if parent_id else None
        if child is None or parent is None:
            joins.append(f"Nối {catalog.tables[step.table_id].label}")
            continue
        child_table = catalog.tables[child.column.table_id].label
        parent_table = catalog.tables[parent.column.table_id].label
        joins.append(
            f"{child_table} (cột {child.label}) nối tới {parent_table} (cột {parent.label})"
        )
    root = catalog.tables[option.root_table_id].label
    description = f"Bắt đầu từ {root}" + (": " + "; ".join(joins) if joins else "")
    return {
        "description": description, "root_table": root, "tables": list(dict.fromkeys(tables)), "joins": joins,
    }


def sanitize_message(message: str, catalog: CatalogContext) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            value = UUID(match.group(0))
        except ValueError:
            return "(mục nội bộ)"
        column = catalog.columns_by_id.get(value)
        if column is not None:
            return f"'{catalog.tables[column.column.table_id].table.name}.{column.column.name}'"
        table = catalog.tables.get(value)
        if table is not None:
            return f"'{table.qualified_name}'"
        metric = catalog.metrics_by_id.get(value)
        if metric is not None:
            return f"'{metric.label or metric.name}'"
        return "(mục nội bộ)"

    text = UUID_PATTERN.sub(replace, message)
    return text.replace("plan_join", "tính lại cách nối").replace("column_id", "cột")
