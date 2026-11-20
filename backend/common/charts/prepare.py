from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .catalog import CATALOG
from .profile import (
    CATEGORY_TYPES,
    TEMPORAL_TYPES,
    category_key,
    is_non_finite,
    number,
    temporal_key,
)
from .spec import ChartField, ChartSpec, FilterSpec, Measure

DIMENSION_ROLES = ("x", "row", "path", "source", "target", "series")
MEASURE_ROLES = ("size", "color", "goal", "compare")
RAW_REQUIRED = {"scatter": ("x", "y0"), "bubble": ("x", "y0", "size"), "histogram": ("x",), "box_plot": ("y0",)}


@dataclass
class Cell:
    key: tuple[str, ...]
    dims: dict[str, str]
    values: dict[str, float | None]

    def has_value(self) -> bool:
        return any(value is not None for value in self.values.values())


@dataclass
class Prepared:
    rows: list[list[Any]]
    dropped_null: int
    aggregated: bool
    duplicate: bool = False
    cells: list[Cell] = field(default_factory=list)
    x_values: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def bucket(value: str, unit: str) -> str:
    text = value[:10]
    if unit == "day":
        return text
    if unit == "month":
        return text[:7]
    if unit == "year":
        return text[:4]
    if unit == "quarter":
        return f"{text[:4]}-Q{(int(text[5:7]) - 1) // 3 + 1}"
    day = date.fromisoformat(text)
    return (day - timedelta(days=day.weekday())).isoformat()


def measure_slots(spec: ChartSpec) -> list[tuple[str, Measure]]:
    encoding = spec.encoding
    slots = [(f"y{index}", item) for index, item in enumerate(encoding.y)]
    slots.extend((role, getattr(encoding, role)) for role in MEASURE_ROLES if getattr(encoding, role) is not None)
    return slots


def dimension_refs(spec: ChartSpec) -> list[tuple[str, Any]]:
    encoding = spec.encoding
    refs: list[tuple[str, Any]] = []
    for role in DIMENSION_ROLES:
        if role == "path":
            refs.extend((f"path{index}", item) for index, item in enumerate(encoding.path))
        elif getattr(encoding, role) is not None:
            refs.append((role, getattr(encoding, role)))
    return refs


def is_categorical(item: ChartField) -> bool:
    return item.type in CATEGORY_TYPES or (item.type == "number" and item.role == "dimension")


def _positional(item: ChartField) -> bool:
    return item.type in TEMPORAL_TYPES or item.type == "number"


def _missing(value: Any, item: ChartField) -> bool:
    if value is None:
        return True
    if item.type == "number":
        return number(value) is None
    if item.type in TEMPORAL_TYPES:
        return temporal_key(value) is None
    return False


def dimension_key(value: Any, item: ChartField, unit: str | None) -> str:
    if item.type in TEMPORAL_TYPES:
        key = temporal_key(value)
        if key is None:
            return category_key(value)
        return bucket(key, unit) if unit and unit != item.time_unit else key
    return category_key(value)


def _compare(cell: Any, item: ChartField, rule: FilterSpec) -> bool:
    if cell is None or is_non_finite(cell):
        return rule.op in ("ne", "not_in")
    wanted = rule.value if isinstance(rule.value, list) else [rule.value]
    if item.type == "number":
        left = number(cell)
        rights = [number(value) for value in wanted]
    elif item.type in TEMPORAL_TYPES:
        left = str(cell)
        rights = [None if value is None else str(value) for value in wanted]
        if rule.op in ("gt", "gte", "lt", "lte", "eq", "ne", "in", "not_in") and all(
            right is not None and len(right) == 10 for right in rights
        ):
            left = left[:10]
    else:
        left = category_key(cell)
        rights = [category_key(value) for value in wanted]
    if left is None:
        return rule.op in ("ne", "not_in")
    if rule.op == "eq":
        return left == rights[0]
    if rule.op == "ne":
        return left != rights[0]
    if rule.op == "in":
        return left in rights
    if rule.op == "not_in":
        return left not in rights
    right = rights[0]
    if right is None:
        return False
    try:
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[rule.op]
    except TypeError:
        return False


