from collections.abc import Sequence
from typing import Any

import httpx

from backend.core.setting import config

from ..utils.exceptions import Text2SqlIndexUnavailable

TEXT_INDEX_SCHEMA: dict[str, Any] = {
    "type": "text", "tokenizer": "word", "lowercase": True, "ascii_folding": True, "scoring": {"type": "bm25"},
}


def text_index_is_current(index_info: dict[str, Any]) -> bool:
    params = index_info.get("params", {})
    return bool(params.get("ascii_folding")) and params.get("scoring", {}).get("type") == "bm25"


class QdrantRepository:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(base_url=config.qdrant_url.rstrip("/"), timeout=30)
        self.collection = config.text2sql_collection
        self.dimensions = config.text2sql_embedding_dimensions

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise Text2SqlIndexUnavailable() from error

    def ensure_collection(self) -> None:
        path = f"/collections/{self.collection}"
        try:
            response = self.client.get(path)
        except httpx.HTTPError as error:
            raise Text2SqlIndexUnavailable() from error
        if response.status_code == 404:
            self._request("PUT", path, json={"vectors": {"size": self.dimensions, "distance": "Cosine"}})
            payload_schema: dict[str, Any] = {}
        else:
            try:
                response.raise_for_status()
                result = response.json()["result"]
                vectors = result["config"]["params"]["vectors"]
                if vectors["size"] != self.dimensions:
                    raise Text2SqlIndexUnavailable("Kích thước vector của collection không khớp cấu hình.")
                payload_schema = result.get("payload_schema", {})
            except (httpx.HTTPError, KeyError, TypeError) as error:
                raise Text2SqlIndexUnavailable() from error
        fields: dict[str, Any] = {
            "connection_id": "keyword",
            "topic": "keyword",
            "table_id": "keyword",
            "entity_id": "keyword",
            "user_id": "keyword",
            "is_active": "bool",
            "text": TEXT_INDEX_SCHEMA,
        }
        for field_name, field_schema in fields.items():
            existing = payload_schema.get(field_name)
            if field_name == "text" and existing is not None and not text_index_is_current(existing):
                self._request("DELETE", f"{path}/index/{field_name}?wait=true")
                existing = None
            if existing is None:
                self._request(
                    "PUT", f"{path}/index?wait=true",
                    json={"field_name": field_name, "field_schema": field_schema},
                )

    def existing_points(self, connection_id: str, topics: Sequence[str]) -> dict[str, dict[str, Any]]:
        points: dict[str, dict[str, Any]] = {}
        offset: str | int | None = None
        while True:
            body: dict[str, Any] = {
                "filter": {"must": [
                    {"key": "connection_id", "match": {"value": connection_id}},
                    {"key": "topic", "match": {"any": list(topics)}},
                ]},
                "limit": 256,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            result = self._request("POST", f"/collections/{self.collection}/points/scroll", json=body)["result"]
            for point in result["points"]:
                points[str(point["id"])] = point["payload"]
            offset = result.get("next_page_offset")
            if offset is None:
                return points

    def upsert(self, points: list[dict[str, Any]]) -> None:
        if points:
            self._request("PUT", f"/collections/{self.collection}/points?wait=true", json={"points": points})

    def delete(self, point_ids: list[str]) -> None:
        if point_ids:
            self._request("POST", f"/collections/{self.collection}/points/delete?wait=true", json={"points": point_ids})

    def search(
        self, question: str, vector: list[float], connection_id: str, topic: str, limit: int,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        point_filter = {"must": [
            {"key": "connection_id", "match": {"value": connection_id}},
            {"key": "topic", "match": {"value": topic}},
            *({"key": key, "match": {"value": value}} for key, value in (filters or {}).items()),
        ]}
        body = {
            "prefetch": [
                {"query": vector, "filter": point_filter, "limit": limit},
                {"query": {"text": question}, "using": "text", "filter": point_filter, "limit": limit},
            ],
            "query": {"rrf": {}},
            "limit": limit,
            "with_payload": True,
        }
        result = self._request("POST", f"/collections/{self.collection}/points/query", json=body)["result"]
        return result["points"]

    def close(self) -> None:
        self.client.close()
