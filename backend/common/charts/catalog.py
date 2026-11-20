from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .spec import CHART_VERSION, PALETTE, Strict

KIND_TYPES = {"N": ("number",), "C": ("text", "boolean", "other"), "T": ("date", "datetime")}
KIND_NAMES = {"N": "số", "C": "văn bản", "T": "ngày giờ"}
ANY_KIND = frozenset({"N", "C", "T"})


class NoOptions(Strict):
    pass


class LineOptions(Strict):
    curve: Literal["linear", "monotone", "step"] = "linear"
    points: Literal["auto", "show", "hide"] = "auto"
    connect_nulls: bool = False


class DivergingOptions(Strict):
    baseline: float = 0


class WaterfallOptions(Strict):
    total: bool = True
    total_label: str = Field("Tổng", max_length=30)


class FunnelOptions(Strict):
    show_conversion: bool = True


class PieOptions(Strict):
    show_percent: bool = True


class KpiOptions(Strict):
    sparkline: bool = True
    delta_good: Literal["up", "down"] = "up"


class BulletOptions(Strict):
    target_value: float | None = None
    ranges: list[float] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def ascending(self) -> BulletOptions:
        if any(left >= right for left, right in zip(self.ranges, self.ranges[1:], strict=False)):
            raise ValueError("ranges phải tăng dần")
        return self


class HistogramOptions(Strict):
    bins: int | None = Field(None, ge=5, le=50)
    bin_width: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def one_rule(self) -> HistogramOptions:
        if self.bins is not None and self.bin_width is not None:
            raise ValueError("chỉ đặt một trong bins hoặc bin_width")
        return self


class BoxOptions(Strict):
    whisker: Literal["tukey", "minmax"] = "tukey"
    outliers: bool = True


class HeatOptions(Strict):
    midpoint: float | None = None


class ScatterOptions(Strict):
    trend: Literal["none", "linear"] = "none"


class RadarOptions(Strict):
    fill: bool = True


class SparklineOptions(Strict):
    sparkline: Literal["line", "bar"] = "line"
    show_last: bool = True


class TableOptions(Strict):
    columns: list[str] = Field(default_factory=list, max_length=50)
    heat: str | None = None


@dataclass(frozen=True)
class RoleDef:
    role: str
    required: bool
    min: int
    max: int
    accepts: frozenset[str]


@dataclass(frozen=True)
class ChartTypeDef:
    type: str
    family: str
    label: str
    roles: tuple[RoleDef, ...]
    options_model: type[BaseModel]
    aggregates: bool = True
    min_points: int = 1
    max_groups: int | None = None
    max_series: int | None = None

    def role(self, name: str) -> RoleDef | None:
        return next((item for item in self.roles if item.role == name), None)


def _role(name: str, kinds: str, required: bool = True, minimum: int = 1, maximum: int = 1) -> RoleDef:
    return RoleDef(name, required, minimum if required else 0, maximum, frozenset(kinds))


X_CT = _role("x", "CT")
X_C = _role("x", "C")
Y1 = _role("y", "N")
SERIES = _role("series", "C", required=False)

