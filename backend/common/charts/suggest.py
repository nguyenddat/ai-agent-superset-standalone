from collections.abc import Callable
from typing import Any

from .catalog import CATALOG, TYPES
from .profile import ColumnProfile, ResultProfile, folded, profile
from .spec import ChartField, ChartSpec
from .validate import ChartSpecError, ValidatedChart, validate_chart

GOAL_WORDS = ("muc tieu", "target", "ke hoach", "chi tieu", "goal")
Builder = Callable[[ResultProfile], dict[str, Any] | None]


def _ref(column: ColumnProfile) -> dict[str, str]:
    return {"field": column.field.name}


def _measure(column: ColumnProfile, **extra: Any) -> dict[str, Any]:
    return {"field": column.field.name, **extra}


def _shape(data: ResultProfile) -> tuple[list[ColumnProfile], list[ColumnProfile], list[ColumnProfile]]:
    return data.by_kind("T"), data.by_kind("C"), data.by_kind("N")


def _units_differ(measures: list[ColumnProfile]) -> bool:
    units = {item.field.unit or ("%" if item.field.percent else None) for item in measures}
    return len(units - {None}) > 1


def _top(column: ColumnProfile, limit: int, other: bool) -> dict[str, Any]:
    if column.distinct <= limit:
        return {}
    return {"top_n": {"n": limit, "other": other}}


def _other_ok(measure: ColumnProfile) -> bool:
    return measure.field.additive is True


def _sorted_bar(kind: str, data: ResultProfile, limit: int) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    if not numbers:
        return None
    if texts:
        transform = {"sort": {"by": "y", "order": "desc"}, **_top(texts[0], limit, _other_ok(numbers[0]))}
        return {"type": kind, "encoding": {"x": _ref(texts[0]), "y": [_measure(numbers[0])]}, "transform": transform}
    if times and kind != "bar_horizontal":
        return {"type": kind, "encoding": {"x": _ref(times[0]), "y": [_measure(numbers[0])]}}
    return None


def _x_one(kind: str, data: ResultProfile) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    x = texts[0] if texts else times[0] if times else None
    if x is None or not numbers:
        return None
    return {"type": kind, "encoding": {"x": _ref(x), "y": [_measure(numbers[0])]}}


def _multi(kind: str, data: ResultProfile, limit: int) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    x = (times or texts or [None])[0]
    if x is None or not numbers:
        return None
    others = [item for item in texts if item is not x]
    if others and len(numbers) == 1:
        return {"type": kind, "encoding": {"x": _ref(x), "y": [_measure(numbers[0])], "series": _ref(others[0])}}
    if len(numbers) >= 2:
        return {"type": kind, "encoding": {"x": _ref(x), "y": [_measure(item) for item in numbers[:limit]]}}
    return None


def _kpi(data: ResultProfile) -> dict[str, Any] | None:
    times, _, numbers = _shape(data)
    if data.row_count == 1 and numbers:
        return {"type": "kpi", "encoding": {"y": [_measure(item) for item in numbers[:4]]}}
    if times and numbers:
        return {"type": "kpi", "encoding": {"x": _ref(times[0]), "y": [_measure(numbers[0])]}}
    return None


