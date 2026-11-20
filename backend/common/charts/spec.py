from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CHART_VERSION = 1

ChartType = Literal[
    "kpi", "bullet", "bar", "bar_horizontal", "bar_grouped", "lollipop", "dumbbell", "diverging_bar", "radial_bar",
    "radar", "bar_stacked", "bar_stacked_100", "pie", "donut", "treemap", "sunburst", "waterfall", "funnel", "line",
    "area", "area_stacked", "area_stacked_100", "combo", "sparkline_table", "calendar_heatmap", "histogram",
    "box_plot", "heatmap", "scatter", "bubble", "sankey", "table",
]
CHART_TYPES: tuple[str, ...] = ChartType.__args__
PaletteToken = Literal[
    "series-1", "series-2", "series-3", "series-4", "series-5", "series-6", "series-7", "series-8", "muted",
]
PALETTE: tuple[str, ...] = PaletteToken.__args__
FieldType = Literal["number", "date", "datetime", "text", "boolean", "other"]
TimeUnit = Literal["day", "week", "month", "quarter", "year"]
TIME_UNITS: tuple[str, ...] = TimeUnit.__args__


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChartField(Strict):
    name: str
    label: str
    type: FieldType
    unit: str | None = None
    decimals: int | None = None
    percent: bool = False
    additive: bool | None = None
    role: Literal["measure", "dimension"] = "dimension"
    format_hint: Literal["plain"] | None = None
    time_unit: TimeUnit | None = None
    pii: bool = False


class NumberFormat(Strict):
    style: Literal["number", "percent", "compact"] = "number"
    decimals: int | None = Field(None, ge=0, le=4)
    percent_input: Literal["ratio", "percent"] = "ratio"
    unit: str | None = Field(None, max_length=12)


class DateFormat(Strict):
    style: Literal["auto", "day", "day_weekday", "week", "month", "quarter", "year", "datetime"] = "auto"


class FieldRef(Strict):
    field: str = Field(min_length=1, max_length=128)
    label: str | None = Field(None, max_length=80)


class Dimension(FieldRef):
    time_unit: TimeUnit | None = None


class Measure(FieldRef):
    aggregate: Literal["auto", "none", "sum", "avg", "min", "max", "count", "count_distinct"] = "auto"
    mark: Literal["bar", "line", "area"] | None = None
    color: PaletteToken | None = None
    format: NumberFormat | None = None


class Encoding(Strict):
    x: Dimension | None = None
    y: list[Measure] = Field(default_factory=list, max_length=8)
    series: FieldRef | None = None
    row: Dimension | None = None
    path: list[FieldRef] = Field(default_factory=list, max_length=3)
    size: Measure | None = None
    color: Measure | None = None
    goal: Measure | None = None
    compare: Measure | None = None
    source: FieldRef | None = None
    target: FieldRef | None = None
    label: FieldRef | None = None


class FilterSpec(Strict):
    field: str
    op: Literal["eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte"]
    value: bool | int | float | str | list[str | int | float] | None


class SortSpec(Strict):
    by: str = "none"
    order: Literal["asc", "desc"] = "desc"


class TopN(Strict):
    n: int = Field(ge=1, le=50)
    other: bool = True
    other_label: str = Field("Khác", max_length=30)


class Transform(Strict):
    filter: list[FilterSpec] = Field(default_factory=list, max_length=5)
    sort: SortSpec | None = None
    top_n: TopN | None = None
    limit: int | None = Field(None, ge=1, le=1000)
    index_to: Literal["none", "first"] = "none"
    cumulative: bool = False


class AxisSpec(Strict):
    title: str | None = Field(None, max_length=60)
    hide: bool = False
    scale: Literal["linear", "log"] = "linear"
    min: float | None = None
    max: float | None = None
    zero: bool = True
    tick_angle: Literal[0, -45, -90] = 0


class Axes(Strict):
    x: AxisSpec = AxisSpec()
    y: AxisSpec = AxisSpec()


class ReferenceLine(Strict):
    axis: Literal["x", "y"]
    value: float | str
    label: str | None = Field(None, max_length=60)
    color: PaletteToken = "muted"


class ReferenceBand(Strict):
    axis: Literal["x", "y"]
    start: float | str
    end: float | str
    label: str | None = Field(None, max_length=60)


class Annotation(Strict):
    x: float | str
    y: float | None = None
    text: str = Field(min_length=1, max_length=80)


class Legend(Strict):
    show: Literal["auto", "show", "hide"] = "auto"
    position: Literal["top", "bottom", "right"] = "bottom"


class Labels(Strict):
    show: Literal["auto", "none", "endpoints", "extremes", "all"] = "auto"


class Colors(Strict):
    scheme: Literal["categorical", "sequential", "diverging", "emphasis"] = "categorical"
    assign: dict[str, PaletteToken] = Field(default_factory=dict, max_length=8)
    highlight: list[str] = Field(default_factory=list, max_length=3)


class Facet(Strict):
    by: Literal["measure", "series"]
    columns: int = Field(2, ge=1, le=4)


class Formats(Strict):
    number: NumberFormat | None = None
    date: DateFormat = DateFormat()


class ChartSpec(Strict):
    version: Literal[1] = 1
    type: ChartType
    title: str | None = Field(None, max_length=120)
    subtitle: str | None = Field(None, max_length=200)
    encoding: Encoding = Encoding()
    transform: Transform = Transform()
    orientation: Literal["vertical", "horizontal"] | None = None
    axes: Axes = Axes()
    format: Formats = Formats()
    reference_lines: list[ReferenceLine] = Field(default_factory=list, max_length=5)
    reference_bands: list[ReferenceBand] = Field(default_factory=list, max_length=3)
    annotations: list[Annotation] = Field(default_factory=list, max_length=8)
    legend: Legend = Legend()
    labels: Labels = Labels()
    colors: Colors = Colors()
    facet: Facet | None = None
    options: dict[str, Any] = Field(default_factory=dict)


def spec_json(spec: ChartSpec) -> dict[str, Any]:
    compact = spec.model_dump(mode="json", exclude_defaults=True)
    compact.pop("version", None)
    compact.pop("type", None)
    return {"version": CHART_VERSION, "type": spec.type, **compact}


def spec_summary(spec: ChartSpec | dict[str, Any]) -> dict[str, Any]:
    data = spec_json(spec) if isinstance(spec, ChartSpec) else spec
    encoding = data.get("encoding") or {}
    summary: dict[str, Any] = {"type": data.get("type")}
    if isinstance(encoding.get("x"), dict):
        summary["x"] = encoding["x"].get("field")
    if encoding.get("y"):
        summary["y"] = [item.get("field") for item in encoding["y"] if isinstance(item, dict)]
    if isinstance(encoding.get("series"), dict):
        summary["series"] = encoding["series"].get("field")
    return summary