def resolved_aggregate(item: Measure, measure: ChartField | None, duplicate: bool) -> str:
    if item.aggregate != "auto":
        return item.aggregate
    if not duplicate:
        return "none"
    return "sum" if measure is not None and measure.additive is True else "avg"


def _aggregate(values: list[Any], how: str) -> float | None:
    if how == "count":
        return float(sum(value is not None and not is_non_finite(value) for value in values))
    if how == "count_distinct":
        return float(len({category_key(value) for value in values if value is not None and not is_non_finite(value)}))
    numbers = [number(value) for value in values]
    present = [value for value in numbers if value is not None]
    if how == "none":
        return numbers[0] if numbers else None
    if not present:
        return None
    if how == "sum":
        return sum(present)
    if how == "avg":
        return sum(present) / len(present)
    if how == "min":
        return min(present)
    return max(present)


def _order_key(value: str, item: ChartField | None) -> tuple[int, Any]:
    if item is not None and item.type == "number":
        try:
            return (0, float(value))
        except ValueError:
            return (1, value)
    return (0, value)


def prepare(spec: ChartSpec, fields: list[ChartField], rows: list[list[Any]]) -> Prepared:
    index = {item.name: position for position, item in enumerate(fields)}
    by_name = {item.name: item for item in fields}
    definition = CATALOG[spec.type]

    def cell(row: list[Any], name: str) -> Any:
        position = index.get(name)
        return row[position] if position is not None and position < len(row) else None

    slots = measure_slots(spec)
    dims = [(role, ref) for role, ref in dimension_refs(spec) if ref.field in by_name]
    required: list[str] = []
    for role, ref in dims:
        if role in ("x", "row") and _positional(by_name[ref.field]):
            required.append(ref.field)
    raw_slots = RAW_REQUIRED.get(spec.type, ())
    slot_fields = {slot: item.field for slot, item in slots}
    if "x" in raw_slots and spec.encoding.x is not None:
        required.append(spec.encoding.x.field)
    required.extend(slot_fields[slot] for slot in raw_slots if slot in slot_fields)
    kept = []
    dropped = 0
    for row in rows:
        if any(name in by_name and _missing(cell(row, name), by_name[name]) for name in required):
            dropped += 1
            continue
        kept.append(row)
    for rule in spec.transform.filter:
        if rule.field in by_name:
            kept = [row for row in kept if _compare(cell(row, rule.field), by_name[rule.field], rule)]
    x_ref = spec.encoding.x
    if not definition.aggregates or not dims:
        series = spec.encoding.series
        x_field = by_name.get(x_ref.field) if x_ref is not None else None
        groups = 0
        if x_field is not None and is_categorical(x_field):
            groups = len({category_key(cell(row, x_ref.field)) for row in kept})
        series_count = len({category_key(cell(row, series.field)) for row in kept}) if series is not None else 0
        return Prepared(kept, dropped, False, stats={
            "points": len(kept), "groups": groups, "series": series_count, "dropped_null": dropped,
        })
    units = {role: getattr(ref, "time_unit", None) for role, ref in dims}
    keyed: dict[tuple[str, ...], list[list[Any]]] = {}
    for row in kept:
        key = tuple(
            dimension_key(cell(row, ref.field), by_name[ref.field], units[role]) for role, ref in dims
        )
        keyed.setdefault(key, []).append(row)
    duplicate = any(len(group) > 1 for group in keyed.values())
    how = {slot: resolved_aggregate(item, by_name.get(item.field), duplicate) for slot, item in slots}
    cells = [
        Cell(
            key=key, dims={role: part for (role, _), part in zip(dims, key, strict=True)},
            values={slot: _aggregate([cell(row, item.field) for row in group], how[slot]) for slot, item in slots},
        )
        for key, group in keyed.items()
    ]
    x_field = by_name.get(x_ref.field) if x_ref is not None and x_ref.field in by_name else None
    x_values = list(dict.fromkeys(item.dims["x"] for item in cells)) if x_field is not None else []
    rank_slot = slots[0][0] if slots else None
    other_label = None
    top_n = spec.transform.top_n
    if x_field is not None and top_n is not None and is_categorical(x_field) and len(x_values) > top_n.n:
        totals = _totals(cells, "x", rank_slot)
        ranked = sorted(x_values, key=lambda value: -totals.get(value, float("-inf")))
        keep = set(ranked[:top_n.n])
        rest = [item for item in cells if item.dims["x"] not in keep]
        cells = [item for item in cells if item.dims["x"] in keep]
        x_values = [value for value in x_values if value in keep]
        if top_n.other:
            other_label = top_n.other_label
            merged: dict[tuple[str, ...], Cell] = {}
            for item in rest:
                dims_other = {**item.dims, "x": other_label}
                key = tuple(dims_other[role] for role, _ in dims)
                target = merged.setdefault(key, Cell(key, dims_other, dict.fromkeys(item.values)))
                for slot, value in item.values.items():
                    if value is not None:
                        target.values[slot] = (target.values[slot] or 0.0) + value
            cells.extend(merged.values())
            x_values.append(other_label)
    if x_field is not None:
        x_values = _sorted_x(spec, x_values, x_field, cells, other_label)
        if spec.transform.limit is not None:
            x_values = x_values[:spec.transform.limit]
        allowed = set(x_values)
        cells = [item for item in cells if item.dims["x"] in allowed]
    elif spec.transform.limit is not None:
        cells = cells[:spec.transform.limit]
    points = [item for item in cells if item.has_value()]
    if x_field is not None:
        present = {item.dims["x"] for item in points}
        x_values = [value for value in x_values if value in present]
        groups = len(x_values)
    elif spec.encoding.path:
        groups = len({item.dims[f"path{len(spec.encoding.path) - 1}"] for item in points})
    elif spec.encoding.source is not None:
        groups = len({(item.dims.get("source"), item.dims.get("target")) for item in points})
    else:
        groups = 0
    series_count = (
        len({item.dims["series"] for item in points}) if "series" in units else len(spec.encoding.y)
    )
    return Prepared(kept, dropped, True, duplicate, cells, x_values, {
        "points": len(points), "groups": groups, "series": series_count, "dropped_null": dropped,
    })