TYPES: tuple[ChartTypeDef, ...] = (
    ChartTypeDef("kpi", "Con số", "Thẻ số", (
        _role("y", "N", maximum=4), _role("compare", "N", required=False), _role("x", "T", required=False),
    ), KpiOptions),
    ChartTypeDef("bullet", "Con số", "Thanh mục tiêu", (
        Y1, _role("goal", "N", required=False), _role("x", "C", required=False),
    ), BulletOptions, max_groups=12),
    ChartTypeDef("bar", "So sánh", "Cột", (X_CT, Y1), NoOptions, max_groups=40),
    ChartTypeDef("bar_horizontal", "So sánh", "Thanh ngang", (X_C, Y1), NoOptions, max_groups=50),
    ChartTypeDef("bar_grouped", "So sánh", "Cột nhóm", (X_CT, _role("y", "N", maximum=4), SERIES), NoOptions,
                 max_groups=20, max_series=8),
    ChartTypeDef("lollipop", "So sánh", "Kẹo mút", (X_CT, Y1), NoOptions, max_groups=50),
    ChartTypeDef("dumbbell", "So sánh", "Quả tạ", (X_C, _role("y", "N", maximum=2), SERIES), NoOptions,
                 max_groups=30, max_series=2),
    ChartTypeDef("diverging_bar", "So sánh", "Thanh phân kỳ", (X_CT, Y1), DivergingOptions, max_groups=50),
    ChartTypeDef("radial_bar", "So sánh", "Thanh tròn", (X_C, Y1), NoOptions, min_points=2, max_groups=8),
    ChartTypeDef("radar", "So sánh", "Mạng nhện", (X_C, _role("y", "N", maximum=3), SERIES), RadarOptions,
                 min_points=3, max_groups=12, max_series=3),
    ChartTypeDef("bar_stacked", "Thành phần", "Cột chồng", (X_CT, _role("y", "N", maximum=8), SERIES), NoOptions,
                 max_groups=40, max_series=8),
    ChartTypeDef("bar_stacked_100", "Thành phần", "Cột chồng 100%", (X_CT, _role("y", "N", maximum=8), SERIES),
                 NoOptions, max_groups=40, max_series=8),
    ChartTypeDef("pie", "Thành phần", "Tròn", (X_C, Y1), PieOptions, min_points=2, max_groups=6),
    ChartTypeDef("donut", "Thành phần", "Vành khuyên", (X_C, Y1), PieOptions, min_points=2, max_groups=6),
    ChartTypeDef("treemap", "Thành phần", "Ô vuông", (X_C, Y1, _role("path", "C", required=False)), NoOptions,
                 max_groups=60),
    ChartTypeDef("sunburst", "Thành phần", "Vành nhiều tầng", (_role("path", "C", minimum=2, maximum=3), Y1),
                 NoOptions, max_groups=60),
    ChartTypeDef("waterfall", "Thành phần", "Thác nước", (X_CT, Y1), WaterfallOptions, max_groups=30),
    ChartTypeDef("funnel", "Thành phần", "Phễu", (X_C, Y1), FunnelOptions, min_points=2, max_groups=8),
    ChartTypeDef("line", "Xu hướng", "Đường", (_role("x", "TNC"), _role("y", "N", maximum=8), SERIES), LineOptions,
                 min_points=2, max_series=8),
    ChartTypeDef("area", "Xu hướng", "Vùng", (_role("x", "TN"), _role("y", "N", maximum=3)), LineOptions,
                 min_points=2),
    ChartTypeDef("area_stacked", "Xu hướng", "Vùng chồng", (_role("x", "T"), _role("y", "N", maximum=8), SERIES),
                 LineOptions, min_points=2, max_series=8),
    ChartTypeDef("area_stacked_100", "Xu hướng", "Vùng chồng 100%", (
        _role("x", "T"), _role("y", "N", maximum=8), SERIES,
    ), LineOptions, min_points=2, max_series=8),
    ChartTypeDef("combo", "Xu hướng", "Cột và đường", (X_CT, _role("y", "N", minimum=2, maximum=4)), NoOptions,
                 max_groups=60),
    ChartTypeDef("sparkline_table", "Xu hướng", "Bảng đường nhỏ", (_role("x", "T"), Y1, _role("series", "C")),
                 SparklineOptions, max_series=50),
    ChartTypeDef("calendar_heatmap", "Xu hướng", "Lịch nhiệt", (_role("x", "T"), _role("color", "N")), HeatOptions,
                 min_points=7, max_groups=400),
    ChartTypeDef("histogram", "Phân bố", "Tần suất", (_role("x", "N"),), HistogramOptions, aggregates=False,
                 min_points=10),
    ChartTypeDef("box_plot", "Phân bố", "Hộp", (Y1, _role("x", "C", required=False)), BoxOptions, aggregates=False,
                 min_points=5, max_groups=20),
    ChartTypeDef("heatmap", "Phân bố", "Bản đồ nhiệt", (X_CT, _role("row", "CT"), _role("color", "N")), HeatOptions,
                 max_groups=40),
    ChartTypeDef("scatter", "Quan hệ", "Phân tán", (
        _role("x", "N"), Y1, SERIES, _role("label", "C", required=False),
    ), ScatterOptions, aggregates=False, min_points=5, max_series=3),
    ChartTypeDef("bubble", "Quan hệ", "Bong bóng", (
        _role("x", "N"), Y1, _role("size", "N"), SERIES, _role("label", "C", required=False),
    ), ScatterOptions, aggregates=False, min_points=3, max_series=3),
    ChartTypeDef("sankey", "Dòng chảy", "Dòng chảy", (_role("source", "C"), _role("target", "C"), Y1), NoOptions,
                 max_groups=60),
    ChartTypeDef("table", "Bảng", "Bảng", (), TableOptions, aggregates=False, min_points=0),
)
CATALOG: dict[str, ChartTypeDef] = {item.type: item for item in TYPES}
ROLE_NAMES = ("x", "y", "series", "row", "path", "size", "color", "goal", "compare", "source", "target", "label")
MULTI_ROLES = frozenset({"y", "path"})
NO_FACET = frozenset({
    "kpi", "bullet", "pie", "donut", "treemap", "sunburst", "sankey", "funnel", "sparkline_table",
    "calendar_heatmap", "table",
})
STACKED = frozenset({"bar_stacked", "bar_stacked_100", "area_stacked", "area_stacked_100"})
NON_NEGATIVE = frozenset({
    "pie", "donut", "treemap", "sunburst", "funnel", "radial_bar", "sankey", *STACKED,
})
ADDITIVE_ONLY = frozenset({"pie", "donut", *STACKED})
TIME_AXIS = frozenset({"line", "area", "area_stacked", "area_stacked_100", "combo", "sparkline_table",
                       "calendar_heatmap"})
SHARED_AXIS = frozenset({
    "line", "area", "bar_grouped", "dumbbell", "radar", "combo", *STACKED,
})
SEQUENTIAL_OK = frozenset({"heatmap", "calendar_heatmap", "treemap", "table"})


def _accepts(kinds: frozenset[str]) -> list[str]:
    return [name for kind in ("N", "C", "T") if kind in kinds for name in KIND_TYPES[kind]]


def type_names(enabled: frozenset[str] | None = None) -> list[str]:
    return [item.type for item in TYPES if enabled is None or item.type in enabled or item.type == "table"]


def chart_catalog(enabled: frozenset[str] | None = None) -> dict[str, Any]:
    return {
        "version": CHART_VERSION, "palette": list(PALETTE), "enabled": type_names(enabled),
        "types": [
            {
                "type": item.type, "family": item.family, "label": item.label,
                "roles": [
                    {
                        "role": role.role, "required": role.required, "multiple": role.role in MULTI_ROLES,
                        "min": role.min, "max": role.max, "accepts": _accepts(role.accepts),
                    }
                    for role in item.roles
                ],
                "min_rows": item.min_points, "max_rows": item.max_groups, "max_series": item.max_series,
                "options_schema": item.options_model.model_json_schema(),
            }
            for item in TYPES
        ],
    }