def _bullet(data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    goals = [item for item in numbers if any(word in folded(f"{item.field.name} {item.field.label}").replace(
        "_", " ") for word in GOAL_WORDS)]
    values = [item for item in numbers if item not in goals]
    if not goals or not values:
        return None
    encoding: dict[str, Any] = {"y": [_measure(values[0])], "goal": _measure(goals[0])}
    if texts and data.row_count > 1:
        encoding["x"] = _ref(texts[0])
    return {"type": "bullet", "encoding": encoding}


def _dumbbell(data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if not texts or not numbers:
        return None
    if len(numbers) == 2:
        return {"type": "dumbbell", "encoding": {"x": _ref(texts[0]), "y": [_measure(item) for item in numbers]}}
    if len(texts) >= 2 and texts[1].distinct == 2:
        return {"type": "dumbbell", "encoding": {
            "x": _ref(texts[0]), "y": [_measure(numbers[0])], "series": _ref(texts[1]),
        }}
    return None


def _radar(data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if not texts or not numbers:
        return None
    if len(texts) >= 2:
        return {"type": "radar", "encoding": {"x": _ref(texts[0]), "y": [_measure(numbers[0])], "series": _ref(
            texts[1])}}
    return {"type": "radar", "encoding": {"x": _ref(texts[0]), "y": [_measure(item) for item in numbers[:3]]}}


def _pie(kind: str, data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if not texts or not numbers:
        return None
    transform = {"sort": {"by": "y", "order": "desc"}}
    if texts[0].distinct > 6:
        transform["top_n"] = {"n": 5, "other": True}
    return {"type": kind, "encoding": {"x": _ref(texts[0]), "y": [_measure(numbers[0])]}, "transform": transform}


def _hierarchy(kind: str, data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if not numbers or not texts:
        return None
    ordered = sorted(texts, key=lambda item: item.distinct)
    if kind == "sunburst":
        if len(ordered) < 2:
            return None
        return {"type": kind, "encoding": {"path": [_ref(item) for item in ordered[:3]], "y": [_measure(numbers[0])]}}
    encoding: dict[str, Any] = {"x": _ref(ordered[-1]), "y": [_measure(numbers[0])]}
    if len(ordered) >= 2:
        encoding["path"] = [_ref(ordered[0])]
    return {"type": kind, "encoding": encoding}


def _line(kind: str, data: ResultProfile) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    x = (times or [None])[0]
    if x is None and kind in ("line", "area") and len(numbers) >= 2:
        return None
    if x is None or not numbers:
        return None
    if texts and len(numbers) == 1 and kind != "area":
        return {"type": kind, "encoding": {"x": _ref(x), "y": [_measure(numbers[0])], "series": _ref(texts[0])}}
    limit = 3 if kind == "area" else 8
    if kind in ("area_stacked", "area_stacked_100") and len(numbers) < 2:
        return None
    spec: dict[str, Any] = {"type": kind, "encoding": {"x": _ref(x), "y": [_measure(item) for item in
                                                                           numbers[:limit]]}}
    if len(numbers) > 1 and _units_differ(numbers[:limit]):
        if kind != "line":
            return None
        spec["facet"] = {"by": "measure"}
    return spec


def _combo(data: ResultProfile) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    x = (times or texts or [None])[0]
    if x is None or len(numbers) < 2:
        return None
    marks = ["bar", *(["line"] * (min(len(numbers), 4) - 1))]
    spec: dict[str, Any] = {"type": "combo", "encoding": {
        "x": _ref(x), "y": [_measure(item, mark=mark) for item, mark in zip(numbers, marks, strict=False)],
    }}
    if _units_differ(numbers[:4]):
        spec["transform"] = {"index_to": "first"}
    return spec


def _sparkline(data: ResultProfile) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    if not times or not texts or not numbers:
        return None
    return {"type": "sparkline_table", "encoding": {
        "x": _ref(times[0]), "y": [_measure(numbers[0])], "series": _ref(texts[0]),
    }}


def _calendar(data: ResultProfile) -> dict[str, Any] | None:
    times, _, numbers = _shape(data)
    days = [item for item in times if item.field.type == "date" and item.field.time_unit in (None, "day")]
    if not days or not numbers:
        return None
    return {"type": "calendar_heatmap", "encoding": {"x": _ref(days[0]), "color": _measure(numbers[0])}}


def _histogram(data: ResultProfile) -> dict[str, Any] | None:
    _, _, numbers = _shape(data)
    return {"type": "histogram", "encoding": {"x": _ref(numbers[0])}} if numbers else None


def _box(data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if not numbers:
        return None
    encoding: dict[str, Any] = {"y": [_measure(numbers[0])]}
    if texts:
        encoding["x"] = _ref(texts[0])
    return {"type": "box_plot", "encoding": encoding}


def _heatmap(data: ResultProfile) -> dict[str, Any] | None:
    times, texts, numbers = _shape(data)
    dims = [*texts, *times]
    if len(dims) < 2 or not numbers:
        return None
    return {"type": "heatmap", "encoding": {
        "x": _ref(dims[0]), "row": _ref(dims[1]), "color": _measure(numbers[0]),
    }}


def _scatter(kind: str, data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    needed = 3 if kind == "bubble" else 2
    if len(numbers) < needed:
        return None
    encoding: dict[str, Any] = {"x": _ref(numbers[0]), "y": [_measure(numbers[1])]}
    if kind == "bubble":
        encoding["size"] = _measure(numbers[2])
    labels = [item for item in texts if not item.field.pii]
    if labels:
        encoding["label"] = _ref(labels[0])
    return {"type": kind, "encoding": encoding}


def _sankey(data: ResultProfile) -> dict[str, Any] | None:
    _, texts, numbers = _shape(data)
    if len(texts) < 2 or not numbers:
        return None
    return {"type": "sankey", "encoding": {
        "source": _ref(texts[0]), "target": _ref(texts[1]), "y": [_measure(numbers[0])],
    }}


BUILDERS: dict[str, Builder] = {
    "kpi": _kpi,
    "bullet": _bullet,
    "bar": lambda data: _sorted_bar("bar", data, 40),
    "bar_horizontal": lambda data: _sorted_bar("bar_horizontal", data, 15),
    "bar_grouped": lambda data: _multi("bar_grouped", data, 4),
    "lollipop": lambda data: _sorted_bar("lollipop", data, 15),
    "dumbbell": _dumbbell,
    "diverging_bar": lambda data: _x_one("diverging_bar", data),
    "radial_bar": lambda data: _x_one("radial_bar", data),
    "radar": _radar,
    "bar_stacked": lambda data: _multi("bar_stacked", data, 8),
    "bar_stacked_100": lambda data: _multi("bar_stacked_100", data, 8),
    "pie": lambda data: _pie("pie", data),
    "donut": lambda data: _pie("donut", data),
    "treemap": lambda data: _hierarchy("treemap", data),
    "sunburst": lambda data: _hierarchy("sunburst", data),
    "waterfall": lambda data: _x_one("waterfall", data),
    "funnel": lambda data: _x_one("funnel", data),
    "line": lambda data: _line("line", data),
    "area": lambda data: _line("area", data),
    "area_stacked": lambda data: _line("area_stacked", data),
    "area_stacked_100": lambda data: _line("area_stacked_100", data),
    "combo": _combo,
    "sparkline_table": _sparkline,
    "calendar_heatmap": _calendar,
    "histogram": _histogram,
    "box_plot": _box,
    "heatmap": _heatmap,
    "scatter": lambda data: _scatter("scatter", data),
    "bubble": lambda data: _scatter("bubble", data),
    "sankey": _sankey,
    "table": lambda data: {"type": "table"},
}


def _preferences(data: ResultProfile, question_type: str | None) -> list[str]:
    times, texts, numbers = _shape(data)
    rows = data.row_count
    if rows == 0 or not numbers:
        order = ["table"]
    elif rows == 1:
        order = ["kpi", "bullet"]
    elif len(numbers) >= 2 and not texts and not times:
        order = ["bubble", "scatter"] if len(numbers) >= 3 else ["scatter", "histogram"]
    elif len(numbers) == 1 and texts and not times and texts[0].distinct < rows:
        order = (["heatmap", "bar_stacked", "bar_grouped", "treemap", "sunburst", "sankey"]
                 if len(texts) >= 2 else ["box_plot", "histogram"])
    elif len(numbers) == 1 and not texts and not times:
        order = ["histogram", "box_plot"]
    elif times and texts and len(numbers) == 1:
        order = ["line", "bar_grouped", "bar_stacked", "area_stacked", "bar_stacked_100", "area_stacked_100",
                 "heatmap", "sparkline_table"]
    elif times and len(numbers) == 1:
        points = times[0].distinct
        additive = numbers[0].field.additive is True
        order = (["bar", "dumbbell"] if points == 2 else
                 ["bar" if additive and points <= 31 else "line", "line", "area", "lollipop", "calendar_heatmap",
                  "kpi", "waterfall"])
    elif times and len(numbers) >= 2:
        order = ["line", "combo", "area_stacked"]
    elif texts and len(numbers) >= 2:
        order = (["table", "bar_grouped", "combo"] if _units_differ(numbers[:4]) else
                 ["bar_grouped", "bar_stacked", "dumbbell", "radar", "combo"])
    else:
        distinct = texts[0].distinct
        if distinct <= 3:
            order = ["bar", "bar_horizontal"]
        elif distinct <= 6:
            order = ["bar_horizontal", "bar"]
        elif distinct <= 50:
            order = ["bar_horizontal", "lollipop", "bar"]
        else:
            order = ["table", "bar_horizontal"]
        order += ["lollipop", "radial_bar", "treemap", "funnel", "donut", "pie", "diverging_bar", "waterfall",
                  "bullet"]
    if question_type == "T13":
        order = ["scatter", *order]
    elif question_type == "T11":
        order = ["donut", *order] if texts else order
    elif question_type == "T10" and times:
        order = [item for item in order if item in ("line", "bar")] + order
    return list(dict.fromkeys([*order, "table"]))


def _candidate(kind: str, data: ResultProfile, question_type: str | None) -> dict[str, Any] | None:
    spec = BUILDERS[kind](data)
    if spec is None:
        return None
    if question_type == "T7" and kind in ("bar_horizontal", "bar", "lollipop"):
        transform = spec.setdefault("transform", {})
        _, texts, _ = _shape(data)
        if texts and texts[0].distinct > 10:
            transform["top_n"] = {"n": 10, "other": False}
    return spec


def _checked(
    kind: str, fields: list[ChartField], rows: list[list[Any]], data: ResultProfile, question_type: str | None,
    enabled: frozenset[str] | None, rows_complete: bool = True,
) -> ValidatedChart | None:
    if enabled is not None and kind not in enabled and kind != "table":
        return None
    spec = _candidate(kind, data, question_type)
    if spec is None:
        return None
    try:
        return validate_chart(spec, fields, rows, rows_complete=rows_complete, enabled=enabled)
    except ChartSpecError:
        return None


def compatible_types(
    fields: list[ChartField], rows: list[list[Any]], question_type: str | None = None,
    enabled: frozenset[str] | None = None, rows_complete: bool = True,
) -> list[str]:
    data = profile(fields, rows)
    preferred = _preferences(data, question_type)
    ordered = [*preferred, *(item.type for item in TYPES if item.type not in preferred)]
    found = [
        kind for kind in ordered if kind != "table"
        and _checked(kind, fields, rows, data, question_type, enabled, rows_complete) is not None
    ]
    return [*found, "table"]


def suggest_chart(
    fields: list[ChartField], rows: list[list[Any]], question_type: str | None = None,
    enabled: frozenset[str] | None = None, rows_complete: bool = True,
) -> ValidatedChart:
    data = profile(fields, rows)
    for kind in _preferences(data, question_type):
        checked = _checked(kind, fields, rows, data, question_type, enabled, rows_complete)
        if checked is not None:
            return checked
    stats = {"points": len(rows), "groups": 0, "series": 0, "dropped_null": 0}
    return ValidatedChart(ChartSpec(type="table"), [], stats)


def chart_display(spec: ChartSpec | dict[str, Any] | None, points: int, source: str | None) -> str:
    kind = spec.type if isinstance(spec, ChartSpec) else (spec or {}).get("type")
    if kind in (None, "table", "kpi") or points < 3:
        return "none"
    return "chart" if source == "agent" else "chart_if_last"


def default_options(kind: str) -> dict[str, Any]:
    return CATALOG[kind].options_model().model_dump(mode="json")
