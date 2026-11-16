import json
import os
import unittest
from uuid import uuid4

import httpx

from backend.modules.text2sql.vector_store.qdrant_db_service import (
    TEXT_INDEX_SCHEMA,
    QdrantDbService,
    text_index_is_current,
)

KEYWORD_FIELDS = ("connection_id", "topic", "table_id", "entity_id", "user_id")


def collection_info(text_params: dict | None) -> dict:
    schema = {name: {"data_type": "keyword", "points": 0} for name in KEYWORD_FIELDS}
    schema["is_active"] = {"data_type": "bool", "points": 0}
    if text_params is not None:
        schema["text"] = {"data_type": "text", "params": text_params, "points": 0}
    return {"result": {"config": {"params": {"vectors": {"size": 1536}}}, "payload_schema": schema}}


def service_with(info: dict) -> tuple[QdrantDbService, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=info)
        return httpx.Response(200, json={"result": True})

    client = httpx.Client(base_url="http://qdrant:6333", transport=httpx.MockTransport(respond))
    return QdrantDbService(client), requests


class TextIndexTests(unittest.TestCase):
    def test_current_index_requires_folding_and_bm25(self) -> None:
        self.assertTrue(text_index_is_current({"params": TEXT_INDEX_SCHEMA}))
        legacy = {key: value for key, value in TEXT_INDEX_SCHEMA.items() if key != "ascii_folding"}
        self.assertFalse(text_index_is_current({"params": legacy}))
        self.assertFalse(text_index_is_current({"params": {**TEXT_INDEX_SCHEMA, "scoring": {"type": "tf"}}}))
        self.assertFalse(text_index_is_current({}))

    def test_ensure_collection_rebuilds_legacy_text_index_once(self) -> None:
        legacy = {key: value for key, value in TEXT_INDEX_SCHEMA.items() if key != "ascii_folding"}
        service, requests = service_with(collection_info(legacy))
        service.ensure_collection()
        writes = [(request.method, request.url.path) for request in requests if request.method != "GET"]
        self.assertEqual(writes, [
            ("DELETE", f"/collections/{service.collection}/index/text"),
            ("PUT", f"/collections/{service.collection}/index"),
        ])
        created = json.loads(requests[-1].content)
        self.assertEqual(created["field_name"], "text")
        self.assertTrue(created["field_schema"]["ascii_folding"])

    def test_ensure_collection_leaves_current_indexes_alone(self) -> None:
        service, requests = service_with(collection_info(TEXT_INDEX_SCHEMA))
        service.ensure_collection()
        self.assertEqual([request.method for request in requests], ["GET"])

    def test_ensure_collection_creates_missing_text_index(self) -> None:
        service, requests = service_with(collection_info(None))
        service.ensure_collection()
        created = [json.loads(request.content) for request in requests if request.method == "PUT"]
        self.assertEqual([item["field_name"] for item in created], ["text"])
        self.assertEqual(created[0]["field_schema"], TEXT_INDEX_SCHEMA)


class SearchFilterTests(unittest.TestCase):
    def body(self, filters: dict | None) -> dict:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"result": {"points": []}})

        client = httpx.Client(base_url="http://qdrant:6333", transport=httpx.MockTransport(respond))
        QdrantDbService(client).search("q", [0.1] * 4, "connection-id", "own_knowledge", 5, filters)
        return json.loads(requests[0].content)

    def test_extra_filters_apply_to_both_dense_and_keyword_branches(self) -> None:
        body = self.body({"user_id": "alice"})
        for prefetch in body["prefetch"]:
            self.assertIn({"key": "user_id", "match": {"value": "alice"}}, prefetch["filter"]["must"])
            self.assertIn({"key": "topic", "match": {"value": "own_knowledge"}}, prefetch["filter"]["must"])

    def test_no_extra_filter_by_default(self) -> None:
        self.assertEqual(len(self.body(None)["prefetch"][0]["filter"]["must"]), 2)


