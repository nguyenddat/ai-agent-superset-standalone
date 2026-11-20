import json
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from backend.modules.text2sql.schemas import FieldOut
from backend.modules.text2sql.services.agent_catalog import AgentCatalog, ColumnInfo, MetricInfo, TableInfo
from backend.modules.text2sql.services.display_format import (
    NumberStyle,
    bucket_display,
    cell_display,
    date_display,
    dates_context,
    llm_fields,
    llm_rows,
    metric_fields,
    parse_d3_format,
    period_label,
    sql_fields,
    unique_columns,
    value_type,
    vi_number,
)
from backend.modules.text2sql.services.sql_builder import QueryMetricArgs

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 20)
TABLE_ID = uuid4()
COLUMNS = (
    ColumnInfo("ngay", "date", "Ngày", None, (), False),
    ColumnInfo("nam", "integer", "Năm", None, (), False),
    ColumnInfo("ma_tram", "integer", "Mã trạm", None, (), False),
    ColumnInfo("thanh_pho", "text", "Thành phố", None, (), False),
    ColumnInfo("luong_mua", "numeric", "Lượng mưa", None, (), False, "mm", ",.1f"),
    ColumnInfo("nhiet_do", "numeric", "Nhiệt độ", None, (), False, "°C"),
    ColumnInfo("doanh_thu", "numeric", "Doanh thu", None, (), False),
    ColumnInfo("so_dien_thoai", "text", "Số điện thoại", None, (), True),
)


def metric(name: str, expression: str, label: str, currency: str | None = None, fmt: str | None = None) -> MetricInfo:
    return MetricInfo(uuid4(), name, label, expression, None, fmt, currency, None, TABLE_ID, None)


METRICS = [
    metric("tong_luong_mua", "SUM(luong_mua)", "Tổng lượng mưa"),
    metric("nhiet_do_tb", "AVG(nhiet_do)", "Nhiệt độ trung bình"),
    metric("tong_doanh_thu", "SUM(doanh_thu)", "Tổng doanh thu", currency="VND"),
]
CATALOG = AgentCatalog(
    tables={TABLE_ID: TableInfo(TABLE_ID, "weather", "daily", "Thời tiết ngày", None, None, COLUMNS)},
    metrics={item.id: item for item in METRICS}, rules=[],
)


def number(**extra) -> FieldOut:
    return FieldOut(name="v", label="V", type="number", role="measure", **extra)


