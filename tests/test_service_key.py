import re
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.core.setting import config
from backend.main import app
from tests.service_key import SERVICE_HEADERS, use_service_key

OWN_KNOWLEDGE = "/api/v1/own-knowledge"


def api_routes(own_knowledge: bool) -> list[tuple[str, str]]:
    routes = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/") or path.startswith(OWN_KNOWLEDGE) != own_knowledge:
            continue
        url = re.sub(r"\{[^}]+\}", str(uuid4()), path)
        routes += [(method.upper(), url) for method in operations]
    return routes


class ServiceKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.routes = api_routes(own_knowledge=False)
        self.assertGreater(len(self.routes), 30)

    def call(self, method: str, url: str, headers=None):
        return self.client.request(method, url, headers=headers or {})

    def test_every_route_rejects_a_missing_key(self) -> None:
        use_service_key(self)
        for method, url in self.routes:
            with self.subTest(route=f"{method} {url}"):
                self.assertEqual(self.call(method, url).status_code, 401)

    def test_every_route_rejects_a_wrong_key(self) -> None:
        use_service_key(self)
        for method, url in self.routes:
            with self.subTest(route=f"{method} {url}"):
                self.assertEqual(self.call(method, url, {"X-Service-Key": "wrong"}).status_code, 401)

    def test_unset_key_fails_closed(self) -> None:
        self.addCleanup(setattr, config, "text2sql_service_key", config.text2sql_service_key)
        for unset in (None, SecretStr("")):  # compose passes "" when the variable is unset
            config.text2sql_service_key = unset
            for method, url in self.routes:
                with self.subTest(key=unset, route=f"{method} {url}"):
                    self.assertEqual(self.call(method, url, SERVICE_HEADERS).status_code, 503)

    def test_right_key_passes_the_gate(self) -> None:
        use_service_key(self)
        for method, url in self.routes:
            with self.subTest(route=f"{method} {url}"):
                self.assertNotIn(self.call(method, url, SERVICE_HEADERS).status_code, (401, 503))

    def test_openapi_stays_open(self) -> None:
        use_service_key(self)
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_own_knowledge_keeps_its_own_keys(self) -> None:
        self.addCleanup(setattr, config, "text2sql_service_key", config.text2sql_service_key)
        config.text2sql_service_key = None
        gate_answers = {"Backend chưa được cấu hình TEXT2SQL_SERVICE_KEY.", "Thiếu hoặc sai X-Service-Key."}
        own = [
            (method.upper(), re.sub(r"\{[^}]+\}", str(uuid4()), path))
            for path, operations in app.openapi()["paths"].items()
            if path.startswith(OWN_KNOWLEDGE)
            for method in operations
        ]
        self.assertTrue(own)
        for method, url in own:  # its real method, so routing does not answer 405 before the gate
            with self.subTest(route=f"{method} {url}"):
                self.assertNotIn(self.call(method, url).json().get("detail"), gate_answers)


if __name__ == "__main__":
    unittest.main()
