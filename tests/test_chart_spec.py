import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from backend.common.charts import (
    CATALOG,
    CHART_TYPES,
    ChartField,
    ChartSpecError,
    chart_catalog,
    chart_display,
    chart_stats,
    compatible_types,
    infer_fields,
    suggest_chart,
    validate_chart,
)
from backend.common.charts.profile import profile
from backend.common.charts.suggest import BUILDERS

FIXTURES = Path(__file__).parent / "fixtures"


def field(name: str, kind: str, **extra: Any) -> ChartField:
    role = "measure" if kind == "number" else "dimension"
    return ChartField(name=name, label=extra.pop("label", name), type=kind, role=extra.pop("role", role), **extra)


DAYS = [f"2026-11-{day:02d}" for day in range(1, 11)]
CITY = [field("ten_thanh_pho", "text"), field("luong_mua", "number", unit="mm", additive=True)]
CITY_ROWS = [["Phu Quoc", 46.9], ["Hue", 8.6], ["Ha Noi", 3.2], ["Da Nang", 0.5]]
GRID = [
    field("ngay", "date"), field("vung", "text"), field("tram", "text"),
    field("a", "number", unit="mm", additive=True), field("b", "number", unit="mm", additive=True),
    field("c", "number", unit="mm", additive=True),
]
GRID_ROWS = [[day, vung, tram, index + 1, index + 2, index + 3]
             for index, (day, vung, tram) in enumerate((d, v, t) for d in DAYS for v in ("Bac", "Nam") for t in "XYZ")]
TEMPERATURE = [field("ngay", "date"), field("nhiet_do", "number", unit="°C", additive=False)]
TEMPERATURE_ROWS = [[day, 20 + index] for index, day in enumerate(DAYS)]


def errors(spec: dict[str, Any], fields: list[ChartField] | None = None, rows: list[list[Any]] | None = None,
           **options: Any) -> list[str]:
    try:
        validate_chart(spec, fields if fields is not None else CITY, rows if rows is not None else CITY_ROWS, **options)
    except ChartSpecError as error:
        return error.errors
    return []


def bar(**extra: Any) -> dict[str, Any]:
    return {"type": "bar", "encoding": {"x": {"field": "ten_thanh_pho"}, "y": [{"field": "luong_mua"}]}, **extra}


def by_x(kind: str, x: str, *measures: str, **encoding: Any) -> dict[str, Any]:
    return {"type": kind, "encoding": {"x": {"field": x}, "y": [{"field": name} for name in measures], **encoding}}


