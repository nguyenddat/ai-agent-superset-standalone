import json
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.main import app
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.chat.events import ChatEvent, done, reasoning, step, token
from backend.modules.text2sql.chat.pipeline import ChatPipeline
from backend.modules.text2sql.routes.chat import get_chat_pipeline

register_all_models()
URL = "/api/v1/text2sql/chat"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n")
        assert len(lines) == 2, block
        assert lines[0].startswith("event: ") and lines[1].startswith("data: "), block
        events.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return events


class ScriptedPipeline(ChatPipeline):
    def __init__(self, engine, events: list[ChatEvent]) -> None:
        super().__init__(session_factory=lambda: Session(engine))
        self.events = events
        self.calls: list[tuple] = []
        self.turn_requests: list = []

    def run(self, connection_id, question, user_id=None, turn_request=None):
        self.calls.append((connection_id, question, user_id))
        self.turn_requests.append(turn_request)
        yield from self.events


class ChatRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            active = DatabaseConnection(name=f"a-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            paused = DatabaseConnection(name=f"p-{uuid4()}", dialect="postgresql", uri_ciphertext="x", is_active=False)
            s.add_all([active, paused])
            s.commit()
            self.active, self.paused = str(active.id), str(paused.id)
        self.pipeline = ScriptedPipeline(self.engine, [
            step("rewrite", "started"),
            reasoning("rewrite", "model", 0, "B1. Câu hỏi "), reasoning("rewrite", "model", 0, "hỏi \"doanh thu\"\n"),
            reasoning("rewrite", "model", 1, "B2. Giữ nguyên"),
            step("rewrite", "done", {"rewritten_question": "Doanh thu\ntheo vùng"}),
            step("join_plan", "started"), reasoning("join_plan", "server", 0, "Bảng gốc: Đơn hàng."),
            step("join_plan", "done", {"status": "ok"}),
            ChatEvent("data", {"kind": "dataset", "rows": [["Bắc", "350.00"]]}),
            token("Miền Bắc "), token("dẫn đầu."),
            done("answered", "dataset", "d-1", assumptions=["Năm 2025"], message="Doanh thu \"theo vùng\".",
                 clarification_question=None),
        ])
        app.dependency_overrides[get_chat_pipeline] = lambda: self.pipeline
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_streams_server_sent_events(self) -> None:
        response = self.client.post(URL, json={"connection_id": self.active, "question": "  Doanh thu?  ",
                                               "user_id": "  "})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        events = parse_sse(response.text)
        self.assertEqual([name for name, _ in events], [
            "step", "reasoning", "reasoning", "reasoning", "step", "step", "reasoning", "step", "data", "token",
            "token", "done",
        ])
        self.assertEqual(events[4][1]["detail"]["rewritten_question"], "Doanh thu\ntheo vùng")
        thoughts: dict[tuple[str, int], str] = {}
        for name, data in events:
            if name == "reasoning":
                self.assertEqual(set(data), {"step", "source", "index", "delta"})
                key = (data["step"], data["index"])
                thoughts[key] = thoughts.get(key, "") + data["delta"]
        self.assertEqual(thoughts, {
            ("rewrite", 0): 'B1. Câu hỏi hỏi "doanh thu"\n', ("rewrite", 1): "B2. Giữ nguyên",
            ("join_plan", 0): "Bảng gốc: Đơn hàng.",
        })
        self.assertEqual(events[6][1]["source"], "server")
        self.assertEqual("".join(data["text"] for name, data in events if name == "token"), "Miền Bắc dẫn đầu.")
        self.assertEqual(events[-1][1], {"status": "answered", "flow": "dataset", "dataset_id": "d-1",
                                         "assumptions": ["Năm 2025"], "message": 'Doanh thu "theo vùng".'})
        self.assertEqual(self.pipeline.calls[0][1:], ("Doanh thu?", None))

    def test_invalid_input_is_rejected_before_streaming(self) -> None:
        for body in (
            {"connection_id": self.active, "question": "   "},
            {"connection_id": self.active, "question": "x" * 2001},
            {"connection_id": "not-a-uuid", "question": "q"},
            {"connection_id": self.active},
            {"connection_id": self.active, "question": "q", "sql": "SELECT 1"},
        ):
            with self.subTest(body=str(body)[:60]):
                response = self.client.post(URL, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertTrue(response.headers["content-type"].startswith("application/json"))
        self.assertEqual(self.pipeline.calls, [])

    def test_unknown_connection_returns_404_before_streaming(self) -> None:
        response = self.client.post(URL, json={"connection_id": str(uuid4()), "question": "q"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Không tìm thấy connection.")
        self.assertEqual(self.pipeline.calls, [])

    def test_paused_connection_is_rejected_before_streaming(self) -> None:
        response = self.client.post(URL, json={"connection_id": self.paused, "question": "q"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("tạm dừng", response.json()["detail"])
        self.assertEqual(self.pipeline.calls, [])

    def test_errors_after_the_stream_starts_arrive_as_an_error_event(self) -> None:
        from backend.modules.text2sql.chat.events import error

        self.pipeline.events = [step("rewrite", "started"), error("agent_unavailable", "Không thể gọi mô hình.")]
        response = self.client.post(URL, json={"connection_id": self.active, "question": "q"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parse_sse(response.text)[-1], (
            "error", {"code": "agent_unavailable", "message": "Không thể gọi mô hình."},
        ))


if __name__ == "__main__":
    unittest.main()


class ScopeTokenPipeline(ScriptedPipeline):
    """Reports the scope token the executor would see while the pipeline runs."""

    def run(self, connection_id, question, user_id=None, turn_request=None):
        from backend.modules.text2sql.query.executor import SCOPE_TOKEN

        yield token(str(SCOPE_TOKEN.get()))
        yield done("answered", "dataset", None, assumptions=[], message="", clarification_question=None)


class ServiceCallTests(unittest.TestCase):
    def setUp(self) -> None:
        from backend.core.setting import config

        self.config = config
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            c = DatabaseConnection(name=f"a-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
            s.add(c)
            s.commit()
            self.connection = str(c.id)
        pipeline = ScopeTokenPipeline(self.engine, [])
        app.dependency_overrides[get_chat_pipeline] = lambda: pipeline
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def ask(self, headers=None, **extra):
        return self.client.post(
            URL, json={"connection_id": self.connection, "question": "kWh?", **extra}, headers=headers or {}
        )

    def test_scope_token_reaches_the_executor_only_for_its_request(self) -> None:
        scope = str(uuid4())
        tokens = [d["text"] for name, d in parse_sse(self.ask(scope_token=scope).text) if name == "token"]
        self.assertEqual(tokens, [scope])
        tokens = [d["text"] for name, d in parse_sse(self.ask().text) if name == "token"]
        self.assertEqual(tokens, ["None"])
        self.assertEqual(self.ask(scope_token="not-a-uuid").status_code, 422)
        self.assertEqual(self.ask(time_zone="UTC -c fsync=off").status_code, 422)  # no option injection
        self.assertEqual(self.ask(time_zone="Asia/Ho_Chi_Minh").status_code, 200)

    def test_service_key_is_required_once_set(self) -> None:
        from pydantic import SecretStr

        self.assertEqual(self.ask().status_code, 200)  # unset: open, as for the frontend
        original = self.config.text2sql_service_key
        self.config.text2sql_service_key = SecretStr("k" * 40)
        self.addCleanup(setattr, self.config, "text2sql_service_key", original)
        self.assertEqual(self.ask().status_code, 401)
        self.assertEqual(self.ask({"X-Service-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.ask({"X-Service-Key": "k" * 40}).status_code, 200)
        self.config.text2sql_service_key = SecretStr("")  # compose passes "" when unset
        self.assertEqual(self.ask().status_code, 200)
