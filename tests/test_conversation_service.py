import unittest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.modules.conversation.models import ConversationTurn, ConversationTurnFeedback
from backend.modules.conversation.services import ConversationService, HistoryTurn, title_from_question
from backend.modules.conversation.utils.exceptions import (
    ConversationConnectionNotFoundError,
    ConversationNotFoundError,
    ConversationValidationError,
)
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.model_registry import register_all_models

register_all_models()


class ConversationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        connection = DatabaseConnection(name="Warehouse", dialect="postgresql", uri_ciphertext="x")
        self.session.add(connection)
        self.session.commit()
        self.connection_id = connection.id
        self.service = ConversationService(self.session, max_stored_rows=3)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def finish(self, turn: ConversationTurn, status: str = "answered", answer: str = "Trả lời") -> None:
        self.service.complete_turn(turn, status=status, flow="metric", answer=answer, rewritten_question="Viết lại")

    def test_title_from_question(self) -> None:
        self.assertEqual(title_from_question("  Doanh   thu\nnăm nay  "), "Doanh thu năm nay")
        long = " ".join(["doanhthu"] * 20)
        title = title_from_question(long)
        self.assertTrue(title.endswith("…"))
        self.assertLessEqual(len(title), 81)
        self.assertNotIn("doanhth…", title)
        self.assertEqual(len(title_from_question("x" * 200)), 81)

    def test_start_begin_complete_and_sequence(self) -> None:
        conversation = self.service.start(self.connection_id, " alice ", "Doanh thu tháng này là bao nhiêu?")
        self.assertEqual(conversation.user_id, "alice")
        self.assertEqual(conversation.title, "Doanh thu tháng này là bao nhiêu?")
        self.assertIsNone(conversation.last_message_at)
        first = self.service.begin_turn(conversation, "Doanh thu tháng này là bao nhiêu?")
        self.assertEqual((first.sequence, first.status), (1, "running"))
        self.assertIsNotNone(conversation.last_message_at)
        second = self.service.begin_turn(conversation, "Còn tháng trước?", retry_of=first.id)
        self.assertEqual((second.sequence, second.retry_of), (2, first.id))
        rows = [{"a": Decimal("1.5")}] * 5
        self.service.complete_turn(
            second, status="answered", flow="metric", answer="Tăng 5%", rewritten_question="Doanh thu tháng trước",
            steps=[{"step": "rewrite", "status": "done"}],
            results=[{"sql": "SELECT 1", "rows": rows, "row_count": 5}, {"sql": "SELECT 2", "rows": [[1]]}],
            rewrite={"terms": []}, assumptions=["Năm dương lịch"], pii={"masked": []}, dataset_id=uuid4(),
            duration_ms=1200, model="m",
        )
        self.session.commit()
        stored = self.session.get(ConversationTurn, second.id)
        self.assertEqual(len(stored.results[0]["rows"]), 3)
        self.assertTrue(stored.results[0]["stored_truncated"])
        self.assertEqual(stored.results[0]["row_count"], 5)
        self.assertEqual(stored.results[0]["rows"][0], {"a": "1.5"})
        self.assertFalse(stored.results[1]["stored_truncated"])
        self.assertEqual(stored.status, "answered")
        with self.assertRaises(ConversationValidationError):
            self.service.complete_turn(first, status="running")
        with self.assertRaises(ConversationValidationError):
            self.service.complete_turn(first, status="answered", flow="sql")
        with self.assertRaises(ConversationValidationError):
            self.service.begin_turn(conversation, "   ")
        other = self.service.start(self.connection_id, "alice", "Khác")
        with self.assertRaises(ConversationValidationError):
            self.service.begin_turn(other, "Thử lại", retry_of=first.id)

    def test_empty_title_is_set_on_first_turn(self) -> None:
        created = self.service.create({"connection_id": self.connection_id, "user_id": "alice", "title": None})
        conversation = self.service.get_owned(created["id"], "alice")
        self.assertEqual(conversation.title, "")
        self.service.begin_turn(conversation, "Số khách hàng mới")
        self.assertEqual(conversation.title, "Số khách hàng mới")
        self.service.begin_turn(conversation, "Câu sau không đổi tiêu đề")
        self.assertEqual(conversation.title, "Số khách hàng mới")

    def test_recent_history_only_finished_and_clipped(self) -> None:
        conversation = self.service.start(self.connection_id, "alice", "Câu 1")
        statuses = ["answered", "error", "needs_clarification", "cannot_answer", None, "answered"]
        for index, status in enumerate(statuses, start=1):
            turn = self.service.begin_turn(conversation, f"Câu {index}")
            if status is not None:
                self.finish(turn, status, ("chữ " * 400) if index == 6 else f"Đáp {index}")
        history = self.service.recent_history(conversation.id)
        self.assertEqual([item.question for item in history], ["Câu 1", "Câu 3", "Câu 4", "Câu 6"])
        self.assertEqual(history[1], HistoryTurn(question="Câu 3", answer="Đáp 3"))
        self.assertLessEqual(len(history[-1].answer), 501)
        self.assertTrue(history[-1].answer.endswith("…"))
        self.assertEqual([item.question for item in self.service.recent_history(conversation.id, limit=2)],
                         ["Câu 4", "Câu 6"])
        self.assertEqual(self.service.recent_history(conversation.id, limit=0), [])

    def test_recent_history_uses_the_masked_answer_when_stored(self) -> None:
        conversation = self.service.start(self.connection_id, "alice", "Câu 1")
        turn = self.service.begin_turn(conversation, "Ai mua nhiều nhất?")
        self.service.complete_turn(
            turn, status="answered", answer="Nguyễn Văn An mua nhiều nhất",
            pii={"history_answer": "<PII> mua nhiều nhất"},
        )
        history = self.service.recent_history(conversation.id)
        self.assertEqual(history, [HistoryTurn(question="Ai mua nhiều nhất?", answer="<PII> mua nhiều nhất")])

    def test_ownership_and_missing_connection(self) -> None:
        conversation = self.service.start(self.connection_id, "alice", "Câu hỏi")
        with self.assertRaises(ConversationNotFoundError):
            self.service.get_owned(conversation.id, "bob")
        with self.assertRaises(ConversationNotFoundError):
            self.service.get_owned(uuid4(), "alice")
        with self.assertRaises(ConversationConnectionNotFoundError):
            self.service.start(uuid4(), "alice", "Câu hỏi")

    def test_cascade_and_constraints(self) -> None:
        conversation = self.service.start(self.connection_id, "alice", "Câu hỏi")
        first = self.service.begin_turn(conversation, "Một")
        retry = self.service.begin_turn(conversation, "Hai", retry_of=first.id)
        self.session.add(ConversationTurnFeedback(turn_id=first.id, user_id="alice", rating="up"))
        self.session.commit()
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.add(ConversationTurnFeedback(turn_id=first.id, user_id="alice", rating="down"))
                self.session.flush()
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.add(ConversationTurnFeedback(turn_id=retry.id, user_id="alice", rating="meh"))
                self.session.flush()
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.add(ConversationTurn(conversation_id=conversation.id, sequence=1, question="Trùng"))
                self.session.flush()
        self.service.delete_turn(conversation.id, first.id, "alice")
        self.session.commit()
        self.session.expire_all()
        self.assertIsNone(self.session.get(ConversationTurn, retry.id).retry_of)
        self.assertEqual(self.session.scalars(select(ConversationTurnFeedback)).all(), [])
        self.service.delete(conversation.id, "alice")
        self.session.commit()
        self.assertEqual(self.session.scalars(select(ConversationTurn)).all(), [])
        self.service.start(self.connection_id, "alice", "Câu khác")
        self.session.commit()
        self.session.delete(self.session.get(DatabaseConnection, self.connection_id))
        self.session.commit()
        self.assertEqual(self.service.repository.list_page("alice", None, False, None, 50, 0), [])


if __name__ == "__main__":
    unittest.main()