MINIMAL: dict[str, tuple[list[ChartField], list[list[Any]], dict[str, Any]]] = {
    "kpi": (CITY, [["Hue", 8.6]], {"type": "kpi", "encoding": {"y": [{"field": "luong_mua"}]}}),
    "bullet": (GRID, GRID_ROWS, by_x("bullet", "vung", "a", goal={"field": "b"})),
    "bar": (CITY, CITY_ROWS, bar()),
    "bar_horizontal": (CITY, CITY_ROWS, by_x("bar_horizontal", "ten_thanh_pho", "luong_mua")),
    "bar_grouped": (GRID, GRID_ROWS, by_x("bar_grouped", "vung", "a", "b")),
    "lollipop": (CITY, CITY_ROWS, by_x("lollipop", "ten_thanh_pho", "luong_mua")),
    "dumbbell": (GRID, GRID_ROWS, by_x("dumbbell", "vung", "a", "b")),
    "diverging_bar": (CITY, [["A", 3], ["B", -2], ["C", 1]], by_x("diverging_bar", "ten_thanh_pho", "luong_mua")),
    "radial_bar": (CITY, CITY_ROWS, by_x("radial_bar", "ten_thanh_pho", "luong_mua")),
    "radar": (GRID, GRID_ROWS, by_x("radar", "tram", "a", "b")),
    "bar_stacked": (GRID, GRID_ROWS, by_x("bar_stacked", "vung", "a", series={"field": "tram"})),
    "bar_stacked_100": (GRID, GRID_ROWS, by_x("bar_stacked_100", "vung", "a", series={"field": "tram"})),
    "pie": (CITY, CITY_ROWS, by_x("pie", "ten_thanh_pho", "luong_mua")),
    "donut": (CITY, CITY_ROWS, by_x("donut", "ten_thanh_pho", "luong_mua")),
    "treemap": (CITY, CITY_ROWS, by_x("treemap", "ten_thanh_pho", "luong_mua")),
    "sunburst": (
        [field("mien", "text"), field("tinh", "text"), field("so", "number", additive=True)],
        [["Bac", "Ha Noi", 3], ["Bac", "Hai Phong", 2], ["Trung", "Hue", 4]],
        {"type": "sunburst", "encoding": {"path": [{"field": "mien"}, {"field": "tinh"}], "y": [{"field": "so"}]}},
    ),
    "waterfall": (CITY, [["A", 3], ["B", -2], ["C", 1]], by_x("waterfall", "ten_thanh_pho", "luong_mua")),
    "funnel": (CITY, CITY_ROWS, by_x("funnel", "ten_thanh_pho", "luong_mua")),
    "line": (TEMPERATURE, TEMPERATURE_ROWS, by_x("line", "ngay", "nhiet_do")),
    "area": (TEMPERATURE, TEMPERATURE_ROWS, by_x("area", "ngay", "nhiet_do")),
    "area_stacked": (GRID, GRID_ROWS, by_x("area_stacked", "ngay", "a", series={"field": "vung"})),
    "area_stacked_100": (GRID, GRID_ROWS, by_x("area_stacked_100", "ngay", "a", series={"field": "vung"})),
    "combo": (GRID, GRID_ROWS, {"type": "combo", "encoding": {"x": {"field": "ngay"}, "y": [
        {"field": "a", "mark": "bar"}, {"field": "b", "mark": "line"}]}}),
    "sparkline_table": (GRID, GRID_ROWS, by_x("sparkline_table", "ngay", "a", series={"field": "vung"})),
    "calendar_heatmap": (GRID, GRID_ROWS, {"type": "calendar_heatmap", "encoding": {
        "x": {"field": "ngay"}, "color": {"field": "a"}}}),
    "histogram": (GRID, GRID_ROWS, {"type": "histogram", "encoding": {"x": {"field": "a"}}}),
    "box_plot": (GRID, GRID_ROWS, {"type": "box_plot", "encoding": {"x": {"field": "vung"}, "y": [{"field": "a"}]}}),
    "heatmap": (GRID, GRID_ROWS, {"type": "heatmap", "encoding": {
        "x": {"field": "ngay"}, "row": {"field": "vung"}, "color": {"field": "a"}}}),
    "scatter": (GRID, GRID_ROWS, {"type": "scatter", "encoding": {"x": {"field": "a"}, "y": [{"field": "b"}]}}),
    "bubble": (GRID, GRID_ROWS, {"type": "bubble", "encoding": {
        "x": {"field": "a"}, "y": [{"field": "b"}], "size": {"field": "c"}}}),
    "sankey": (GRID, GRID_ROWS, {"type": "sankey", "encoding": {
        "source": {"field": "vung"}, "target": {"field": "tram"}, "y": [{"field": "a"}]}}),
    "table": (CITY, CITY_ROWS, {"type": "table"}),
}


class MinimalSpecTests(unittest.TestCase):
    def test_every_type_has_a_valid_minimal_spec(self) -> None:
        self.assertEqual(set(MINIMAL), set(CHART_TYPES))
        self.assertEqual(len(CHART_TYPES), 32)
        for kind, (fields, rows, spec) in MINIMAL.items():
            with self.subTest(kind=kind):
                self.assertEqual(errors(spec, fields, rows), [])
                self.assertEqual(validate_chart(spec, fields, rows).spec.type, kind)

    def test_catalog_lists_every_type_with_options_schema(self) -> None:
        catalog = chart_catalog(None)
        self.assertEqual(catalog["version"], 1)
        self.assertEqual([item["type"] for item in catalog["types"]], list(CATALOG))
        self.assertTrue(all("options_schema" in item and item["label"] for item in catalog["types"]))
        self.assertNotIn("#", json.dumps(catalog["palette"]))