@unittest.skipUnless(os.environ.get("QDRANT_TEST_URL"), "Đặt QDRANT_TEST_URL tới một Qdrant dùng để thử nghiệm.")
class HybridSearchIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        url = os.environ["QDRANT_TEST_URL"].rstrip("/")
        self.service = QdrantDbService(httpx.Client(base_url=url, timeout=30))
        self.service.collection = f"text2sql_test_{uuid4().hex}"
        self.addCleanup(lambda: (self.service.client.delete(f"/collections/{self.service.collection}"),
                                 self.service.close()))
        self.service.ensure_collection()
        self.dimensions = self.service.dimensions

    def point(self, number: int, text: str, vector: list[float], topic: str = "metric", connection: str = "c1"):
        return {
            "id": f"00000000-0000-0000-0000-{number:012d}", "vector": vector,
            "payload": {"connection_id": connection, "topic": topic, "entity_id": str(number), "text": text},
        }

    def entity_ids(
        self, question: str, vector: list[float], connection: str = "c1", topic: str = "metric"
    ) -> list[str]:
        return [point["payload"]["entity_id"] for point in
                self.service.search(question, vector, connection, topic, 10)]

    def test_bm25_ranks_by_keywords_when_dense_vectors_are_equal(self) -> None:
        flat = [0.1] * self.dimensions
        self.service.upsert([
            self.point(1, "Metric: Doanh thu | Bảng: Bán hàng", flat),
            self.point(2, "Metric: Số đơn hàng | Bảng: Bán hàng", flat),
            self.point(3, "Metric: Nhiệt độ trung bình | Bảng: Thời tiết", flat),
        ])
        self.assertEqual(self.entity_ids("doanh thu", flat)[0], "1")
        self.assertEqual(self.entity_ids("số đơn hàng", flat)[0], "2")

    def test_matching_ignores_vietnamese_diacritics_and_case(self) -> None:
        flat = [0.1] * self.dimensions
        self.service.upsert([
            self.point(1, "Metric: Nhiệt độ trung bình | Bảng: Thời tiết", flat),
            self.point(2, "Cột: Mã khu vực | Bảng: Đường dẫn", flat),
        ])
        self.assertEqual(self.entity_ids("nhiet do", flat)[0], "1")
        self.assertEqual(self.entity_ids("NHIỆT ĐỘ", flat)[0], "1")
        self.assertEqual(self.entity_ids("duong dan", flat)[0], "2")

    def test_dense_similarity_breaks_ties_when_no_keyword_matches(self) -> None:
        near = [1.0] + [0.0] * (self.dimensions - 1)
        far = [0.0, 1.0] + [0.0] * (self.dimensions - 2)
        self.service.upsert([self.point(1, "alpha", far), self.point(2, "beta", near)])
        self.assertEqual(self.entity_ids("khong trung tu nao", near)[0], "2")

    def test_hybrid_fuses_dense_and_keyword_signals(self) -> None:
        near = [1.0] + [0.0] * (self.dimensions - 1)
        far = [0.0, 1.0] + [0.0] * (self.dimensions - 2)
        self.service.upsert([
            self.point(1, "Metric: Doanh thu", far),
            self.point(2, "Metric: Số lượng tồn kho", near),
        ])
        ranked = self.entity_ids("doanh thu", near)
        self.assertEqual(set(ranked), {"1", "2"})

    def test_search_is_scoped_by_connection_and_topic(self) -> None:
        flat = [0.1] * self.dimensions
        self.service.upsert([
            self.point(1, "Metric: Doanh thu", flat, connection="c1"),
            self.point(2, "Metric: Doanh thu", flat, connection="c2"),
            self.point(3, "Bảng: Doanh thu", flat, topic="table", connection="c1"),
        ])
        self.assertEqual(self.entity_ids("doanh thu", flat, connection="c1", topic="metric"), ["1"])

    def test_user_filter_isolates_private_points(self) -> None:
        flat = [0.1] * self.dimensions
        alice = self.point(1, "Ngày mưa là ngày mưa trên 1mm", flat, topic="own_knowledge")
        bob = self.point(2, "Ngày mưa là ngày mưa trên 5mm", flat, topic="own_knowledge")
        alice["payload"]["user_id"], bob["payload"]["user_id"] = "alice", "bob"
        self.service.upsert([alice, bob])
        results = self.service.search("ngày mưa", flat, "c1", "own_knowledge", 10, {"user_id": "alice"})
        self.assertEqual([item["payload"]["entity_id"] for item in results], ["1"])
        everyone = self.service.search("ngày mưa", flat, "c1", "own_knowledge", 10)
        self.assertEqual({item["payload"]["entity_id"] for item in everyone}, {"1", "2"})

    def test_ensure_collection_upgrades_legacy_text_index_in_place(self) -> None:
        flat = [0.1] * self.dimensions
        path = f"/collections/{self.service.collection}"
        self.service.client.delete(f"{path}/index/text")
        legacy = {key: value for key, value in TEXT_INDEX_SCHEMA.items() if key != "ascii_folding"}
        self.service.client.put(f"{path}/index?wait=true", json={"field_name": "text", "field_schema": legacy})
        self.service.upsert([self.point(1, "Metric: Nhiệt độ", flat)])

        def keyword_hits() -> int:
            response = self.service.client.post(f"{path}/points/query", json={
                "query": {"text": "nhiet do"}, "using": "text", "limit": 5,
            })
            return len(response.json()["result"]["points"])

        self.assertEqual(keyword_hits(), 0)
        self.service.ensure_collection()
        info = self.service.client.get(path).json()["result"]["payload_schema"]["text"]
        self.assertTrue(text_index_is_current(info))
        self.assertEqual(keyword_hits(), 1)


if __name__ == "__main__":
    unittest.main()
