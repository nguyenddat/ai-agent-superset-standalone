import unittest
from datetime import date
from uuid import uuid4

from backend.modules.text2sql.services.agent_catalog import (
    AgentCatalog,
    ColumnInfo,
    MetricInfo,
    RuleCondition,
    RuleInfo,
    TableInfo,
)
from backend.modules.text2sql.services.explanations import (
    DataRange,
    ValueMatch,
    metric_explanations,
    sql_explanations,
)
from backend.modules.text2sql.services.sql_builder import QueryMetricArgs, build_metric_query

TODAY = date(2026, 11, 20)
TABLE_ID = uuid4()
METRIC_ID = uuid4()
COLUMNS = (
    ColumnInfo("ngay", "date", "Ngày", None, (), False),
    ColumnInfo("thanh_pho", "text", "Thành phố", None, (), False),
    ColumnInfo("luong_mua", "numeric", "Lượng mưa", None, (), False, "mm"),
    ColumnInfo("loai_tram", "text", "Loại trạm", None, (), False),
    ColumnInfo("quan_trac_vien", "text", "Quan trắc viên", None, (), True),
)
RULE = RuleInfo(
    id=uuid4(), name="Chỉ trạm chính", table_id=TABLE_ID, description=None,
    conditions=(RuleCondition("loai_tram", "equals", "chinh"),), exceptions=(), examples=(),
    metric_ids=frozenset({METRIC_ID}),
)


def make_catalog(warning: str | None = None) -> AgentCatalog:
    table = TableInfo(TABLE_ID, "weather", "daily", "Thời tiết ngày", None, "một trạm một ngày", COLUMNS)
    metric = MetricInfo(
        METRIC_ID, "tong_luong_mua", "Tổng lượng mưa", "SUM(luong_mua)", "Tổng lượng mưa đo được", None, None,
        warning, TABLE_ID, None,
    )
    return AgentCatalog(tables={TABLE_ID: table}, metrics={METRIC_ID: metric}, rules=[RULE])


def explain(args: QueryMetricArgs, catalog: AgentCatalog | None = None, **extra):
    catalog = catalog or make_catalog()
    built = build_metric_query(catalog, args)
    options = {"matches": [], "data_range": None, "aggregated": False, "truncated": False, "row_count": 3}
    options.update(extra)
    return metric_explanations(catalog, args, built, today=TODAY, **options)


def kinds(items) -> list[str]:
    return [item.kind for item in items]


class MetricExplanationTests(unittest.TestCase):
    def test_period_from_bounds_and_filter_with_unit(self) -> None:
        items = explain(QueryMetricArgs(metric="tong_luong_mua", group_by=["thanh_pho"], filters=[
            {"column": "ngay", "operator": "greater_than_or_equal", "value": "2026-11-13"},
            {"column": "ngay", "operator": "less_than", "value": "2026-11-20"},
            {"column": "luong_mua", "operator": "greater_than", "value": 10.5},
        ], order_by=[{"field": "value"}], limit=5))
        self.assertEqual(kinds(items), ["metric", "source", "period", "filter", "group", "order", "rule"])
        self.assertEqual(items[0].text, "Chỉ số: Tổng lượng mưa – Tổng lượng mưa đo được")
        self.assertEqual(items[1].text, "Nguồn: Thời tiết ngày (mỗi dòng: một trạm một ngày)")
        period = items[2]
        self.assertEqual((period.text, period.start, period.end), ("Thời gian: 13–19/11", "2026-11-13", "2026-11-19"))
        self.assertEqual(items[3].text, "Lượng mưa trên 10,5 mm")
        self.assertEqual(items[4].text, "Chia theo: Thành phố")
        self.assertEqual(items[5].text, "Sắp xếp giảm dần theo Tổng lượng mưa, lấy 5 dòng đầu")
        self.assertEqual((items[6].status, items[6].name), ("applied", "Chỉ trạm chính"))

    def test_rule_statuses(self) -> None:
        yielded = explain(QueryMetricArgs(metric="tong_luong_mua", filters=[
            {"column": "loai_tram", "operator": "equals", "value": "phu"}]))
        rule = next(item for item in yielded if item.kind == "rule")
        self.assertEqual(rule.status, "yielded")
        self.assertEqual(rule.text, "Quy tắc «Chỉ trạm chính» không lọc Loại trạm vì câu hỏi đã lọc")
        skipped = explain(QueryMetricArgs(metric="tong_luong_mua", skip_rules=["Chỉ trạm chính"]))
        self.assertEqual([item.status for item in skipped if item.kind == "rule"], ["skipped"])

    def test_built_in_rule_is_hidden(self) -> None:
        catalog = make_catalog()
        catalog.metrics[METRIC_ID] = MetricInfo(
            METRIC_ID, "ty_le", "Tỷ lệ", "100.0 * COUNT(CASE WHEN loai_tram = 'chinh' THEN 1 END) / COUNT(*)",
            None, None, None, None, TABLE_ID, None,
        )
        items = explain(QueryMetricArgs(metric="ty_le"), catalog)
        self.assertNotIn("rule", kinds(items))

    def test_value_match_range_scope_assumption_truncated_warning(self) -> None:
        items = explain(
            QueryMetricArgs(metric="tong_luong_mua", assumption="Hiểu 'gần đây' là 7 ngày qua"),
            make_catalog("Số liệu tháng 11 chưa chốt"),
            matches=[ValueMatch("thanh_pho", "Đà Nẵng", ["Da Nang"])],
            data_range=DataRange("ngay", "2025-01-01", "2026-11-19"), aggregated=True, truncated=True,
            row_count=200,
        )
        self.assertEqual(kinds(items)[-6:], ["value_match", "data_range", "scope", "assumption", "truncated",
                                             "warning"])
        found = {item.kind: item for item in items}
        self.assertEqual(found["value_match"].text, "«Đà Nẵng» được hiểu là «Da Nang» trong dữ liệu")
        self.assertEqual(found["value_match"].values, ["Da Nang"])
        self.assertEqual((found["data_range"].start, found["data_range"].end), ("2025-01-01", "2026-11-19"))
        self.assertIn("1/1/2025", found["data_range"].text)
        self.assertEqual(found["assumption"].text, "Hiểu 'gần đây' là 7 ngày qua")
        self.assertEqual(found["truncated"].text, "Chỉ lấy 200 dòng đầu theo giới hạn truy vấn")
        self.assertEqual(found["warning"].text, "Số liệu tháng 11 chưa chốt")

    def test_personal_data_values_are_hidden(self) -> None:
        items = explain(QueryMetricArgs(metric="tong_luong_mua", filters=[
            {"column": "quan_trac_vien", "operator": "equals", "value": "Nguyen Van A"}]))
        found = next(item for item in items if item.kind == "filter")
        self.assertEqual(found.text, "Lọc theo Quan trắc viên (giá trị ẩn)")
        self.assertIsNone(found.values)
        self.assertNotIn("Nguyen", repr(items))

    def test_period_text_uses_turn_today(self) -> None:
        items = explain(QueryMetricArgs(metric="tong_luong_mua", filters=[
            {"column": "ngay", "operator": "equals", "value": "2025-11-19"}]))
        period = next(item for item in items if item.kind == "period")
        self.assertEqual(period.text, "Thời gian: thứ Tư, 19/11/2025")