class RuleTests(unittest.TestCase):
    def assertError(self, found: list[str], *parts: str) -> None:
        self.assertTrue(found, "spec phải bị từ chối")
        for part in parts:
            self.assertTrue(any(part in message for message in found), f"thiếu '{part}' trong {found}")

    def test_v1_pydantic_paths_and_unknown_keys(self) -> None:
        self.assertError(errors(bar(axes={"y2": {"title": "x"}})), "axes.y2: không hỗ trợ trục y thứ hai")
        self.assertError(errors(bar(title="x" * 121)), "title: tối đa 120")
        self.assertError(errors(bar(bogus=1)), "bogus: không có trường này")
        spec = bar()
        spec["encoding"]["y"][0]["aggregate"] = "median"
        self.assertError(errors(spec), "encoding.y[0].aggregate: giá trị 'median' không hợp lệ")
        self.assertError(errors("bar"), "chart: phải là một object JSON")

    def test_v2_version(self) -> None:
        self.assertEqual(errors(bar(version=2)), ["version: chỉ hỗ trợ 1."])

    def test_v3_unknown_type_suggests_similar(self) -> None:
        self.assertError(errors(bar(type="stacked_bar")), "type: 'stacked_bar' không có", "bar_stacked")
        self.assertError(errors({"encoding": {}}), "type: thiếu loại biểu đồ")

    def test_v4_missing_column_lists_columns(self) -> None:
        spec = bar()
        spec["encoding"]["y"][0]["field"] = "tong"
        self.assertEqual(
            errors(spec, result_id="1-2"),
            [("encoding.y[0].field: không có cột 'tong' trong kết quả 1-2. "
              "Các cột: ten_thanh_pho (văn bản), luong_mua (số).")],
        )

    def test_v5_role_counts(self) -> None:
        found = errors(by_x("bar", "vung", "a", "b"), GRID, GRID_ROWS)
        self.assertError(found, "encoding.y: bar cần đúng 1 số đo, đang có 2")
        self.assertError(errors({"type": "bar", "encoding": {"y": [{"field": "luong_mua"}]}}), "encoding.x: bar cần")
        self.assertError(errors(bar() | {"encoding": {**bar()["encoding"], "size": {"field": "luong_mua"}}}),
                         "encoding.size: bar không dùng")

    def test_v6_column_kind_must_fit_role(self) -> None:
        found = errors(by_x("area", "ten_thanh_pho", "luong_mua"))
        self.assertError(found, "encoding.x: area cần cột", "'ten_thanh_pho' là văn bản")

    def test_v7_duplicate_keys_without_aggregate(self) -> None:
        spec = by_x("bar", "vung", "a")
        spec["encoding"]["y"][0]["aggregate"] = "none"
        self.assertError(errors(spec, GRID, GRID_ROWS), "encoding.y[0].aggregate: 'vung' lặp giá trị")

    def test_v8_point_limits(self) -> None:
        self.assertError(errors({"type": "histogram", "encoding": {"x": {"field": "luong_mua"}}}),
                         "histogram: cần ít nhất 10 giá trị số, kết quả có 4 dòng")
        self.assertError(errors(by_x("line", "ngay", "nhiet_do"), TEMPERATURE, TEMPERATURE_ROWS[:1]), "line: cần")

    def test_v8_counts_points_after_dropping_nulls(self) -> None:
        rows = [*TEMPERATURE_ROWS[:1], [None, 5], ["2026-11-03", None]]
        self.assertError(errors(by_x("line", "ngay", "nhiet_do"), TEMPERATURE, rows), "line: cần")

    def test_v9_group_and_series_limits(self) -> None:
        rows = [[f"T{index}", index + 1] for index in range(12)]
        self.assertError(errors(by_x("pie", "ten_thanh_pho", "luong_mua"), CITY, rows),
                         "pie: 'ten_thanh_pho' có 12 giá trị, tối đa 6 lát", 'transform.top_n {"n": 5, "other": true}')
        many = [[DAYS[0], f"V{index}", "X", 1, 1, 1] for index in range(10)]
        self.assertError(errors(by_x("bar_grouped", "ngay", "a", series={"field": "vung"}), GRID, many),
                         "encoding.series có 10 giá trị, tối đa 8")

    def test_v10_negative_values(self) -> None:
        self.assertError(errors(by_x("pie", "ten_thanh_pho", "luong_mua"), CITY, [["A", 3], ["B", -3.2]]),
                         "pie: 'luong_mua' có giá trị âm (-3,2)")

    def test_v11_stacking_needs_additive(self) -> None:
        fields = [field("vung", "text"), field("tram", "text"),
                  field("nhiet_do_trung_binh", "number", unit="°C", additive=False)]
        rows = [["A", "X", 20], ["A", "Y", 21], ["B", "X", 22]]
        spec = by_x("bar_stacked", "vung", "nhiet_do_trung_binh", series={"field": "tram"})
        self.assertError(errors(spec, fields, rows),
                         "bar_stacked: 'nhiet_do_trung_binh' không cộng dồn được (trung bình)")

    def test_v12_units_must_match_on_one_axis(self) -> None:
        fields = [*TEMPERATURE, field("luong_mua", "number", unit="mm", additive=True)]
        rows = [[*row, index] for index, row in enumerate(TEMPERATURE_ROWS)]
        spec = {"type": "combo", "encoding": {"x": {"field": "ngay"}, "y": [
            {"field": "luong_mua", "mark": "bar"}, {"field": "nhiet_do", "mark": "line"}]}}
        self.assertError(errors(spec, fields, rows), "combo: các số đo khác đơn vị (mm, °C)")
        self.assertEqual(errors(spec | {"transform": {"index_to": "first"}}, fields, [[*row, 1] for row in
                                                                                       TEMPERATURE_ROWS]), [])

    def test_v13_log_scale_needs_positive(self) -> None:
        found = errors(bar(axes={"y": {"scale": "log"}}), CITY, [["A", 3], ["B", 0]])
        self.assertError(found, "axes.y.scale: log cần mọi giá trị > 0; 'luong_mua' có giá trị ≤ 0.")

    def test_v14_axes_and_reference_lines(self) -> None:
        self.assertError(errors(bar(axes={"y": {"min": 10, "max": 5}})), "axes.y.min: phải nhỏ hơn max")
        self.assertError(errors(bar(reference_lines=[{"axis": "y", "value": "30 độ"}])),
                         "reference_lines[0]: trục y là số, '30 độ' không phải số.")

    def test_v15_annotation_must_be_on_axis(self) -> None:
        spec = by_x("line", "ngay", "nhiet_do") | {"annotations": [{"x": "2026-11-31", "text": "x"}]}
        self.assertError(errors(spec, TEMPERATURE, TEMPERATURE_ROWS), "annotations[0].x: '2026-11-31' không có")
        spec["annotations"][0]["x"] = "2026-11-03"
        self.assertEqual(errors(spec, TEMPERATURE, TEMPERATURE_ROWS), [])

    def test_v16_colors_assign_tokens_only(self) -> None:
        found = errors(bar(colors={"assign": {"Hue": "#ff0000"}}))
        self.assertError(found, "colors.assign['Hue']: chỉ dùng series-1…series-8 hoặc muted, không dùng mã màu.")
        self.assertError(errors(bar(colors={"assign": {"Vinh": "series-2"}})), "colors.assign['Vinh']: không phải")
        self.assertEqual(errors(bar(colors={"assign": {"Hue": "series-2"}})), [])

    def test_v17_highlight_suggests_close_value(self) -> None:
        found = errors(bar(colors={"scheme": "emphasis", "highlight": ["Hà Nội"]}))
        self.assertEqual(found, [("colors.highlight[0]: 'Hà Nội' không có trong 'ten_thanh_pho'. "
                                  "Giá trị gần giống: Ha Noi.")])

    def test_v18_options_per_type(self) -> None:
        found = errors(by_x("line", "ngay", "nhiet_do") | {"options": {"bins": 5}}, TEMPERATURE, TEMPERATURE_ROWS)
        self.assertEqual(found, ["options.bins: không dùng cho line. Tùy chọn của line: curve, points, connect_nulls."])
        spec = {"type": "histogram", "encoding": {"x": {"field": "a"}}, "options": {"bins": 5, "bin_width": 2}}
        self.assertError(errors(spec, GRID, GRID_ROWS), "options:")
        spec = by_x("bullet", "vung", "a") | {"options": {"target_value": 5, "ranges": [3, 2]}}
        self.assertError(errors(spec, GRID, GRID_ROWS), "options:")

    def test_v19_sort_and_filter_fields(self) -> None:
        self.assertError(errors(bar(transform={"sort": {"by": "nhiet_do"}})),
                         "transform.sort.by: phải là none, x, y hoặc một cột trong encoding.y (luong_mua).")
        self.assertError(errors(bar(transform={"filter": [{"field": "nhiet", "op": "eq", "value": 1}]})),
                         "transform.filter[0].field: không có cột 'nhiet'")

    def test_v20_facet_requirements(self) -> None:
        self.assertError(errors(bar(facet={"by": "series"})), "facet: facet.by = series cần encoding.series.")
        self.assertError(errors(bar(facet={"by": "measure"})), "facet: facet.by = measure cần ít nhất 2 số đo")

    def test_v21_same_column_in_two_roles(self) -> None:
        spec = by_x("bar_grouped", "vung", "a", series={"field": "vung"})
        self.assertError(errors(spec, GRID, GRID_ROWS), "encoding.series: 'vung' đã dùng ở encoding.x")
        self.assertError(errors(by_x("bar_grouped", "vung", "a", "a"), GRID, GRID_ROWS),
                         "encoding.y[1].field: 'a' đã có ở encoding.y[0].")
        spec = {"type": "sankey", "encoding": {"source": {"field": "vung"}, "target": {"field": "vung"},
                                               "y": [{"field": "a"}]}}
        self.assertError(errors(spec, GRID, GRID_ROWS), "'vung' đã dùng")

    def test_v22_aggregate_needs_number(self) -> None:
        spec = by_x("bar", "ngay", "vung")
        spec["encoding"]["y"][0]["aggregate"] = "sum"
        self.assertError(errors(spec, GRID, GRID_ROWS), "encoding.y[0].aggregate: sum cần cột số; 'vung' là văn bản")
        spec["encoding"]["y"][0]["aggregate"] = "count_distinct"
        self.assertEqual(errors(spec, GRID, GRID_ROWS), [])

    def test_v23_other_and_cumulative_need_additive(self) -> None:
        spec = by_x("line", "ngay", "nhiet_do") | {"transform": {"cumulative": True}}
        self.assertError(errors(spec, TEMPERATURE, TEMPERATURE_ROWS), "transform.cumulative: 'nhiet_do' không cộng")
        fields = [field("ten", "text"), field("nhiet_do", "number", additive=False)]
        spec = by_x("bar", "ten", "nhiet_do") | {"transform": {"top_n": {"n": 1, "other": True}}}
        self.assertError(errors(spec, fields, [["A", 1], ["B", 2]]), "không gộp 'Khác' cho 'nhiet_do'")

    def test_v24_index_to_first_needs_non_zero_start(self) -> None:
        rows = [[day, index] for index, day in enumerate(DAYS)]
        spec = by_x("line", "ngay", "nhiet_do") | {"transform": {"index_to": "first"}}
        self.assertError(errors(spec, TEMPERATURE, rows), "transform.index_to: 'nhiet_do' bằng 0")

    def test_v25_time_axis_is_not_sorted_by_value(self) -> None:
        spec = by_x("line", "ngay", "nhiet_do") | {"transform": {"sort": {"by": "y"}}}
        self.assertError(errors(spec, TEMPERATURE, TEMPERATURE_ROWS), "transform.sort.by: line có trục x thời gian")

    def test_v26_duplicate_color_tokens(self) -> None:
        spec = bar(colors={"assign": {"Hue": "series-2", "Ha Noi": "series-2"}})
        self.assertError(errors(spec), "series-2 đã gán cho 'Hue'")
        spec = by_x("bar_grouped", "vung", "a", "b")
        spec["encoding"]["y"][0]["color"] = spec["encoding"]["y"][1]["color"] = "series-3"
        self.assertError(errors(spec, GRID, GRID_ROWS), "encoding.y[1].color: series-3 đã gán cho 'a'")

    def test_v27_time_unit_only_on_dates_and_not_finer(self) -> None:
        spec = bar()
        spec["encoding"]["x"]["time_unit"] = "month"
        self.assertError(errors(spec), "encoding.x.time_unit: chỉ dùng cho cột ngày; 'ten_thanh_pho' là văn bản.")
        fields = [field("thang", "date", time_unit="month"), TEMPERATURE[1]]
        spec = by_x("line", "thang", "nhiet_do")
        spec["encoding"]["x"]["time_unit"] = "day"
        found = errors(spec, fields, [["2026-10-01", 1], ["2026-11-01", 2]])
        self.assertError(found, "encoding.x.time_unit: cột đã gom theo month")

    def test_v28_color_scheme(self) -> None:
        self.assertError(errors(bar(colors={"scheme": "emphasis"})), "colors.scheme: emphasis cần colors.highlight.")
        spec = by_x("bar_grouped", "vung", "a", "b") | {"colors": {"scheme": "sequential"}}
        self.assertError(errors(spec, GRID, GRID_ROWS), "colors.scheme: sequential không dùng cho bar_grouped")
        spec = {"type": "heatmap", "encoding": {"x": {"field": "ngay"}, "row": {"field": "vung"},
                                                "color": {"field": "a"}}, "colors": {"scheme": "diverging"}}
        self.assertError(errors(spec, GRID, GRID_ROWS), "colors.scheme: diverging cần giá trị cả âm lẫn dương")
        spec["options"] = {"midpoint": 20}
        self.assertEqual(errors(spec, GRID, GRID_ROWS), [])

    def test_v29_log_x_on_category_and_bands(self) -> None:
        self.assertError(errors(bar(axes={"x": {"scale": "log"}})),
                         "axes.x.scale: log chỉ dùng cho trục số; trục x của bar là phân loại.")
        self.assertError(errors(bar(reference_bands=[{"axis": "y", "start": 30, "end": 10}])),
                         "reference_bands[0]: start (30) phải nhỏ hơn end (10).")

    def test_v30_facet_not_for_part_to_whole(self) -> None:
        spec = by_x("pie", "ten_thanh_pho", "luong_mua") | {"facet": {"by": "measure"}}
        self.assertError(errors(spec), "facet: không dùng cho pie.")
        rows = [[DAYS[index % 3], f"V{index}", "X", 1, 1, 1] for index in range(13)]
        spec = by_x("line", "ngay", "a", series={"field": "vung"}) | {"facet": {"by": "series"}}
        self.assertError(errors(spec, GRID, rows), "facet: chia theo series ra 13 ô, tối đa 12.")

    def test_v31_filter_shapes(self) -> None:
        def filtered(rule: dict[str, Any]) -> list[str]:
            return errors(bar(transform={"filter": [rule]}))

        self.assertError(filtered({"field": "ten_thanh_pho", "op": "in", "value": "Hue"}), "op in cần danh sách")
        self.assertError(filtered({"field": "ten_thanh_pho", "op": "eq", "value": ["Hue"]}),
                         "op eq cần đúng một giá trị")
        self.assertError(filtered({"field": "ten_thanh_pho", "op": "gt", "value": "A"}),
                         "op: gt chỉ dùng cho cột số hoặc ngày")
        self.assertError(filtered({"field": "luong_mua", "op": "gt", "value": "nhiều"}), "'nhiều' không phải số")
        found = errors(by_x("line", "ngay", "nhiet_do") | {"transform": {"filter": [
            {"field": "ngay", "op": "gte", "value": "13/11"}]}}, TEMPERATURE, TEMPERATURE_ROWS)
        self.assertError(found, "giá trị phải dạng YYYY-MM-DD")

    def test_v32_graph_shapes(self) -> None:
        fields = [field("nguon", "text"), field("dich", "text"), field("so", "number", additive=True)]
        spec = {"type": "sankey", "encoding": {"source": {"field": "nguon"}, "target": {"field": "dich"},
                                               "y": [{"field": "so"}]}}
        self.assertError(errors(spec, fields, [["A", "B", 1], ["B", "C", 1], ["C", "A", 1]]), "sankey: có vòng")
        self.assertError(errors(spec, fields, [["A", "A", 1], ["A", "B", 1]]), "tự nối")
        fields, rows, spec = MINIMAL["sunburst"]
        self.assertError(errors(spec, fields, [*rows, ["Trung", "Ha Noi", 1]]), "lá 'Ha Noi' thuộc hai cha")

    def test_v33_personal_data(self) -> None:
        fields = [*CITY, field("so_dien_thoai", "text", pii=True)]
        rows = [[*row, f"09{index}"] for index, row in enumerate(CITY_ROWS)]
        spec = {"type": "scatter", "encoding": {"x": {"field": "luong_mua"}, "y": [{"field": "luong_mua"}],
                                                "label": {"field": "so_dien_thoai"}}}
        self.assertError(errors(spec, fields, rows), "encoding.label: 'so_dien_thoai' là dữ liệu cá nhân")
        spec = bar(transform={"filter": [{"field": "so_dien_thoai", "op": "eq", "value": "090"}]})
        self.assertError(errors(spec, fields, rows), "không lọc theo giá trị của cột dữ liệu cá nhân")

    def test_v34_disabled_types(self) -> None:
        found = errors(by_x("pie", "ten_thanh_pho", "luong_mua"), enabled=frozenset({"bar", "table"}))
        self.assertEqual(found, ["type: pie chưa được hỗ trợ ở bản này. Các loại dùng được: bar, table."])
        self.assertEqual(errors(bar(), enabled=frozenset({"bar", "table"})), [])

    def test_many_errors_are_collected(self) -> None:
        spec = {"type": "bar", "encoding": {"x": {"field": "khong_co"}, "y": [{"field": "cung_khong"}]}}
        self.assertEqual(len(errors(spec)), 2)

    def test_combo_marks(self) -> None:
        spec = by_x("combo", "ngay", "a", "b")
        self.assertError(errors(spec, GRID, GRID_ROWS), "combo cần mark")
        self.assertError(errors(by_x("bar", "vung", "a") | {"encoding": {"x": {"field": "vung"}, "y": [
            {"field": "a", "mark": "bar"}]}}, GRID, GRID_ROWS), "mark: chỉ dùng cho combo")