def _totals(cells: list[Cell], role: str, slot: str | None) -> dict[str, float]:
    totals: dict[str, float] = {}
    for item in cells:
        value = item.values.get(slot) if slot else None
        if value is not None:
            totals[item.dims[role]] = totals.get(item.dims[role], 0.0) + value
    return totals


def _sorted_x(
    spec: ChartSpec, values: list[str], x_field: ChartField, cells: list[Cell], other: str | None,
) -> list[str]:
    plain = [value for value in values if value != other]
    tail = [other] if other is not None and other in values else []
    sort = spec.transform.sort
    by = sort.by if sort is not None else "none"
    descending = sort is not None and sort.order == "desc"
    if by == "x" or (by == "none" and not is_categorical(x_field)):
        ordered = sorted(plain, key=lambda value: _order_key(value, x_field), reverse=by == "x" and descending)
        return ordered + tail
    if by == "none":
        return plain + tail
    slot = "y0"
    for position, item in enumerate(spec.encoding.y):
        if by == item.field:
            slot = f"y{position}"
    totals = _totals(cells, "x", slot)
    missing = float("-inf") if descending else float("inf")
    ordered = sorted(plain, key=lambda value: totals.get(value, missing), reverse=descending)
    return ordered + tail


def chart_stats(spec: ChartSpec, fields: list[ChartField], rows: list[list[Any]]) -> dict[str, int]:
    return prepare(spec, fields, rows).stats
