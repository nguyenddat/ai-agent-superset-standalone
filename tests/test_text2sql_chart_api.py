import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.core.setting import config
from backend.main import app

BASE = "/api/v1/text2sql"
FIELDS = [
    {"name": "thanh_pho", "label": "Thành phố", "type": "text"},
    {"name": "luong_mua", "label": "Lượng mưa", "type": "number", "unit": "mm", "role": "measure"},
]
ROWS = [["Hue", 12.5], ["Vinh", 3], ["Ha Noi", 1]]
BAR = {"type": "bar", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "luong_mua"}]}}


class ChartApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    def test_chart_types_lists_catalog(self) -> None:
        response = self.client.get(f"{BASE}/chart-types")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["types"]), 32)
        bar = next(item for item in body["types"] if item["type"] == "bar")
        self.assertEqual(bar["family"], "So sánh")
        self.assertIn("properties", bar["options_schema"])
        self.assertEqual([role["role"] for role in bar["roles"]], ["x", "y"])
        self.assertIn("series-1", body["palette"])

    def test_chart_types_respects_enabled_setting(self) -> None:
        with patch.object(type(config), "text2sql_chart_types", frozenset({"bar", "table"})):
            body = self.client.get(f"{BASE}/chart-types").json()
        self.assertEqual(sorted(body["enabled"]), ["bar", "table"])

    def test_validate_returns_normalized_spec(self) -> None:
        response = self.client.post(f"{BASE}/charts/validate", json={"chart": BAR, "fields": FIELDS, "rows": ROWS})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["chart"]["encoding"]["y"][0]["aggregate"], "none")
        self.assertEqual(body["chart_types"][-1], "table")

    def test_validate_rejects_with_messages(self) -> None:
        spec = {**BAR, "axes": {"y2": {}}}
        response = self.client.post(f"{BASE}/charts/validate", json={"chart": spec, "fields": FIELDS, "rows": ROWS})
        self.assertEqual(response.status_code, 400)
        self.assertIn("axes.y2: không hỗ trợ trục y thứ hai", response.json()["detail"])

    def test_validate_limits_rows(self) -> None:
        body = {"chart": BAR, "fields": FIELDS, "rows": [["x", 1]] * 1001}
        self.assertEqual(self.client.post(f"{BASE}/charts/validate", json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