class SqlExplanationTests(unittest.TestCase):
    def test_method_source_period_and_filters(self) -> None:
        sql = (
            "SELECT thanh_pho, SUM(luong_mua) FROM weather.daily WHERE ngay >= DATE '2026-11-01' "
            "AND ngay < '2026-12-01' AND thanh_pho IN ('Hue', 'Vinh') GROUP BY 1"
        )
        items, notes = sql_explanations(
            make_catalog(), sql, "Tổng mưa tháng 11 theo thành phố", None, [], False, 2, TODAY,
        )
        self.assertEqual(notes, [])
        self.assertEqual(kinds(items), ["method", "source", "period", "filter"])
        self.assertEqual(items[1].text, "Nguồn: Thời tiết ngày")
        self.assertEqual(items[2].text, "Thời gian: tháng 11")
        self.assertEqual(items[3].values, ["Hue", "Vinh"])

    def test_complex_where_is_skipped_and_cte_is_not_a_source(self) -> None:
        sql = (
            "WITH t AS (SELECT * FROM weather.daily) SELECT COUNT(*) FROM t "
            "WHERE ngay >= '2026-11-01' OR thanh_pho = 'Hue'"
        )
        items, _ = sql_explanations(make_catalog(), sql, "Đếm", None, [], False, 1, TODAY)
        self.assertNotIn("period", kinds(items))
        self.assertNotIn("filter", kinds(items))
        self.assertEqual([item.text for item in items if item.kind == "source"], ["Nguồn: Thời tiết ngày"])

    def test_unparsable_sql_does_not_raise(self) -> None:
        items, notes = sql_explanations(make_catalog(), "SELECT (((", "Thử", "giả định", [], True, 5, TODAY)
        self.assertEqual(kinds(items), ["method", "assumption", "truncated"])
        self.assertEqual(notes, [])

    def test_rules_applied(self) -> None:
        items, notes = sql_explanations(
            make_catalog(), "SELECT 1 FROM weather.daily", "x", None, ["chỉ trạm chính", "Quy tắc lạ"], False, 1,
            TODAY,
        )
        rule = [item for item in items if item.kind == "rule"]
        self.assertEqual([(item.name, item.status) for item in rule], [("Chỉ trạm chính", "applied")])
        self.assertEqual(notes, ["Không có quy tắc 'Quy tắc lạ'."])

    def test_personal_filter_value_hidden(self) -> None:
        sql = "SELECT COUNT(*) FROM weather.daily WHERE quan_trac_vien = 'Nguyen Van A'"
        items, _ = sql_explanations(make_catalog(), sql, "x", None, [], False, 1, TODAY)
        self.assertNotIn("Nguyen", repr(items))


if __name__ == "__main__":
    unittest.main()
