import copy
import difflib
import typing
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from .catalog import (
    ADDITIVE_ONLY,
    CATALOG,
    KIND_NAMES,
    NO_FACET,
    NON_NEGATIVE,
    SEQUENTIAL_OK,
    SHARED_AXIS,
    TIME_AXIS,
    ChartTypeDef,
    type_names,
)
from .prepare import (
    Prepared,
    dimension_key,
    is_categorical,
    measure_slots,
    prepare,
    resolved_aggregate,
)
from .profile import (
    EMPTY_LABEL,
    TEMPORAL_TYPES,
    category_key,
    field_kinds,
    folded,
    number,
    temporal_key,
)
from .spec import CHART_TYPES, TIME_UNITS, ChartField, ChartSpec, FieldRef, spec_json

MAX_ERRORS = 8
SECOND_AXIS_KEYS = ("y2", "dual_axis", "secondary_axis", "secondary_y", "y_secondary")
SECOND_AXIS = (
    "không hỗ trợ trục y thứ hai. Hai số đo khác đơn vị thì dùng facet {\"by\": \"measure\"} hoặc "
    "transform.index_to = \"first\"."
)
COLOR_ONLY = "chỉ dùng series-1…series-8 hoặc muted, không dùng mã màu."
ROLE_NOUNS = {
    "x": "cột trục x", "y": "số đo", "series": "cột series", "row": "cột hàng", "path": "cột phân cấp",
    "size": "cột kích thước", "color": "cột màu", "goal": "cột mục tiêu", "compare": "cột so sánh",
    "source": "cột nguồn", "target": "cột đích", "label": "cột nhãn điểm",
}
ROLE_ALTERNATIVES = {
    ("y", "bar"): "Dùng bar_grouped hoặc combo cho nhiều số đo.",
    ("y", "bar_horizontal"): "Dùng bar_grouped hoặc combo cho nhiều số đo.",
    ("y", "pie"): "Dùng bar_grouped cho nhiều số đo.",
    ("y", "donut"): "Dùng bar_grouped cho nhiều số đo.",
    ("x", "line"): "Dùng bar hoặc bar_horizontal.",
    ("x", "area"): "Dùng bar hoặc bar_horizontal.",
    ("x", "area_stacked"): "Dùng bar_stacked.",
    ("x", "area_stacked_100"): "Dùng bar_stacked_100.",
    ("x", "bar_horizontal"): "Dùng bar hoặc line.",
    ("x", "scatter"): "Dùng bar hoặc bar_horizontal.",
    ("x", "histogram"): "Dùng bar.",
}
MIN_ALTERNATIVES = {
    "histogram": "bar", "box_plot": "bar", "scatter": "table", "bubble": "scatter", "line": "bar", "area": "bar",
    "area_stacked": "bar_stacked", "area_stacked_100": "bar_stacked_100", "calendar_heatmap": "bar",
    "radar": "bar", "radial_bar": "bar", "pie": "bar", "donut": "bar", "funnel": "bar",
}
GROUP_NOUNS = {"pie": "lát", "donut": "lát", "funnel": "giai đoạn", "radar": "trục", "calendar_heatmap": "ngày"}
TIME_ORDER = {unit: position for position, unit in enumerate(TIME_UNITS)}
ORIENTED = frozenset({
    "bar_grouped", "bar_stacked", "bar_stacked_100", "lollipop", "dumbbell", "diverging_bar", "waterfall",
    "funnel", "bar",
})
MULTI_OR_SERIES = frozenset({
    "bar_grouped", "dumbbell", "radar", "bar_stacked", "bar_stacked_100", "area_stacked", "area_stacked_100", "line",
})
TRANSLATIONS = {
    "missing": "thiếu trường bắt buộc", "string_type": "cần chuỗi", "int_type": "cần số nguyên",
    "int_parsing": "cần số nguyên", "float_type": "cần số", "float_parsing": "cần số", "bool_type": "cần true/false",
    "bool_parsing": "cần true/false", "list_type": "cần danh sách", "dict_type": "cần object JSON",
    "model_type": "cần object JSON", "model_attributes_type": "cần object JSON",
}


class ChartSpecError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors[:MAX_ERRORS]
        super().__init__("\n".join(self.errors))


@dataclass
class ValidatedChart:
    spec: ChartSpec
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return spec_json(self.spec)


@dataclass
class Issues:
    rows_complete: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)

    def data(self, message: str) -> None:
        if self.rows_complete:
            self.error(message)
        elif message not in self.warnings:
            self.warnings.append(message)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