class NumberTests(unittest.TestCase):
    def test_vi_number(self) -> None:
        cases = [
            (1234.5, 1, "1.234,5"), (77.56, 1, "77,6"), (41250000, 0, "41.250.000"), (-0.04, 1, "0"),
            (-1.25, 1, "-1,3"), (0.035, 3, "0,035"), (77.55, None, "77,55"), (21.0285, None, "21,03"),
            (0.000123, None, "0,000123"), (Decimal("2.5"), 0, "3"),
        ]
        for value, decimals, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(vi_number(value, decimals), expected)
        self.assertEqual(vi_number(2026, 0, grouped=False), "2026")

    def test_vi_number_rejects_non_numbers(self) -> None:
        for value in (float("nan"), float("inf"), True, "1"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                vi_number(value, None)

    def test_parse_d3_format(self) -> None:
        self.assertEqual(parse_d3_format(",.1f"), NumberStyle(1, False))
        self.assertEqual(parse_d3_format(".1%"), NumberStyle(1, True))
        self.assertEqual(parse_d3_format(",d"), NumberStyle(0, False))
        for text in ("SMART_NUMBER", None, "", "$,.2s", "abc"):
            with self.subTest(text=text):
                self.assertEqual(parse_d3_format(text), NumberStyle(None, False))

    def test_cell_display_numbers(self) -> None:
        self.assertEqual(cell_display(2026, number(format_hint="plain"), TODAY), "2026")
        self.assertEqual(cell_display(70000, number(format_hint="plain"), TODAY), "70000")
        self.assertEqual(cell_display(0.123, number(percent=True, decimals=1), TODAY), "12,3%")
        self.assertIsNone(cell_display("NaN", number(), TODAY))
        self.assertIsNone(cell_display("-Infinity", number(), TODAY))
        self.assertIsNone(cell_display(None, number(), TODAY))

    def test_format_fixture(self) -> None:
        cases = json.loads((FIXTURES / "format_cases.json").read_text(encoding="utf-8"))
        for value, data, expected in cases["number"]:
            with self.subTest(value=value, field=data):
                self.assertEqual(cell_display(value, FieldOut.model_validate(data), TODAY), expected)
        for value, unit, today, expected in cases["date"]:
            day = date.fromisoformat(today)
            with self.subTest(value=value, unit=unit):
                if unit in (None, "datetime"):
                    kind = "date" if unit is None else "datetime"
                    found = cell_display(value, FieldOut(name="t", label="T", type=kind), day)
                else:
                    found = bucket_display(value, unit, day)
                self.assertEqual(found, expected)


class DateTests(unittest.TestCase):
    def test_date_display(self) -> None:
        self.assertEqual(date_display("2026-11-19", TODAY), "thứ Năm, 19/11")
        self.assertEqual(date_display("2025-11-19", TODAY), "thứ Tư, 19/11/2025")
        self.assertEqual(date_display(date(2026, 11, 22), TODAY, weekday=False), "22/11")
        self.assertIsNone(date_display("không phải ngày", TODAY))

    def test_period_label(self) -> None:
        self.assertEqual(period_label(date(2026, 11, 19), date(2026, 11, 20), TODAY), "thứ Năm, 19/11")
        self.assertEqual(period_label(date(2026, 11, 13), date(2026, 11, 20), TODAY), "13–19/11")
        self.assertEqual(period_label(date(2026, 10, 28), date(2026, 11, 4), TODAY), "28/10–3/11")
        self.assertEqual(period_label(date(2026, 10, 1), date(2026, 11, 1), TODAY), "tháng 10")
        self.assertEqual(period_label(date(2025, 12, 29), date(2026, 1, 5), TODAY), "29/12/2025–4/1/2026")

    def test_dates_context_has_six_labelled_ranges(self) -> None:
        context = dates_context(TODAY)
        self.assertEqual(context["yesterday"], {"from": "2026-11-19", "before": "2026-11-20",
                                                "label": "hôm qua (thứ Năm, 19/11)"})
        self.assertEqual(context["last_7_days"]["label"], "7 ngày qua (13–19/11)")
        self.assertEqual(context["last_week"]["label"], "tuần trước (9–15/11)")
        self.assertEqual(context["this_week"]["label"], "tuần này (16–22/11)")
        self.assertEqual(context["this_month"]["label"], "tháng này (tháng 11)")
        self.assertEqual(context["last_month"]["label"], "tháng trước (tháng 10)")

    def test_buckets(self) -> None:
        self.assertEqual(bucket_display("2026-11-01", "month", TODAY), "tháng 11")
        self.assertEqual(bucket_display("2026-11-16", "week", TODAY), "tuần 16–22/11")
        self.assertEqual(bucket_display("2026-10-01", "quarter", TODAY), "quý 4")
        self.assertEqual(bucket_display("2026-01-01", "year", TODAY), "2026")
        self.assertEqual(bucket_display("2025-10-01", "month", TODAY), "tháng 10/2025")

    def test_llm_rows_keep_text(self) -> None:
        fields = [FieldOut(name="ten", label="Tên", type="text"), number(unit="mm")]
        self.assertEqual(llm_rows([["2026/11", 1234.5]], fields, TODAY), [["2026/11", "1.234,5"]])


class FieldTests(unittest.TestCase):
    def test_value_types(self) -> None:
        self.assertEqual(value_type([datetime(2026, 11, 19), datetime(2026, 11, 20)]), "date")
        self.assertEqual(value_type([datetime(2026, 11, 19, 7, 30)]), "datetime")
        self.assertEqual(value_type([time(7, 30)]), "text")
        self.assertEqual(value_type([uuid4()]), "text")
        self.assertEqual(value_type(["<binary>"]), "text")
        self.assertEqual(value_type([1, "x"]), "text")
        self.assertEqual(value_type([True, None]), "boolean")
        self.assertIsNone(value_type([None]))

    def test_unique_columns(self) -> None:
        names, notes = unique_columns(["ten", "ten", "?column?", "ten_2", ""])
        self.assertEqual(names, ["ten", "ten_2", "cot_3", "ten_2_2", "cot_5"])
        self.assertEqual(len(notes), 4)

    def test_metric_fields(self) -> None:
        args = QueryMetricArgs(metric="tong_luong_mua", group_by=["nam", "thanh_pho"])
        fields = metric_fields(CATALOG, args, ["nam", "thanh_pho", "tong_luong_mua"], [[2026, "Hue", 12.5]])
        nam, city, measure = fields
        self.assertEqual((nam.format_hint, nam.role, nam.label), ("plain", "dimension", "Năm"))
        self.assertEqual(cell_display(2026, nam, TODAY), "2026")
        self.assertEqual((city.type, city.role), ("text", "dimension"))
        self.assertEqual((measure.label, measure.unit, measure.additive, measure.role),
                         ("Tổng lượng mưa", "mm", True, "measure"))
        average = metric_fields(CATALOG, QueryMetricArgs(metric="nhiet_do_tb"), ["nhiet_do_tb"], [[21.5]])[0]
        self.assertEqual((average.unit, average.additive), ("°C", False))
        money = metric_fields(CATALOG, QueryMetricArgs(metric="tong_doanh_thu"), ["tong_doanh_thu"], [[1]])[0]
        self.assertEqual(money.unit, "đồng")

    def test_metric_fields_time_grain(self) -> None:
        args = QueryMetricArgs(metric="tong_luong_mua", time_grain={"column": "ngay", "grain": "month"})
        fields = metric_fields(CATALOG, args, ["ngay", "tong_luong_mua"], [[datetime(2026, 11, 1), 3]])
        self.assertEqual((fields[0].type, fields[0].time_unit), ("date", "month"))
        self.assertEqual(cell_display("2026-11-01", fields[0], TODAY), "tháng 11")
        self.assertEqual(cell_display("2026-11-16", fields[0].model_copy(update={"time_unit": "week"}), TODAY),
                         "tuần 16–22/11")

    def test_sql_fields(self) -> None:
        sql = (
            "SELECT EXTRACT(YEAR FROM ngay) AS nam_do, ma_tram, DATE_TRUNC('week', ngay) AS tuan, "
            "luong_mua, so_dien_thoai, SUM(luong_mua) AS tong_luong_mua, AVG(nhiet_do) AS tb, id "
            "FROM weather.daily GROUP BY 1, 2, 3, 4, 5, 8"
        )
        columns = ["nam_do", "ma_tram", "tuan", "luong_mua", "so_dien_thoai", "tong_luong_mua", "tb", "id"]
        rows = [[2026, 70000, datetime(2026, 11, 16), 1.5, "090", 3.0, 21.5, 7]]
        fields = {item.name: item for item in sql_fields(CATALOG, sql, {"tb": "Nhiệt độ TB (°C)"}, columns, rows)}
        self.assertEqual(fields["nam_do"].format_hint, "plain")
        self.assertEqual(cell_display(70000, fields["ma_tram"], TODAY), "70000")
        self.assertEqual((fields["tuan"].type, fields["tuan"].time_unit), ("date", "week"))
        self.assertEqual((fields["luong_mua"].label, fields["luong_mua"].unit), ("Lượng mưa", "mm"))
        self.assertTrue(fields["so_dien_thoai"].pii)
        self.assertEqual((fields["tong_luong_mua"].label, fields["tong_luong_mua"].role), ("Tổng lượng mưa", "measure"))
        self.assertEqual((fields["tb"].label, fields["tb"].unit), ("Nhiệt độ TB", "°C"))
        self.assertEqual(fields["id"].format_hint, "plain")
        compact = llm_fields(list(fields.values()))
        self.assertNotIn("pii", compact[4])
        self.assertNotIn("role", compact[0])

    def test_sql_fields_survive_unparsable_sql(self) -> None:
        fields = sql_fields(CATALOG, "SELECT (((", {}, ["so_luong_tram"], [[3]])
        self.assertEqual((fields[0].label, fields[0].role), ("So luong tram", "measure"))


if __name__ == "__main__":
    unittest.main()
