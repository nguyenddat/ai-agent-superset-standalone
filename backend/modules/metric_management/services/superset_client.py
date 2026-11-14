from dataclasses import dataclass
from typing import Any

import httpx

from ..utils.exceptions import SupersetUnavailableError


@dataclass(frozen=True)
class SupersetSnapshot:
    users: list[dict[str, Any]]
    databases: list[dict[str, Any]]
    datasets: list[dict[str, Any]]


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def fetch_snapshot(self) -> SupersetSnapshot:
        try:
            with httpx.Client(
                base_url=self.base_url, timeout=20, follow_redirects=False
            ) as client:
                login = client.post(
                    "/api/v1/security/login",
                    json={
                        "username": self.username,
                        "password": self.password,
                        "provider": "db",
                        "refresh": False,
                    },
                )
                login.raise_for_status()
                token = login.json()["access_token"]
                client.headers["Authorization"] = f"Bearer {token}"
                users = self._list(client, "/api/v1/security/users/")
                databases = self._list(client, "/api/v1/database/")
                dataset_rows = self._list(client, "/api/v1/dataset/")
                datasets = []
                for row in dataset_rows:
                    dataset_id = row.get("id")
                    if not isinstance(dataset_id, int):
                        raise TypeError("dataset id missing")
                    detail = client.get(f"/api/v1/dataset/{dataset_id}")
                    detail.raise_for_status()
                    result = detail.json()["result"]
                    if not isinstance(result, dict) or not isinstance(
                        result.get("metrics", []), list
                    ):
                        raise TypeError("invalid dataset detail")
                    datasets.append(result)
                return SupersetSnapshot(users, databases, datasets)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise SupersetUnavailableError() from error

    @staticmethod
    def _list(client: httpx.Client, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 0
        while True:
            response = client.get(path, params={"q": f"(page:{page},page_size:100)"})
            response.raise_for_status()
            payload = response.json()
            batch = payload["result"]
            if not isinstance(batch, list) or any(
                not isinstance(item, dict) for item in batch
            ):
                raise TypeError("invalid Superset list")
            rows.extend(batch)
            count = payload.get("count")
            if isinstance(count, int) and len(rows) >= count:
                return rows
            if len(batch) < 100:
                return rows
            page += 1