def vi(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if text != "-0" else "0"


def kind_name(item: ChartField) -> str:
    return {"number": "số", "date": "ngày", "datetime": "ngày giờ", "text": "văn bản", "boolean": "đúng/sai"}.get(
        item.type, "không rõ kiểu"
    )


def columns_text(fields: list[ChartField]) -> str:
    return ", ".join(f"{item.name} ({kind_name(item)})" for item in fields) or "không có cột nào"


def _path(loc: tuple[Any, ...]) -> str:
    text = ""
    for position, part in enumerate(loc):
        if isinstance(part, int):
            text += f"[{part}]"
        elif position >= 2 and loc[position - 1] == "assign":
            text += f"['{part}']"
        else:
            text += f".{part}" if text else str(part)
    return text or "chart"


def _model_at(loc: tuple[Any, ...]) -> type[BaseModel] | None:
    model: Any = ChartSpec
    for part in loc:
        if isinstance(part, int):
            continue
        if not (isinstance(model, type) and issubclass(model, BaseModel)) or part not in model.model_fields:
            return None
        model = _unwrap(model.model_fields[part].annotation)
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None


def _unwrap(annotation: Any) -> Any:
    for argument in typing.get_args(annotation) or ():
        found = _unwrap(argument)
        if isinstance(found, type) and issubclass(found, BaseModel):
            return found
    return annotation


def _pydantic_messages(error: PydanticValidationError) -> list[str]:
    messages: list[str] = []
    seen: set[str] = set()
    for item in error.errors():
        loc = tuple(part for part in item["loc"] if not (isinstance(part, str) and (
            "[" in part or part in ("bool", "int", "float", "str", "function-after")
        )))
        path = _path(loc)
        kind = item["type"]
        if kind == "extra_forbidden":
            model = _model_at(loc[:-1])
            allowed = f" Các trường hợp lệ: {', '.join(model.model_fields)}." if model is not None else ""
            message = f"{path}: không có trường này.{allowed}"
        elif kind == "literal_error" and ("color" in str(loc[-1]) or "assign" in loc):
            message = f"{path}: {COLOR_ONLY}"
        elif kind == "literal_error":
            expected = item.get("ctx", {}).get("expected", "")
            message = f"{path}: giá trị '{item.get('input')}' không hợp lệ; chỉ nhận {expected}."
        elif kind in ("string_too_long", "too_long"):
            limit = item.get("ctx", {}).get("max_length")
            unit = "ký tự" if kind == "string_too_long" else "phần tử"
            message = f"{path}: tối đa {limit} {unit}."
        elif kind in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
            ctx = item.get("ctx", {})
            sign = {"greater_than_equal": "≥", "less_than_equal": "≤", "greater_than": ">", "less_than": "<"}[kind]
            bound = next(iter(ctx.values()), "")
            message = f"{path}: phải {sign} {bound}."
        else:
            message = f"{path}: {TRANSLATIONS.get(kind, item['msg'])}."
        if path not in seen:
            seen.add(path)
            messages.append(message)
    return messages


def _similar_types(name: str) -> list[str]:
    tokens = set(str(name).lower().split("_"))

    def score(candidate: str) -> tuple[int, float]:
        shared = len(tokens & set(candidate.split("_")))
        return (-shared, -difflib.SequenceMatcher(None, str(name).lower(), candidate).ratio())

    ranked = sorted(CHART_TYPES, key=score)
    return [item for item in ranked if score(item) < (0, -0.4)][:3] or ranked[:3]


def _raw_checks(raw: dict[str, Any], issues: Issues, enabled: frozenset[str] | None) -> dict[str, Any] | None:
    data = copy.deepcopy(raw)
    if "version" in data and data["version"] != 1:
        issues.error("version: chỉ hỗ trợ 1.")
        data.pop("version")
    kind = data.get("type")
    allowed = ", ".join(type_names(enabled))
    if not kind:
        issues.error(f"type: thiếu loại biểu đồ. Các loại dùng được: {allowed}.")
        return None
    if kind not in CHART_TYPES:
        issues.error(f"type: '{kind}' không có. Các loại gần giống: {', '.join(_similar_types(kind))}.")
        return None
    if enabled is not None and kind not in enabled and kind != "table":
        issues.error(f"type: {kind} chưa được hỗ trợ ở bản này. Các loại dùng được: {allowed}.")
        return None
    for owner, path in ((data, ""), (data.get("axes"), "axes."), (data.get("encoding"), "encoding.")):
        if not isinstance(owner, dict):
            continue
        for key in SECOND_AXIS_KEYS:
            if key in owner:
                owner.pop(key)
                issues.error(f"{path}{key}: {SECOND_AXIS}")
    return data


def _refs(spec: ChartSpec) -> list[tuple[str, str, FieldRef]]:
    encoding = spec.encoding
    refs: list[tuple[str, str, FieldRef]] = []
    for role in ("x", "series", "row", "size", "color", "goal", "compare", "source", "target", "label"):
        ref = getattr(encoding, role)
        if ref is not None:
            refs.append((role, f"encoding.{role}", ref))
    refs[1:1] = [("y", f"encoding.y[{index}]", item) for index, item in enumerate(encoding.y)]
    refs.extend(("path", f"encoding.path[{index}]", item) for index, item in enumerate(encoding.path))
    return refs


def _count_text(minimum: int, maximum: int) -> str:
    return f"đúng {minimum}" if minimum == maximum else f"từ {minimum} đến {maximum}"


def _structure(spec: ChartSpec, definition: ChartTypeDef, by_name: dict[str, ChartField], result_id: str,
               fields: list[ChartField], issues: Issues) -> None:
    kind = spec.type
    encoding = spec.encoding
    target = f" {result_id}" if result_id else ""
    refs = _refs(spec)
    for _, path, ref in refs:
        if ref.field not in by_name:
            issues.error(f"{path}.field: không có cột '{ref.field}' trong kết quả{target}. "
                         f"Các cột: {columns_text(fields)}.")
    allowed_roles = {role.role for role in definition.roles}
    used = {role for role, _, _ in refs}
    for role in sorted(used - allowed_roles, key=lambda name: list(ROLE_NOUNS).index(name)):
        roles = ", ".join(item.role for item in definition.roles) or "không có"
        issues.error(f"encoding.{role}: {kind} không dùng {ROLE_NOUNS[role]}. Vai trò của {kind}: {roles}.")
    for role in definition.roles:
        count = len(encoding.y) if role.role == "y" else len(encoding.path) if role.role == "path" else int(
            getattr(encoding, role.role) is not None
        )
        if role.required and count < role.min:
            hint = ROLE_ALTERNATIVES.get((role.role, kind), "")
            needed = _count_text(role.min, role.max) if role.max > 1 else ""
            noun = f"{needed} {ROLE_NOUNS[role.role]}".strip()
            if role.role == "y" and kind in MULTI_OR_SERIES and encoding.series is not None and count >= 1:
                continue
            issues.error(f"encoding.{role.role}: {kind} cần {noun}, đang có {count}. {hint}".strip())
        elif count > role.max:
            hint = ROLE_ALTERNATIVES.get((role.role, kind), "Bỏ bớt.")
            issues.error(f"encoding.{role.role}: {kind} cần {_count_text(role.min, role.max)} "
                         f"{ROLE_NOUNS[role.role]}, đang có {count}. {hint}")
    _alternatives(spec, issues)
    for role, path, ref in refs:
        item = by_name.get(ref.field)
        definition_role = definition.role(role)
        if item is None or definition_role is None:
            continue
        if role in ("y", "size", "color", "goal", "compare"):
            aggregate = getattr(ref, "aggregate", "auto")
            if aggregate in ("count", "count_distinct"):
                continue
            if aggregate in ("sum", "avg", "min", "max") and item.type != "number":
                issues.error(f"{path}.aggregate: {aggregate} cần cột số; '{item.name}' là {kind_name(item)}. "
                             "Dùng count hoặc count_distinct.")
                continue
        if not field_kinds(item) & definition_role.accepts:
            wanted = " hoặc ".join(KIND_NAMES[name] for name in ("T", "N", "C") if name in definition_role.accepts)
            hint = ROLE_ALTERNATIVES.get((role, kind), "Chọn cột khác hoặc đổi loại biểu đồ.")
            issues.error(f"{path}: {kind} cần cột {wanted} ở {ROLE_NOUNS[role]}; '{item.name}' là "
                         f"{kind_name(item)}. {hint}")
    _duplicates(spec, issues)
    for index, item in enumerate(encoding.y):
        if item.mark is not None and kind != "combo":
            issues.error(f"encoding.y[{index}].mark: chỉ dùng cho combo. Bỏ mark hoặc đổi type thành combo.")


def _alternatives(spec: ChartSpec, issues: Issues) -> None:
    kind = spec.type
    encoding = spec.encoding
    if kind in MULTI_OR_SERIES and encoding.series is not None and len(encoding.y) > 1:
        issues.error(f"encoding.series: {kind} dùng nhiều số đo hoặc một số đo kèm series, không dùng cả hai. "
                     "Bỏ series hoặc chỉ giữ một số đo.")
    if kind in ("bar_grouped", "bar_stacked", "bar_stacked_100", "area_stacked", "area_stacked_100") and len(
        encoding.y
    ) == 1 and encoding.series is None:
        issues.error(f"encoding.y: {kind} cần từ 2 số đo trở lên hoặc một số đo kèm encoding.series. "
                     "Thêm số đo, thêm series hoặc dùng bar.")
    if kind == "dumbbell" and len(encoding.y) == 1 and encoding.series is None:
        issues.error("encoding.y: dumbbell cần đúng 2 số đo hoặc một số đo kèm series có đúng 2 giá trị. "
                     "Thêm số đo thứ hai hoặc dùng bar.")
    if kind == "bullet" and encoding.goal is None and spec.options.get("target_value") is None:
        issues.error("encoding.goal: bullet cần cột mục tiêu hoặc options.target_value. Thêm một trong hai.")
    if kind == "combo" and len(encoding.y) >= 2:
        marks = [item.mark for item in encoding.y]
        if any(mark is None for mark in marks):
            issues.error("encoding.y: combo cần mark (bar, line, area) cho mỗi số đo. Thêm mark.")
        elif "bar" not in marks or not {"line", "area"} & set(marks):
            issues.error("encoding.y: combo cần ít nhất một số đo mark bar và một số đo mark line hoặc area. "
                         "Đổi mark hoặc dùng bar_grouped, line.")


def _duplicates(spec: ChartSpec, issues: Issues) -> None:
    encoding = spec.encoding
    pairs = (("series", "x"), ("row", "x"), ("target", "source"), ("series", "row"))
    for role, other in pairs:
        left, right = getattr(encoding, role), getattr(encoding, other)
        if left is not None and right is not None and left.field == right.field:
            issues.error(f"encoding.{role}: '{left.field}' đã dùng ở encoding.{other}. Chọn cột khác hoặc bỏ {role}.")
    for name, items in (("y", encoding.y), ("path", encoding.path)):
        seen: dict[str, int] = {}
        for index, item in enumerate(items):
            if item.field in seen:
                first = seen[item.field]
                issues.error(f"encoding.{name}[{index}].field: '{item.field}' đã có ở encoding.{name}[{first}].")
            seen.setdefault(item.field, index)
    if encoding.series is not None and any(item.field == encoding.series.field for item in encoding.y):
        issues.error(f"encoding.series: '{encoding.series.field}' đã dùng ở encoding.y. Chọn cột khác.")


def _units(spec: ChartSpec, by_name: dict[str, ChartField]) -> list[str]:
    units: list[str] = []
    for item in spec.encoding.y:
        found = by_name.get(item.field)
        if found is None or item.aggregate in ("count", "count_distinct"):
            continue
        unit = (item.format.unit if item.format else None) or found.unit or ("%" if found.percent else None)
        if unit and unit not in units:
            units.append(unit)
    return units


def _semantics(spec: ChartSpec, by_name: dict[str, ChartField], issues: Issues) -> None:
    kind = spec.type
    encoding = spec.encoding
    transform = spec.transform
    x_field = by_name.get(encoding.x.field) if encoding.x else None
    if kind in ADDITIVE_ONLY:
        for item in encoding.y:
            found = by_name.get(item.field)
            if found is not None and found.additive is False and item.aggregate not in ("sum", "count",
                                                                                          "count_distinct"):
                reason = "trung bình" if "trung binh" in folded(f"{found.name} {found.label}").replace("_", " ") or \
                    "avg" in found.name.lower() else "không phải tổng"
                issues.error(f"{kind}: '{found.name}' không cộng dồn được ({reason}). Dùng bar_grouped hoặc line.")
    by_measure = spec.facet is not None and spec.facet.by == "measure"
    if kind in SHARED_AXIS and len(encoding.y) >= 2 and transform.index_to == "none" and not by_measure:
        units = _units(spec, by_name)
        if len(units) > 1:
            issues.error(f"{kind}: các số đo khác đơn vị ({', '.join(units)}) nên không vẽ chung một trục. Dùng line "
                         "với facet {\"by\": \"measure\"} hoặc transform.index_to = \"first\".")
    if transform.sort is not None:
        allowed = ["none", "x", "y", *(item.field for item in encoding.y)]
        if transform.sort.by not in allowed:
            names = ", ".join(item.field for item in encoding.y) or "không có"
            issues.error(f"transform.sort.by: phải là none, x, y hoặc một cột trong encoding.y ({names}).")
        elif transform.sort.by not in ("none", "x") and kind in TIME_AXIS and x_field is not None and (
            x_field.type in TEMPORAL_TYPES or x_field.type == "number"
        ):
            issues.error(f"transform.sort.by: {kind} có trục x thời gian luôn sắp theo thời gian. Bỏ sort hoặc đặt "
                         "\"by\": \"x\".")
    _filters(spec, by_name, issues)
    if spec.facet is not None:
        if kind in NO_FACET:
            issues.error(f"facet: không dùng cho {kind}. Dùng bar_grouped hoặc bar_stacked_100.")
        elif spec.facet.by == "series" and encoding.series is None:
            issues.error("facet: facet.by = series cần encoding.series.")
        elif spec.facet.by == "measure" and len(encoding.y) < 2:
            issues.error("facet: facet.by = measure cần ít nhất 2 số đo trong encoding.y.")
    slots = measure_slots(spec)
    for flag, path in ((transform.top_n is not None and transform.top_n.other, "transform.top_n.other"),
                       (transform.cumulative, "transform.cumulative")):
        if not flag:
            continue
        for _, item in slots:
            found = by_name.get(item.field)
            if found is None or found.additive is True or item.aggregate in ("sum", "count", "count_distinct"):
                continue
            if path == "transform.cumulative":
                issues.error(f"{path}: '{found.name}' không cộng dồn được. Bỏ cumulative hoặc đặt aggregate sum.")
            else:
                issues.error(f"{path}: không gộp 'Khác' cho '{found.name}' vì số này không cộng dồn được. "
                             "Đặt \"other\": false.")
    _colors(spec, by_name, issues)
    _time_units(spec, by_name, issues)
    _axes(spec, x_field, issues)
    _pii(spec, by_name, issues)


def _filters(spec: ChartSpec, by_name: dict[str, ChartField], issues: Issues) -> None:
    for index, rule in enumerate(spec.transform.filter):
        path = f"transform.filter[{index}]"
        found = by_name.get(rule.field)
        if found is None:
            issues.error(f"{path}.field: không có cột '{rule.field}'. Các cột: {', '.join(by_name)}.")
            continue
        values = rule.value if isinstance(rule.value, list) else [rule.value]
        if rule.op in ("in", "not_in"):
            if not isinstance(rule.value, list) or not 1 <= len(rule.value) <= 50:
                issues.error(f"{path}.value: op {rule.op} cần danh sách 1–50 giá trị, ví dụ [\"Hà Nội\", \"Huế\"].")
                continue
        elif isinstance(rule.value, list) or rule.value is None:
            issues.error(f"{path}.value: op {rule.op} cần đúng một giá trị, không phải danh sách. "
                         "Dùng in cho danh sách.")
            continue
        if rule.op in ("gt", "gte", "lt", "lte") and found.type not in ("number", *TEMPORAL_TYPES):
            issues.error(f"{path}.op: {rule.op} chỉ dùng cho cột số hoặc ngày; '{found.name}' là {kind_name(found)}.")
            continue
        for value in values:
            if found.type == "number" and number(value) is None:
                issues.error(f"{path}.value: '{found.name}' là số, '{value}' không phải số.")
            elif found.type in TEMPORAL_TYPES and (not isinstance(value, str) or temporal_key(value) is None):
                issues.error(f"{path}.value: '{found.name}' là ngày, giá trị phải dạng YYYY-MM-DD, không phải "
                             f"'{value}'.")
            elif found.type == "boolean" and not isinstance(value, bool):
                issues.error(f"{path}.value: '{found.name}' là đúng/sai, giá trị phải là true hoặc false.")
            else:
                continue
            break


def _colors(spec: ChartSpec, by_name: dict[str, ChartField], issues: Issues) -> None:
    colors = spec.colors
    owners: dict[str, str] = {}
    for index, item in enumerate(spec.encoding.y):
        if item.color is None:
            continue
        if item.color in owners:
            issues.error(f"encoding.y[{index}].color: {item.color} đã gán cho '{owners[item.color]}'. Mỗi số đo một "
                         "màu khác nhau.")
        owners.setdefault(item.color, item.field)
    for key, token in colors.assign.items():
        if token in owners:
            issues.error(f"colors.assign['{key}']: {token} đã gán cho '{owners[token]}'. Mỗi series một màu khác nhau.")
        owners.setdefault(token, key)
    kind = spec.type
    if colors.scheme == "emphasis" and not colors.highlight:
        issues.error("colors.scheme: emphasis cần colors.highlight.")
    if colors.scheme == "sequential":
        single = spec.encoding.series is None and len(spec.encoding.y) <= 1
        heat = kind == "table" and spec.options.get("heat")
        if kind not in SEQUENTIAL_OK and not single or (kind == "table" and not heat):
            issues.error(f"colors.scheme: sequential không dùng cho {kind} nhiều series. Dùng categorical.")
    if colors.scheme == "diverging" and kind not in ("heatmap", "calendar_heatmap", "diverging_bar", "table", "bar",
                                                     "bar_horizontal", "waterfall"):
        issues.error(f"colors.scheme: diverging không dùng cho {kind}. Dùng categorical.")


def _time_units(spec: ChartSpec, by_name: dict[str, ChartField], issues: Issues) -> None:
    for role in ("x", "row"):
        ref = getattr(spec.encoding, role)
        if ref is None or ref.time_unit is None or ref.field not in by_name:
            continue
        found = by_name[ref.field]
        if found.type not in TEMPORAL_TYPES:
            issues.error(f"encoding.{role}.time_unit: chỉ dùng cho cột ngày; '{found.name}' là {kind_name(found)}.")
        elif found.time_unit is not None and TIME_ORDER[ref.time_unit] < TIME_ORDER[found.time_unit]:
            issues.error(f"encoding.{role}.time_unit: cột đã gom theo {found.time_unit}, không chia nhỏ thành "
                         f"{ref.time_unit}.")


def _axes(spec: ChartSpec, x_field: ChartField | None, issues: Issues) -> None:
    for name in ("x", "y"):
        axis = getattr(spec.axes, name)
        if axis.min is not None and axis.max is not None and axis.min >= axis.max:
            issues.error(f"axes.{name}.min: phải nhỏ hơn max ({vi(axis.max)}).")
    x_numeric = x_field is not None and x_field.type == "number" and not is_categorical(x_field)
    if spec.axes.x.scale == "log" and not x_numeric:
        issues.error(f"axes.x.scale: log chỉ dùng cho trục số; trục x của {spec.type} là phân loại.")
    for collection, label in ((spec.reference_lines, "reference_lines"), (spec.reference_bands, "reference_bands")):
        for index, item in enumerate(collection):
            values = [item.value] if label == "reference_lines" else [item.start, item.end]
            numeric_axis = item.axis == "y" or x_numeric
            for value in values:
                if numeric_axis and isinstance(value, str):
                    issues.error(f"{label}[{index}]: trục {item.axis} là số, '{value}' không phải số.")
                    break
            if label == "reference_bands" and isinstance(item.start, str) != isinstance(item.end, str):
                issues.error(f"{label}[{index}]: start và end phải cùng kiểu.")
            elif label == "reference_bands" and item.start >= item.end:
                start, end = (value if isinstance(value, str) else vi(value) for value in (item.start, item.end))
                issues.error(f"{label}[{index}]: start ({start}) phải nhỏ hơn end ({end}).")


def _pii(spec: ChartSpec, by_name: dict[str, ChartField], issues: Issues) -> None:
    encoding = spec.encoding

    def pii(ref: FieldRef | None) -> ChartField | None:
        found = by_name.get(ref.field) if ref is not None else None
        return found if found is not None and found.pii else None

    if (found := pii(encoding.label)) is not None:
        issues.error(f"encoding.label: '{found.name}' là dữ liệu cá nhân, không dùng làm nhãn điểm.")
    for index, rule in enumerate(spec.transform.filter):
        found = by_name.get(rule.field)
        if found is not None and found.pii:
            issues.error(f"transform.filter[{index}]: không lọc theo giá trị của cột dữ liệu cá nhân '{found.name}'.")
    highlighted = pii(encoding.series) or pii(encoding.x)
    if highlighted is not None and spec.colors.highlight:
        issues.error(f"colors.highlight[0]: không dùng giá trị của cột dữ liệu cá nhân '{highlighted.name}'.")
    keyed = pii(encoding.series) or (pii(encoding.x) if encoding.series is None else None)
    if keyed is not None and spec.colors.assign:
        issues.error(f"colors.assign: không dùng giá trị của cột dữ liệu cá nhân '{keyed.name}'.")
    if (found := pii(encoding.x)) is not None and (
        spec.annotations or any(item.axis == "x" for item in spec.reference_lines)
    ):
        issues.error(f"annotations: không dùng giá trị của cột dữ liệu cá nhân '{found.name}'.")


def _options(spec: ChartSpec, definition: ChartTypeDef, by_name: dict[str, ChartField],
             issues: Issues) -> dict[str, Any]:
    model = definition.options_model
    allowed = ", ".join(model.model_fields) or "không có"
    try:
        options = model.model_validate(spec.options)
    except PydanticValidationError as error:
        for item in error.errors():
            path = ".".join(str(part) for part in ("options", *item["loc"]))
            if item["type"] == "extra_forbidden":
                issues.error(f"{path}: không dùng cho {spec.type}. Tùy chọn của {spec.type}: {allowed}.")
            elif item["type"] == "value_error":
                issues.error(f"options: {str(item['msg']).removeprefix('Value error, ')}.")
            else:
                issues.error(f"{path}: {TRANSLATIONS.get(item['type'], item['msg'])}.")
        return spec.options
    if spec.type == "table":
        for name in getattr(options, "columns", []):
            if name not in by_name:
                issues.error(f"options.columns: không có cột '{name}'. Các cột: {', '.join(by_name)}.")
        heat = getattr(options, "heat", None)
        if heat is not None and (heat not in by_name or by_name[heat].type != "number"):
            issues.error(f"options.heat: '{heat}' phải là một cột số.")
    return options.model_dump(mode="json", exclude_defaults=True)


def _normalized(spec: ChartSpec, by_name: dict[str, ChartField], options: dict[str, Any],
                duplicate: bool, issues: Issues) -> ChartSpec:
    encoding = spec.encoding
    updates: dict[str, Any] = {}
    for role in ("x", "series", "row", "source", "target", "label"):
        ref = getattr(encoding, role)
        if ref is None or ref.field not in by_name:
            continue
        values: dict[str, Any] = {}
        if ref.label is None:
            values["label"] = by_name[ref.field].label
        if role in ("x", "row") and ref.time_unit is None and by_name[ref.field].time_unit is not None:
            values["time_unit"] = by_name[ref.field].time_unit
        if values:
            updates[role] = ref.model_copy(update=values)
    aggregates = CATALOG[spec.type].aggregates and bool(encoding.x or encoding.row or encoding.path or
                                                         encoding.source or encoding.series)
    measures: list[Any] = []
    for index, item in enumerate(encoding.y):
        found = by_name.get(item.field)
        values = {"label": item.label or (found.label if found else item.field)}
        if item.aggregate == "auto":
            values["aggregate"] = resolved_aggregate(item, found, duplicate) if aggregates else "none"
            if values["aggregate"] == "avg":
                issues.warn(f"encoding.y[{index}]: '{item.field}' lặp khóa nên lấy trung bình (avg).")
        measures.append(item.model_copy(update=values))
    updates["y"] = measures
    for role in ("size", "color", "goal", "compare"):
        item = getattr(encoding, role)
        if item is not None:
            found = by_name.get(item.field)
            values = {"label": item.label or (found.label if found else item.field)}
            if item.aggregate == "auto":
                values["aggregate"] = resolved_aggregate(item, found, duplicate) if aggregates else "none"
            updates[role] = item.model_copy(update=values)
    updates["path"] = [
        item.model_copy(update={"label": item.label or by_name[item.field].label}) if item.field in by_name else item
        for item in encoding.path
    ]
    changes: dict[str, Any] = {"encoding": encoding.model_copy(update=updates), "options": options}
    if spec.orientation is None:
        if spec.type == "bar_horizontal":
            changes["orientation"] = "horizontal"
        elif spec.type in ORIENTED:
            changes["orientation"] = "vertical"
    return spec.model_copy(update=changes)


def _first_values(prepared: Prepared, spec: ChartSpec, x_field: ChartField) -> list[tuple[str, str, float | None]]:
    has_series = spec.encoding.series is not None
    firsts: dict[tuple[str, str], tuple[str, float | None]] = {}
    ordered = sorted(prepared.cells, key=lambda item: item.dims.get("x", ""))
    for item in ordered:
        for slot, value in item.values.items():
            if not slot.startswith("y"):
                continue
            key = (slot, item.dims.get("series", "") if has_series else "")
            firsts.setdefault(key, (item.dims.get("x", ""), value))
    return [(slot, x, value) for (slot, _), (x, value) in firsts.items()]


def _data_checks(spec: ChartSpec, definition: ChartTypeDef, by_name: dict[str, ChartField],
                 prepared: Prepared, issues: Issues) -> None:
    kind = spec.type
    encoding = spec.encoding
    stats = prepared.stats
    x_field = by_name.get(encoding.x.field) if encoding.x else None
    slots = measure_slots(spec)
    names = {slot: item.field for slot, item in slots}
    if prepared.aggregated and prepared.duplicate:
        for index, item in enumerate(encoding.y):
            if item.aggregate == "none":
                key = encoding.x.field if encoding.x else "khóa"
                distinct = len({cell.key for cell in prepared.cells})
                where = "khi không có series" if encoding.series is None else "dù đã có series"
                issues.data(f"encoding.y[{index}].aggregate: '{key}' lặp giá trị ({len(prepared.rows)} dòng, "
                            f"{distinct} giá trị khác nhau) {where}. Đặt aggregate (sum, avg, ...) hoặc thêm "
                            "encoding.series.")
    _point_limits(spec, definition, by_name, prepared, issues)
    values_by_slot: dict[str, list[float]] = {}
    if prepared.aggregated:
        for cell in prepared.cells:
            for slot, value in cell.values.items():
                if value is not None:
                    values_by_slot.setdefault(slot, []).append(value)
    else:
        index = {name: position for position, name in enumerate(by_name)}
        for slot, item in slots:
            position = index.get(item.field)
            values_by_slot[slot] = [
                value for row in prepared.rows if position is not None and position < len(row)
                if (value := number(row[position])) is not None
            ]
    if kind in NON_NEGATIVE or kind == "bubble":
        checked = ["size"] if kind == "bubble" else [slot for slot in values_by_slot if slot.startswith("y")]
        for slot in checked:
            negative = [value for value in values_by_slot.get(slot, []) if value < 0]
            if negative:
                issues.data(f"{kind}: '{names[slot]}' có giá trị âm ({vi(min(negative))}). {kind} chỉ dùng cho số "
                            "không âm; dùng diverging_bar hoặc waterfall.")
        if kind in ("pie", "donut") and stats.get("points") and sum(values_by_slot.get("y0", [])) <= 0:
            issues.data(f"{kind}: tổng '{names.get('y0')}' phải lớn hơn 0. Dùng bar hoặc table.")
    if kind == "diverging_bar" and "baseline" not in spec.options:
        values = values_by_slot.get("y0", [])
        if not (any(value < 0 for value in values) and any(value > 0 for value in values)):
            issues.data(f"diverging_bar: '{names.get('y0')}' không có cả giá trị âm lẫn dương. Đặt options.baseline "
                        "hoặc dùng bar.")
    if spec.axes.y.scale == "log":
        for slot, values in values_by_slot.items():
            if slot.startswith("y") and any(value <= 0 for value in values):
                issues.data(f"axes.y.scale: log cần mọi giá trị > 0; '{names[slot]}' có giá trị ≤ 0.")
    if spec.colors.scheme == "diverging" and "midpoint" not in spec.options and "baseline" not in spec.options:
        slot = "color" if "color" in values_by_slot else "y0"
        values = values_by_slot.get(slot, [])
        if not (any(value < 0 for value in values) and any(value > 0 for value in values)):
            issues.data(f"colors.scheme: diverging cần giá trị cả âm lẫn dương hoặc options.midpoint; "
                        f"'{names.get(slot)}' không đổi dấu. Dùng sequential.")
    if spec.transform.index_to == "first" and x_field is not None and prepared.aggregated:
        for slot, x_value, value in _first_values(prepared, spec, x_field):
            if value is None or value == 0:
                issues.data(f"transform.index_to: '{names[slot]}' bằng 0 hoặc trống ở điểm đầu ({x_value}) nên không "
                            "quy về 100 được. Bỏ index_to hoặc dùng facet {\"by\": \"measure\"}.")
    _value_refs(spec, by_name, prepared, x_field, issues)
    _graph_checks(spec, prepared, issues)
    if kind in ("pie", "donut") and stats.get("points"):
        total = sum(values_by_slot.get("y0", []))
        if total > 0 and any(0 <= value < 0.02 * total for value in values_by_slot.get("y0", [])):
            issues.warn(f"{kind}: có lát nhỏ hơn 2% tổng; cân nhắc transform.top_n hoặc bar_horizontal.")


def _point_limits(spec: ChartSpec, definition: ChartTypeDef, by_name: dict[str, ChartField],
                  prepared: Prepared, issues: Issues) -> None:
    kind = spec.type
    field_names = list(by_name)
    x_field = by_name.get(spec.encoding.x.field) if spec.encoding.x else None
    stats = prepared.stats
    encoding = spec.encoding
    points, groups, series = stats["points"], stats["groups"], stats["series"]
    alternative = MIN_ALTERNATIVES.get(kind, "bar")
    if kind in ("kpi", "bullet") and encoding.x is None and points != 1:
        issues.data(f"{kind}: cần đúng 1 dòng khi không có encoding.x, kết quả có {points} dòng. Thêm encoding.x "
                    "hoặc dùng table.")
    elif kind == "histogram" and points < definition.min_points:
        issues.data(f"histogram: cần ít nhất {definition.min_points} giá trị số, kết quả có {points} dòng. Dùng bar "
                    "hoặc table.")
    elif kind == "box_plot":
        counts: dict[str, int] = {}
        x_position = field_names.index(encoding.x.field) if encoding.x is not None and x_field is not None else None
        for row in prepared.rows:
            key = category_key(row[x_position]) if x_position is not None else ""
            counts[key] = counts.get(key, 0) + 1
        small = [key for key, count in counts.items() if count < definition.min_points]
        if not counts or small:
            where = f" (nhóm '{small[0]}')" if small and encoding.x is not None else ""
            issues.data(f"box_plot: cần ít nhất {definition.min_points} giá trị mỗi nhóm{where}. Dùng bar hoặc table.")
        if definition.max_groups and len(counts) > definition.max_groups:
            issues.data(f"box_plot: có {len(counts)} nhóm, tối đa {definition.max_groups}. Lọc bớt nhóm.")
    elif points < definition.min_points or (kind in ("radial_bar", "pie", "donut", "funnel", "radar",
                                                     "calendar_heatmap") and groups < definition.min_points):
        unit = GROUP_NOUNS.get(kind, "điểm")
        found = groups if kind in GROUP_NOUNS or kind in ("radial_bar",) else points
        issues.data(f"{kind}: cần ít nhất {definition.min_points} {unit}, kết quả có {found}. Dùng {alternative} "
                    "hoặc table.")
    if kind in ("line", "area", "area_stacked", "area_stacked_100") and encoding.x is not None and groups < 2:
        issues.data(f"{kind}: cần ít nhất 2 điểm trên trục x, kết quả có {groups}. Dùng bar hoặc kpi.")
    if definition.max_groups and kind != "box_plot" and groups > definition.max_groups:
        noun = GROUP_NOUNS.get(kind, "nhóm")
        name = encoding.x.field if encoding.x is not None else "nhóm"
        if kind in ("pie", "donut"):
            hint = (f"Thêm transform.top_n {{\"n\": {definition.max_groups - 1}, \"other\": true}} hoặc dùng "
                    "bar_horizontal.")
        elif x_field is not None and is_categorical(x_field):
            hint = f"Thêm transform.top_n {{\"n\": {min(15, definition.max_groups)}}} hoặc dùng table."
        else:
            hint = "Thêm transform.filter hoặc dùng table."
        issues.data(f"{kind}: '{name}' có {groups} giá trị, tối đa {definition.max_groups} {noun}. {hint}")
    if encoding.series is not None and definition.max_series is not None:
        if series > definition.max_series:
            issues.data(f"{kind}: encoding.series có {series} giá trị, tối đa {definition.max_series}. Bỏ series hoặc "
                        "lọc bớt.")
        if kind == "dumbbell" and series != 2:
            issues.data(f"dumbbell: encoding.series cần đúng 2 giá trị, đang có {series}. Lọc còn 2 giá trị.")
        if kind == "sparkline_table" and series < 2:
            issues.data(f"sparkline_table: cần ít nhất 2 series, đang có {series}. Dùng line.")
    if kind == "sparkline_table" and prepared.aggregated:
        counts = {}
        for cell in prepared.cells:
            if cell.has_value():
                counts[cell.dims.get("series", "")] = counts.get(cell.dims.get("series", ""), 0) + 1
        short = [key for key, count in counts.items() if count < 3]
        if short:
            issues.data(f"sparkline_table: series '{short[0]}' chỉ có {counts[short[0]]} điểm, cần ít nhất 3. Dùng "
                        "line hoặc table.")
    if kind == "heatmap" and prepared.aggregated:
        rows = {cell.dims.get("row") for cell in prepared.cells if cell.has_value()}
        if len(rows) > 40:
            issues.data(f"heatmap: encoding.row có {len(rows)} giá trị, tối đa 40. Thêm transform.filter hoặc dùng "
                        "table.")
    if spec.facet is not None and spec.facet.by == "series" and series > 12:
        issues.data(f"facet: chia theo series ra {series} ô, tối đa 12. Thêm transform.filter hoặc bỏ facet.")


def _axis_values(spec: ChartSpec, by_name: dict[str, ChartField], prepared: Prepared,
                 x_field: ChartField) -> set[str]:
    position = list(by_name).index(x_field.name)
    unit = spec.encoding.x.time_unit if spec.encoding.x else None
    values = {dimension_key(row[position], x_field, unit) for row in prepared.rows if position < len(row)}
    if x_field.type in TEMPORAL_TYPES:
        values |= {value[:10] for value in values}
    return values


def _value_refs(spec: ChartSpec, by_name: dict[str, ChartField], prepared: Prepared, x_field: ChartField | None,
                issues: Issues) -> None:
    encoding = spec.encoding
    x_values: set[str] = set()
    if x_field is not None and not (x_field.type == "number" and not is_categorical(x_field)):
        x_values = _axis_values(spec, by_name, prepared, x_field)
        for index, item in enumerate(spec.annotations):
            if category_key(item.x) not in x_values:
                issues.data(f"annotations[{index}].x: '{item.x}' không có trên trục x.")
        for index, item in enumerate(spec.reference_lines):
            if item.axis == "x" and category_key(item.value) not in x_values:
                issues.data(f"reference_lines[{index}].value: '{item.value}' không có trên trục x.")
    series_values: set[str] = set()
    if encoding.series is not None and encoding.series.field in by_name:
        position = list(by_name).index(encoding.series.field)
        series_values = {category_key(row[position]) for row in prepared.rows if position < len(row)}
    if spec.colors.assign:
        keys = series_values if encoding.series is not None else x_values | {item.field for item in encoding.y}
        for key in spec.colors.assign:
            if key not in keys and key != EMPTY_LABEL:
                shown = ", ".join(sorted(keys)[:8])
                issues.data(f"colors.assign['{key}']: không phải giá trị của series hoặc trục x. Các giá trị: {shown}.")
    pool = x_values | series_values
    for index, value in enumerate(spec.colors.highlight):
        if value in pool:
            continue
        close = [item for item in sorted(pool) if folded(item) == folded(value)]
        close = close or [item for item in sorted(pool) if folded(value) in folded(item)]
        column = encoding.series.field if encoding.series is not None and not x_values else (
            encoding.x.field if encoding.x is not None else "x"
        )
        hint = f" Giá trị gần giống: {', '.join(close[:3])}." if close else ""
        issues.data(f"colors.highlight[{index}]: '{value}' không có trong '{column}'.{hint}")


def _graph_checks(spec: ChartSpec, prepared: Prepared, issues: Issues) -> None:
    if not prepared.aggregated:
        return
    cells = [cell for cell in prepared.cells if cell.has_value()]
    if spec.type == "sankey":
        edges: dict[str, set[str]] = {}
        for cell in cells:
            source, target = cell.dims.get("source"), cell.dims.get("target")
            if source == target:
                issues.data(f"sankey: liên kết '{source}' → '{target}' tự nối. Bỏ liên kết này bằng transform.filter.")
                return
            edges.setdefault(source, set()).add(target)
        cycle = _cycle(edges)
        if cycle:
            issues.data(f"sankey: có vòng {' → '.join(cycle)}. Sankey cần luồng một chiều; dùng heatmap.")
    if spec.type in ("sunburst", "treemap") and spec.encoding.path:
        depth = len(spec.encoding.path)
        roles = [f"path{index}" for index in range(depth)]
        if spec.type == "treemap" and spec.encoding.x is not None:
            roles = [*roles, "x"]
        parents: dict[str, set[str]] = {}
        for cell in cells:
            leaf = cell.dims.get(roles[-1])
            parent = cell.dims.get(roles[-2]) if len(roles) > 1 else None
            if parent is not None:
                parents.setdefault(leaf, set()).add(parent)
        for leaf, owners in parents.items():
            if len(owners) > 1:
                shown = ", ".join(sorted(owners))
                issues.data(f"{spec.type}: lá '{leaf}' thuộc hai cha ({shown}). Thêm cột cha vào path hoặc dùng "
                            "treemap không có path.")
                return


def _cycle(edges: dict[str, set[str]]) -> list[str]:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == 1:
                return [*stack[stack.index(nxt):], nxt]
            if nxt not in state and (found := visit(nxt)):
                return found
        stack.pop()
        state[node] = 2
        return []

    for node in sorted(edges):
        if node not in state and (found := visit(node)):
            return found
    return []


def validate_chart(
    spec: dict[str, Any] | ChartSpec, fields: list[ChartField], rows: list[list[Any]], result_id: str = "",
    rows_complete: bool = True, enabled: frozenset[str] | None = None,
) -> ValidatedChart:
    issues = Issues(rows_complete)
    raw = spec_json(spec) if isinstance(spec, ChartSpec) else spec
    if not isinstance(raw, dict):
        raise ChartSpecError(["chart: phải là một object JSON có type."])
    data = _raw_checks(raw, issues, enabled)
    if data is None:
        raise ChartSpecError(issues.errors)
    try:
        parsed = ChartSpec.model_validate(data)
    except PydanticValidationError as error:
        issues.errors.extend(_pydantic_messages(error))
        raise ChartSpecError(issues.errors) from None
    by_name = {item.name: item for item in fields}
    definition = CATALOG[parsed.type]
    _structure(parsed, definition, by_name, result_id, fields, issues)
    options = _options(parsed, definition, by_name, issues)
    if issues.errors:
        raise ChartSpecError(issues.errors)
    _semantics(parsed, by_name, issues)
    if issues.errors:
        raise ChartSpecError(issues.errors)
    prepared = prepare(parsed, fields, rows)
    _data_checks(parsed, definition, by_name, prepared, issues)
    if issues.errors:
        raise ChartSpecError(issues.errors)
    normalized = _normalized(parsed, by_name, options, prepared.duplicate, issues)
    stats = prepared.stats
    if normalized.labels.show == "all" and stats.get("points", 0) > 12:
        normalized = normalized.model_copy(update={"labels": normalized.labels.model_copy(update={"show": "auto"})})
        issues.warn(f"labels.show: all với {stats['points']} điểm sẽ rối; đã đổi thành auto.")
    if stats.get("dropped_null"):
        issues.warn(f"Bỏ {stats['dropped_null']} dòng thiếu giá trị trục x hoặc số đo bắt buộc.")
    top_n = parsed.transform.top_n
    x_field = by_name.get(parsed.encoding.x.field) if parsed.encoding.x else None
    if top_n is not None and (x_field is None or not is_categorical(x_field)):
        issues.warn("transform.top_n: chỉ áp cho trục x phân loại; bỏ qua với trục này.")
    if not rows_complete:
        issues.warn(f"Kiểm trên {len(rows)} dòng đã lưu; biểu đồ chỉ vẽ {len(rows)} dòng này.")
    return ValidatedChart(normalized, issues.warnings, stats)