class NullAndDataTests(unittest.TestCase):
    def test_null_rules(self) -> None:
        rows = [["A", 1], [None, 2], ["B", "NaN"], ["C", float("inf")], ["D", True]]
        checked = validate_chart(bar(), CITY, rows)
        self.assertEqual(checked.stats["points"], 2)
        prepared = chart_stats(checked.spec, CITY, rows)
        self.assertEqual(prepared["groups"], 2)
        rows = [[DAYS[0], 1], [None, 2], [DAYS[1], 3]]
        checked = validate_chart(by_x("line", "ngay", "nhiet_do"), TEMPERATURE, rows)
        self.assertEqual(checked.stats["dropped_null"], 1)
        self.assertTrue(any("Bỏ 1 dòng" in warning for warning in checked.warnings))

    def test_rows_complete_false_downgrades_data_rules(self) -> None:
        spec = {"type": "histogram", "encoding": {"x": {"field": "luong_mua"}}}
        self.assertTrue(errors(spec))
        checked = validate_chart(spec, CITY, CITY_ROWS, rows_complete=False)
        self.assertTrue(any("histogram: cần ít nhất 10" in warning for warning in checked.warnings))
        self.assertTrue(any("Kiểm trên 4 dòng đã lưu" in warning for warning in checked.warnings))
        self.assertTrue(errors(bar(type="stacked_bar"), rows_complete=False))

    def test_aggregate_auto_is_normalized(self) -> None:
        checked = validate_chart(by_x("bar", "vung", "a"), GRID, GRID_ROWS)
        self.assertEqual(checked.spec.encoding.y[0].aggregate, "sum")
        checked = validate_chart(bar(), CITY, CITY_ROWS)
        self.assertEqual(checked.spec.encoding.y[0].aggregate, "none")
        fields = [GRID[1], field("t", "number", additive=False)]
        checked = validate_chart(by_x("bar", "vung", "t"), fields, [["A", 1], ["A", 3], ["B", 2]])
        self.assertEqual(checked.spec.encoding.y[0].aggregate, "avg")
        self.assertTrue(any("avg" in warning for warning in checked.warnings))

    def test_labels_all_with_many_points_is_softened(self) -> None:
        checked = validate_chart(by_x("line", "ngay", "nhiet_do") | {"labels": {"show": "all"}}, TEMPERATURE,
                                 TEMPERATURE_ROWS * 1 + [[f"2026-12-{day:02d}", day] for day in range(1, 10)])
        self.assertEqual(checked.spec.labels.show, "auto")

    def test_fixture_cases(self) -> None:
        cases = json.loads((FIXTURES / "chart_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 40)
        for case in cases:
            with self.subTest(case=case["name"]):
                fields = [ChartField.model_validate(item) for item in case["fields"]]
                expect = case["expect"]
                try:
                    checked = validate_chart(case["spec"], fields, case["rows"])
                except ChartSpecError as error:
                    self.assertFalse(expect["valid"], error.errors)
                    for part in expect["errors"]:
                        self.assertTrue(any(part in message for message in error.errors), (part, error.errors))
                    continue
                self.assertTrue(expect["valid"])
                self.assertEqual(checked.stats, expect["stats"])
                self.assertEqual(chart_stats(checked.spec, fields, case["rows"]), expect["stats"])


class InferTests(unittest.TestCase):
    def test_infer_fields_from_json_values(self) -> None:
        rows = [
            ["2026-11-19", "2026-11-19T00:00:00", "2026-11-19T07:30:00", 1.5, "Hue", True, None, 3],
            ["2026-11-20", "2026-11-20T00:00:00", "2026-11-20T08:00:00", 2, "Vinh", False, None, "x"],
        ]
        columns = ["ngay", "moc", "luc", "luong_mua", "ten", "co", "rong", "lan"]
        kinds = {item.name: item.type for item in infer_fields(columns, rows)}
        self.assertEqual(kinds, {"ngay": "date", "moc": "date", "luc": "datetime", "luong_mua": "number",
                                 "ten": "text", "co": "boolean", "rong": "other", "lan": "text"})
        nam = infer_fields(["nam", "so"], [[2026, 1]])
        self.assertEqual(nam[0].format_hint, "plain")
        self.assertEqual(nam[0].role, "dimension")
        self.assertEqual(nam[1].label, "So")


class SuggestTests(unittest.TestCase):
    SHAPES: ClassVar[dict[str, tuple[list[ChartField], list[list[Any]], str, set[str]]]] = {
        "empty": (CITY, [], "table", set()),
        "text_only": ([field("ten", "text")], [["A"], ["B"]], "table", set()),
        "one_row": ([field("a", "number"), field("b", "number")], [[1, 2]], "kpi", set()),
        "one_row_goal": ([field("thuc_te", "number"), field("muc_tieu", "number")], [[8, 10]], "kpi", {"bullet"}),
        "c_n_3": (CITY, CITY_ROWS[:3], "bar", {"bar_horizontal", "lollipop", "pie", "donut", "funnel", "treemap"}),
        "c_n_5": (CITY, [[name, index + 1] for index, name in enumerate("ABCDE")], "bar_horizontal", {"pie"}),
        "c_n_20": (CITY, [[f"V{index}", index + 1] for index in range(20)], "bar_horizontal", {"lollipop"}),
        "c_n_60": (CITY, [[f"V{index}", index + 1] for index in range(60)], "table", {"bar_horizontal"}),
        "t_n_additive": (GRID[:1] + GRID[3:4], [[day, index] for index, day in enumerate(DAYS)], "bar",
                         {"line", "area", "calendar_heatmap"}),
        "t_n_average": (TEMPERATURE, TEMPERATURE_ROWS, "line", {"area", "calendar_heatmap"}),
        "t_c_n": (GRID[:2] + GRID[3:4], [row[:2] + row[3:4] for row in GRID_ROWS if row[2] == "X"], "line",
                  {"bar_grouped", "bar_stacked", "area_stacked", "heatmap", "sparkline_table"}),
        "c_2n_same_unit": (GRID[1:2] + GRID[3:5], [[name, index, index + 1] for index, name in enumerate("ABCD")],
                           "bar_grouped", {"bar_stacked", "dumbbell", "radar", "combo"}),
        "c_2n_other_unit": ([GRID[1], field("a", "number", unit="mm"), field("b", "number", unit="°C")],
                            [[name, index, index + 1] for index, name in enumerate("ABCD")], "table", set()),
        "two_n": ([field("x", "number"), field("y", "number")], [[index, index * 2 % 7] for index in range(8)],
                  "scatter", set()),
        "three_n": ([field("x", "number"), field("y", "number"), field("z", "number")],
                    [[index, index * 2 % 7, index + 1] for index in range(6)], "bubble", {"scatter"}),
        "one_n_raw": ([field("x", "number")], [[index] for index in range(12)], "histogram", set()),
        "c_n_raw": ([field("vung", "text"), field("x", "number")],
                    [["A" if index % 2 else "B", index] for index in range(12)], "box_plot", {"histogram"}),
        "c_c_n": (GRID[1:4], [[row[1], row[2], row[3]] for row in GRID_ROWS if row[0] == DAYS[0]], "heatmap",
                  {"bar_stacked", "bar_grouped", "sankey"}),
    }

    def test_matrix_default_and_compatible_types(self) -> None:
        for name, (fields, rows, default, expected) in self.SHAPES.items():
            with self.subTest(shape=name):
                self.assertEqual(suggest_chart(fields, rows).spec.type, default)
                types = compatible_types(fields, rows)
                self.assertEqual(types[-1], "table")
                self.assertTrue(expected <= set(types), (expected - set(types), types))
                if default != "table":
                    self.assertEqual(types[0], default)

    def test_question_type_breaks_ties(self) -> None:
        rows = [[name, index + 1] for index, name in enumerate("ABCDE")]
        self.assertEqual(suggest_chart(CITY, rows, "T11").spec.type, "donut")
        spec = suggest_chart(CITY, rows, "T7").spec
        self.assertEqual(spec.transform.sort.order, "desc")

    def test_every_default_spec_validates(self) -> None:
        for name, (fields, rows, default, _) in self.SHAPES.items():
            with self.subTest(shape=name):
                spec = BUILDERS[default](profile(fields, rows))
                checked = validate_chart(spec, fields, rows)
                self.assertEqual(validate_chart(checked.json(), fields, rows).json(), checked.json())
                suggested = suggest_chart(fields, rows)
                self.assertEqual(validate_chart(suggested.json(), fields, rows).spec.type, default)

    def test_enabled_filters_types_and_falls_back_to_table(self) -> None:
        enabled = frozenset({"line", "table"})
        self.assertEqual(compatible_types(CITY, CITY_ROWS, enabled=enabled), ["table"])
        self.assertEqual(suggest_chart(CITY, CITY_ROWS, enabled=enabled).spec.type, "table")

    def test_display(self) -> None:
        self.assertEqual(chart_display({"type": "table"}, 10, "agent"), "none")
        self.assertEqual(chart_display({"type": "bar"}, 2, "agent"), "none")
        self.assertEqual(chart_display({"type": "bar"}, 3, "agent"), "chart")
        self.assertEqual(chart_display({"type": "bar"}, 3, "auto"), "chart_if_last")
        self.assertEqual(chart_display({"type": "kpi"}, 5, "agent"), "none")


if __name__ == "__main__":
    unittest.main()
