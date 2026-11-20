import json
import threading
import unittest
from contextlib import nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import ormsgpack
from fastapi.testclient import TestClient
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from openai import APIConnectionError

from backend.agent_package.tool_agent import ToolAgentPause
from backend.common.base_model import utc_now
from backend.core.database import get_database
from backend.main import app
from backend.modules.conversation.services import HistoryTurn
from backend.modules.conversation.utils.exceptions import ConversationNotFoundError
from backend.modules.text2sql.dependencies import (
    get_chat_service,
    get_chat_service_factory,
)
from backend.modules.text2sql.repositories.source_query_repository import QueryRows
from backend.modules.text2sql.schemas import (
    AgentStepOut,
    ChatHistoryTurnIn,
    QuestionAnswerOut,
)
from backend.modules.text2sql.services.agent_catalog import (
    AgentCatalog,
    ColumnInfo,
    TableInfo,
)
from backend.modules.text2sql.services.agent_tools import QueryCache, Text2SqlToolkit
from backend.modules.text2sql.services.chat_events import step_event
from backend.modules.text2sql.services.chat_graph import (
    CHECKPOINT_TYPES,
    ChatRun,
    Clarification,
    PendingQuestion,
)
from backend.modules.text2sql.services.chat_service import (
    ChatService,
    execution_stages,
    turn_outcome,
)
from backend.modules.text2sql.services.chat_stream import ChatStream
from backend.modules.text2sql.services.retrieval_service import (
    MetricCandidate,
    RetrievalOutcome,
)
from backend.modules.text2sql.services.topic_search_service import (
    TopicHit,
    TopicSearchOutcome,
)
from backend.modules.text2sql.utils.exceptions import (
    Text2SqlAgentUnavailable,
    Text2SqlClarificationNotFound,
    Text2SqlClientDisconnected,
    Text2SqlInvalidRequest,
)

CONNECTION_ID = uuid4()
TODAY = date(2026, 11, 20)
METRIC_ID = uuid4()
TABLE_ID = uuid4()

INTENTS = {
    "Thành phố nào mưa nhiều nhất tuần qua?": {"question_type": "T7", "business_concepts": []},
    "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?": {"question_type": "T1", "business_concepts": []},
}
REWRITE = {
    "rewritten_question": "Thành phố nào mưa nhiều nhất tuần qua, nhiệt độ ở đó hôm qua bao nhiêu?",
    "sub_questions": [
        {"question": "Thành phố nào mưa nhiều nhất tuần qua?", "depends_on": []},
        {"question": "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?", "depends_on": [1]},
    ],
    "execution_mode": "sequential",
}
SINGLE_REWRITE = {
    "rewritten_question": "Lượng mưa ở Huế 3 ngày qua là bao nhiêu?",
    "sub_questions": [],
    "execution_mode": "parallel",
}
INTENTS[SINGLE_REWRITE["rewritten_question"]] = {"question_type": "T2", "business_concepts": []}


class FakeCompletion:
    def __init__(
        self, error: Exception | None = None, rewrite: dict | None = None, wait_for: threading.Event | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.error = error
        self.rewrite = rewrite or REWRITE
        self.wait_for = wait_for
        self.saw_retrieval: list[bool] = []

    def __call__(self, task: str, params: dict) -> dict:
        self.calls.append((task, params))
        if self.error is not None:
            raise self.error
        if task == "rewrite":
            return self.rewrite
        if self.wait_for is not None:
            self.saw_retrieval.append(self.wait_for.wait(timeout=2))
        return INTENTS[params["question"]]


class FakeText:
    def __init__(self, error: Exception | None = None, pieces: list[str] | None = None) -> None:
        self.calls: list[tuple[str, dict, bool]] = []
        self.error = error
        self.pieces = pieces

    def __call__(self, system_prompt: str, params: dict, on_text=None) -> str:
        self.calls.append((system_prompt, params, on_text is not None))
        if self.error is not None:
            raise self.error
        text = " / ".join(item["answer"] for item in params["answers"])
        if on_text is not None:
            for piece in self.pieces or [text]:
                on_text(piece)
        return text


class FakeEmbedding:
    def __init__(self, started: threading.Event | None = None) -> None:
        self.calls: list[list[str]] = []
        self.started = started

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.started is not None:
            self.started.set()
        return [[float(index)] for index, _ in enumerate(texts)]


class FakeRetrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[float] | None]] = []

    def search(self, connection_id, question, k=5, reranker=None, vector=None):
        self.calls.append((question, vector))
        return RetrievalOutcome(candidates=[MetricCandidate(
            metric_id=METRIC_ID, table_id=TABLE_ID, name="tong_luong_mua", label="Tổng lượng mưa",
            description=None, score=1.0, matched_topics=["metric"],
        )])


class FakeTopicSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None, list[float] | None]] = []

    def search(self, connection_id, topic, question, k=5, reranker=None, user_id=None, vector=None):
        self.calls.append((topic, question, user_id, vector))
        return TopicSearchOutcome(hits=[TopicHit(
            entity_id=uuid4(), table_id=None, name=topic, display_name=topic, text=f"{topic}: {question}", score=0.5,
        )])


class FakeAgent:
    def __init__(self) -> None:
        self.started: list = []
        self.prior: dict[int, list[int]] = {}

    def start(self, connection_id):
        self.started.append(connection_id)
        return SimpleNamespace(answer=self.answer, today=TODAY)

    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        self.prior[item.position] = [answer.position for answer in prior]
        return QuestionAnswerOut(position=item.position, question=item.question, answer=f"đáp án {item.position}")


def make_service(
    completion: FakeCompletion, embedding: FakeEmbedding | None = None, agent: FakeAgent | None = None,
) -> ChatService:
    service = ChatService(
        SimpleNamespace(), SimpleNamespace(), embedding or FakeEmbedding(), completion, agent or FakeAgent(),
    )
    service.retrieval = FakeRetrieval()
    service.topic_search = FakeTopicSearch()
    service.text_completion = FakeText()
    return service


class ExecutionStageTests(unittest.TestCase):
    def test_independent_questions_share_one_stage(self) -> None:
        self.assertEqual(execution_stages([[], [], []]), [[1, 2, 3]])

    def test_dependent_questions_run_after_their_dependencies(self) -> None:
        self.assertEqual(execution_stages([[], [], [1], [2, 3]]), [[1, 2], [3], [4]])


class ChatServiceTests(unittest.TestCase):
    def test_rewrites_then_classifies_and_retrieves_every_question(self) -> None:
        completion = FakeCompletion()
        service = make_service(completion)
        result = service.preprocess(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(completion.calls[0], ("rewrite", {"question": "câu hỏi", "chat_history": []}))
        self.assertEqual(sorted(task for task, _ in completion.calls[1:]), ["intent_classify", "intent_classify"])
        self.assertTrue(result.is_split)
        self.assertEqual([item.question_type for item in result.questions], ["T7", "T1"])
        self.assertEqual([item.position for item in result.questions], [1, 2])
        self.assertEqual(result.execution_mode, "sequential")
        self.assertEqual(result.stages, [[1], [2]])
        first = result.questions[0].knowledge
        self.assertEqual([metric.name for metric in first.metrics], ["tong_luong_mua"])
        self.assertEqual(first.glossary[0].text, "glossary: Thành phố nào mưa nhiều nhất tuần qua?")
        self.assertEqual(first.own_knowledge, [])

    def test_embeds_all_questions_once_and_reuses_vectors(self) -> None:
        embedding = FakeEmbedding()
        service = make_service(FakeCompletion(), embedding)
        service.preprocess(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(embedding.calls, [[item["question"] for item in REWRITE["sub_questions"]]])
        self.assertEqual([vector for _, vector in service.retrieval.calls], [[0.0], [1.0]])
        self.assertEqual(
            sorted({topic for topic, *_ in service.topic_search.calls}),
            ["column", "expert_rule", "glossary", "table"],
        )
        self.assertTrue(all(vector is not None for *_, vector in service.topic_search.calls))

    def test_own_knowledge_is_searched_only_with_user_id(self) -> None:
        service = make_service(FakeCompletion(rewrite=SINGLE_REWRITE))
        result = service.preprocess(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        own_calls = [call for call in service.topic_search.calls if call[0] == "own_knowledge"]
        self.assertEqual([user_id for _, _, user_id, _ in own_calls], ["user-1"])
        self.assertEqual(len(result.questions[0].knowledge.own_knowledge), 1)

    def test_classification_runs_while_retrieval_is_in_progress(self) -> None:
        started = threading.Event()
        completion = FakeCompletion(wait_for=started)
        make_service(completion, FakeEmbedding(started)).preprocess(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(completion.saw_retrieval, [True, True])

    def test_unsplit_question_uses_rewritten_question(self) -> None:
        completion = FakeCompletion(rewrite=SINGLE_REWRITE)
        service = make_service(completion)
        result = service.preprocess(CONNECTION_ID, "Còn 3 ngày qua?", [])
        self.assertEqual(completion.calls[1], ("intent_classify", {"question": SINGLE_REWRITE["rewritten_question"]}))
        self.assertEqual(service.retrieval.calls[0][0], SINGLE_REWRITE["rewritten_question"])
        self.assertFalse(result.is_split)
        self.assertEqual([(item.question, item.question_type) for item in result.questions],
                         [(SINGLE_REWRITE["rewritten_question"], "T2")])
        self.assertEqual(result.stages, [[1]])

    def test_history_keeps_last_six_turns_and_clips_answers(self) -> None:
        completion = FakeCompletion()
        history = [ChatHistoryTurnIn(question=f"câu {index}", answer="x" * 600) for index in range(8)]
        make_service(completion).preprocess(CONNECTION_ID, "câu hỏi", history)
        sent = completion.calls[0][1]["chat_history"]
        self.assertEqual([turn.question for turn in sent], [f"câu {index}" for index in range(2, 8)])
        self.assertTrue(all(len(turn.answer) <= 501 for turn in sent))

    def test_parser_error_becomes_agent_unavailable(self) -> None:
        with self.assertRaises(Text2SqlAgentUnavailable):
            make_service(FakeCompletion(OutputParserException("bad json"))).preprocess(CONNECTION_ID, "câu hỏi", [])


class ChatFlowTests(unittest.TestCase):
    def test_answers_each_question_then_synthesizes(self) -> None:
        agent = FakeAgent()
        completion = FakeCompletion()
        service = make_service(completion, agent=agent)
        result = service.chat(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(agent.started, [CONNECTION_ID])
        self.assertEqual(agent.prior, {1: [], 2: [1]})
        self.assertEqual([item.answer for item in result.answers], ["đáp án 1", "đáp án 2"])
        self.assertEqual(result.answer, "đáp án 1 / đáp án 2")
        self.assertEqual([task for task, _ in completion.calls], ["rewrite", "intent_classify", "intent_classify"])
        [(prompt, params, streamed)] = service.text_completion.calls
        self.assertIn("AnswerSynthesizer", prompt)
        self.assertFalse(streamed)
        self.assertEqual(params["today"], "2026-11-20 (thứ Sáu)")
        self.assertEqual(params["answers"][1], {
            "position": 2, "question": "Nhiệt độ ở <kết quả câu 1> hôm qua là bao nhiêu?", "question_type": "T1",
            "answer": "đáp án 2",
        })

    def test_unsplit_question_returns_agent_answer(self) -> None:
        service = make_service(FakeCompletion(rewrite=SINGLE_REWRITE))
        result = service.chat(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(result.answer, "đáp án 1")
        self.assertEqual(service.text_completion.calls, [])

    def test_empty_synthesis_becomes_empty_answer(self) -> None:
        service = make_service(FakeCompletion())
        service.text_completion = lambda prompt, params, on_text=None: ""
        self.assertEqual(service.chat(CONNECTION_ID, "câu hỏi", []).answer, "Chưa trả lời được câu hỏi này.")

    def test_synthesis_llm_error_becomes_agent_unavailable(self) -> None:
        service = make_service(FakeCompletion())
        service.text_completion = FakeText(error=APIConnectionError(request=httpx.Request("POST", "http://llm")))
        with self.assertRaises(Text2SqlAgentUnavailable):
            service.chat(CONNECTION_ID, "câu hỏi", [])


class FakeSession:
    def __init__(self) -> None:
        self.events: list[str] = []

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


class FakeConversations:
    def __init__(self, session: FakeSession, owned: SimpleNamespace | None = None, history=None) -> None:
        self.session = session
        self.owned = owned
        self.history = history or []
        self.calls: list[tuple] = []
        self.completed: dict = {}

    def get_owned(self, conversation_id, user_id, lock=False):
        self.calls.append(("get_owned", conversation_id, user_id))
        if self.owned is None or self.owned.id != conversation_id or self.owned.user_id != user_id:
            raise ConversationNotFoundError()
        return self.owned

    def recent_history(self, conversation_id, limit=6):
        self.calls.append(("recent_history", conversation_id, limit))
        return self.history

    def start(self, connection_id, user_id, question):
        self.calls.append(("start", connection_id, user_id, question))
        return SimpleNamespace(id=uuid4(), connection_id=connection_id, user_id=user_id)

    def begin_turn(self, conversation, question, continued_from=None):
        self.calls.append(("begin_turn", conversation.id, question))
        self.continued_from = continued_from
        return SimpleNamespace(id=uuid4(), conversation_id=conversation.id)

    def continuable_turn(self, conversation, turn_id):
        self.calls.append(("continuable_turn", conversation.id, turn_id))
        return SimpleNamespace(id=turn_id)

    def complete_turn(self, turn, **values):
        self.session.events.append(f"complete:{values['status']}")
        self.completed = values
        return turn


class MetricAgent(FakeAgent):
    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        step = AgentStepOut(
            tool="query_metric", arguments={"metric": "tong_luong_mua"}, sql="SELECT 1", columns=["thanh_pho", "mm"],
            rows=[["Huế", 182]], row_count=1,
        )
        failed = AgentStepOut(tool="run_sql", arguments={"sql": "SELECT x"}, error="Cột x không có.")
        return QuestionAnswerOut(
            position=item.position, question=item.question, answer=f"đáp án {item.position}", steps=[failed, step],
        )


def persisted_service(
    completion: FakeCompletion, owned: SimpleNamespace | None = None, history=None, agent: FakeAgent | None = None,
) -> tuple[ChatService, FakeSession, FakeConversations]:
    session = FakeSession()
    conversations = FakeConversations(session, owned, history)
    service = ChatService(
        session, SimpleNamespace(), FakeEmbedding(), completion, agent or FakeAgent(), conversations,
    )
    service.retrieval = FakeRetrieval()
    service.topic_search = FakeTopicSearch()
    service.text_completion = FakeText()
    return service, session, conversations


class ChatPersistenceTests(unittest.TestCase):
    def test_without_user_nothing_is_stored_and_client_history_is_used(self) -> None:
        completion = FakeCompletion(rewrite=SINGLE_REWRITE)
        service, session, conversations = persisted_service(completion)
        result = service.chat(CONNECTION_ID, "câu hỏi", [ChatHistoryTurnIn(question="câu trước", answer="đáp")])
        self.assertEqual(session.events, [])
        self.assertEqual(conversations.calls, [])
        self.assertIsNone(result.conversation_id)
        self.assertEqual([turn.question for turn in completion.calls[0][1]["chat_history"]], ["câu trước"])

    def test_user_without_conversation_starts_one_and_ignores_client_history(self) -> None:
        completion = FakeCompletion(rewrite=SINGLE_REWRITE)
        service, session, conversations = persisted_service(completion)
        result = service.chat(
            CONNECTION_ID, "câu hỏi", [ChatHistoryTurnIn(question="giả mạo")], user_id=" user-1 ",
        )
        self.assertEqual([call[0] for call in conversations.calls], ["start", "begin_turn"])
        self.assertEqual(conversations.calls[0][1:3], (CONNECTION_ID, "user-1"))
        self.assertEqual(completion.calls[0][1]["chat_history"], [])
        self.assertEqual(session.events, ["commit", "complete:answered", "commit"])
        self.assertEqual(result.conversation_id, conversations.calls[1][1])
        self.assertIsNotNone(result.turn_id)
        self.assertEqual(result.status, "answered")

    def test_existing_conversation_loads_history_from_stored_turns(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        stored = [HistoryTurn(question="câu đã lưu", answer="đáp án cũ")]
        completion = FakeCompletion(rewrite=SINGLE_REWRITE)
        service, _, conversations = persisted_service(completion, owned, stored)
        result = service.chat(
            CONNECTION_ID, "câu hỏi", [ChatHistoryTurnIn(question="giả mạo")], "user-1", owned.id,
        )
        self.assertEqual(conversations.calls[:2], [
            ("get_owned", owned.id, "user-1"), ("recent_history", owned.id, 6),
        ])
        self.assertNotIn("start", [call[0] for call in conversations.calls])
        self.assertEqual(completion.calls[0][1]["chat_history"], stored)
        self.assertEqual(result.conversation_id, owned.id)

    def test_conversation_of_another_user_is_not_found(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        agent = FakeAgent()
        service, session, _ = persisted_service(FakeCompletion(), owned, agent=agent)
        with self.assertRaises(ConversationNotFoundError):
            service.chat(CONNECTION_ID, "câu hỏi", [], "user-2", owned.id)
        self.assertEqual(agent.started, [])
        self.assertEqual(session.events, [])

    def test_conversation_of_another_connection_is_rejected(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=uuid4(), user_id="user-1")
        service, session, _ = persisted_service(FakeCompletion(), owned)
        with self.assertRaises(Text2SqlInvalidRequest):
            service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        self.assertEqual(session.events, [])

    def test_completed_turn_stores_answer_steps_and_results(self) -> None:
        service, _, conversations = persisted_service(FakeCompletion(), agent=MetricAgent())
        result = service.chat(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        values = conversations.completed
        self.assertEqual(values["status"], "answered")
        self.assertEqual(values["answer"], result.answer)
        self.assertEqual(values["rewritten_question"], REWRITE["rewritten_question"])
        self.assertEqual(values["flow"], "metric")
        self.assertEqual([item["position"] for item in values["steps"]], [1, 2])
        self.assertEqual([step["error"] for step in values["steps"][0]["steps"]], ["Cột x không có.", None])
        self.assertNotIn("rows", values["steps"][0]["steps"][1])
        self.assertEqual(len(values["results"]), 2)
        first = values["results"][0]
        self.assertEqual(first["kind"], "metric")
        self.assertEqual(first["metric"], {"name": "tong_luong_mua"})
        self.assertEqual(first["rows"], [["Huế", 182]])
        self.assertEqual(values["rewrite"]["questions"][0]["metrics"], ["tong_luong_mua"])
        self.assertNotIn("knowledge", values["rewrite"]["questions"][0])
        self.assertIsInstance(values["duration_ms"], int)

    def test_llm_failure_marks_turn_as_error(self) -> None:
        service, session, conversations = persisted_service(FakeCompletion(OutputParserException("bad json")))
        with self.assertRaises(Text2SqlAgentUnavailable):
            service.chat(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        self.assertEqual(session.events, ["commit", "rollback", "complete:error", "commit"])
        self.assertEqual(conversations.completed["error_code"], Text2SqlAgentUnavailable.code)

    def test_unexpected_failure_stores_only_error_type(self) -> None:
        service, _, conversations = persisted_service(FakeCompletion(RuntimeError("chi tiết nội bộ")))
        with self.assertRaises(RuntimeError):
            service.chat(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        self.assertEqual(conversations.completed["error_code"], "internal_error")
        self.assertEqual(conversations.completed["error_message"], "RuntimeError")

    def test_clarification_marks_turn_needs_clarification(self) -> None:
        outcome = turn_outcome(ChatRun(
            state={}, clarification=Clarification("Bạn muốn xem thành phố nào?", ["Huế"], [1]), snapshot=b"x",
        ))
        self.assertEqual(outcome.status, "needs_clarification")
        self.assertEqual(outcome.answer, "Bạn muốn xem thành phố nào?")
        self.assertEqual(outcome.clarification_options, ["Huế"])


class FakeCheckpoints:
    def __init__(self) -> None:
        self.rows: dict = {}
        self.purged = 0

    def locked(self, checkpoint_id, now):
        row = self.rows.get(checkpoint_id)
        return row if row is not None and row.expires_at > now else None

    def add(self, checkpoint) -> None:
        self.rows[checkpoint.id] = checkpoint

    def remove(self, checkpoint) -> None:
        del self.rows[checkpoint.id]

    def purge_expired(self, now) -> int:
        self.purged += 1
        return 0


class ClarifyingAgent(FakeAgent):
    def __init__(self, asking: int = 2, fail_on_reply: bool = False) -> None:
        super().__init__()
        self.asking = asking
        self.fail_on_reply = fail_on_reply
        self.calls: list[tuple[int, str | None]] = []

    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        self.calls.append((item.position, reply))
        if reply is not None and self.fail_on_reply:
            raise Text2SqlAgentUnavailable()
        if item.position == self.asking and pending is None:
            pause = ToolAgentPause("ask", "ask_user", {"question": "Thành phố nào?"}, [HumanMessage("ngữ cảnh")], 1)
            step = AgentStepOut(tool="ask_user", arguments={"question": "Thành phố nào?"})
            return PendingQuestion(item.position, "Thành phố nào?", ["Huế", "Vinh"], pause, [step])
        suffix = f" ({reply})" if reply else ""
        answer = f"đáp án {item.position}{suffix}"
        return QuestionAnswerOut(position=item.position, question=item.question, answer=answer)


def clarifying_service(
    agent: ClarifyingAgent, owned: SimpleNamespace | None = None, completion: FakeCompletion | None = None,
) -> tuple[ChatService, FakeSession, FakeConversations, FakeCheckpoints]:
    session = FakeSession()
    conversations = FakeConversations(session, owned)
    checkpoints = FakeCheckpoints()
    service = ChatService(
        session, SimpleNamespace(), FakeEmbedding(), completion or FakeCompletion(), agent, conversations, checkpoints,
    )
    service.retrieval = FakeRetrieval()
    service.topic_search = FakeTopicSearch()
    service.text_completion = FakeText()
    return service, session, conversations, checkpoints


class ChatClarificationTests(unittest.TestCase):
    def test_stateless_pause_then_resume_without_recomputing(self) -> None:
        agent = ClarifyingAgent()
        completion = FakeCompletion()
        service, session, _, checkpoints = clarifying_service(agent, completion=completion)
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(paused.status, "needs_clarification")
        self.assertEqual(paused.answer, "Thành phố nào?")
        self.assertEqual(paused.clarification_options, ["Huế", "Vinh"])
        self.assertEqual([item.position for item in paused.answers], [1])
        self.assertIsNotNone(paused.resume_id)
        self.assertIsNone(paused.conversation_id)
        stored = checkpoints.rows[paused.resume_id]
        self.assertIsNone(stored.user_id)
        self.assertEqual(stored.expires_at, paused.resume_expires_at)
        self.assertEqual(session.events, ["commit"])
        calls_before = len(completion.calls)
        resumed = service.chat(CONNECTION_ID, "Huế", [], resume_id=paused.resume_id)
        self.assertEqual(resumed.status, "answered")
        self.assertIsNone(resumed.resume_id)
        self.assertEqual(agent.calls, [(1, None), (2, None), (2, "Huế")])
        self.assertEqual(completion.calls[calls_before:], [])
        self.assertEqual(len(service.text_completion.calls), 1)
        self.assertEqual(resumed.answer, "đáp án 1 / đáp án 2 (Huế)")
        self.assertEqual(checkpoints.rows, {})

    def test_unknown_or_expired_resume_id_is_not_found(self) -> None:
        agent = ClarifyingAgent()
        service, _, _, checkpoints = clarifying_service(agent)
        with self.assertRaises(Text2SqlClarificationNotFound):
            service.chat(CONNECTION_ID, "Huế", [], resume_id=uuid4())
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        checkpoints.rows[paused.resume_id].expires_at = utc_now() - timedelta(seconds=1)
        with self.assertRaises(Text2SqlClarificationNotFound):
            service.chat(CONNECTION_ID, "Huế", [], resume_id=paused.resume_id)
        self.assertEqual(len(agent.started), 1)

    def test_resume_by_another_owner_or_connection_is_not_found(self) -> None:
        service, _, _, checkpoints = clarifying_service(ClarifyingAgent())
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        with self.assertRaises(Text2SqlClarificationNotFound):
            service.chat(CONNECTION_ID, "Huế", [], user_id="user-1", resume_id=paused.resume_id)
        with self.assertRaises(Text2SqlClarificationNotFound):
            service.chat(uuid4(), "Huế", [], resume_id=paused.resume_id)
        self.assertIn(paused.resume_id, checkpoints.rows)

    def test_conversation_turn_pauses_and_answer_continues_it(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        agent = ClarifyingAgent()
        service, _, conversations, checkpoints = clarifying_service(agent, owned)
        paused = service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        values = conversations.completed
        self.assertEqual(values["status"], "needs_clarification")
        self.assertEqual(values["clarification_question"], "Thành phố nào?")
        self.assertEqual(values["clarification_options"], ["Huế", "Vinh"])
        self.assertEqual(values["continuation"]["kind"], "text2sql_clarification")
        self.assertEqual(values["continuation"]["resume_id"], str(paused.resume_id))
        stored = checkpoints.rows[paused.resume_id]
        self.assertEqual((stored.user_id, stored.conversation_id, stored.turn_id), ("user-1", owned.id, paused.turn_id))
        with self.assertRaises(Text2SqlClarificationNotFound):
            service.chat(CONNECTION_ID, "Huế", [], user_id="user-1", resume_id=paused.resume_id)
        resumed = service.chat(CONNECTION_ID, "Huế", [], "user-1", owned.id, paused.resume_id)
        self.assertIn(("continuable_turn", owned.id, paused.turn_id), conversations.calls)
        self.assertEqual(conversations.continued_from, paused.turn_id)
        self.assertEqual(conversations.completed["status"], "answered")
        self.assertIsNone(conversations.completed["continuation"])
        self.assertEqual([item["position"] for item in conversations.completed["steps"]], [1, 2])
        self.assertNotEqual(resumed.turn_id, paused.turn_id)
        self.assertEqual(checkpoints.rows, {})

    def test_failed_resume_restores_checkpoint(self) -> None:
        agent = ClarifyingAgent(fail_on_reply=True)
        service, session, _, checkpoints = clarifying_service(agent)
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        with self.assertRaises(Text2SqlAgentUnavailable):
            service.chat(CONNECTION_ID, "Huế", [], resume_id=paused.resume_id)
        self.assertIn(paused.resume_id, checkpoints.rows)
        self.assertEqual(session.events[-2:], ["rollback", "commit"])

    def test_failed_save_after_resume_marks_turn_and_restores_checkpoint(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        service, session, conversations, checkpoints = clarifying_service(ClarifyingAgent(), owned)
        paused = service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        complete_turn = conversations.complete_turn

        def failing_complete(turn, **values):
            if values["status"] == "answered":
                raise RuntimeError("database down")
            return complete_turn(turn, **values)

        conversations.complete_turn = failing_complete
        with self.assertRaises(RuntimeError):
            service.chat(CONNECTION_ID, "Huế", [], "user-1", owned.id, paused.resume_id)
        self.assertEqual(conversations.completed["status"], "error")
        self.assertIn(paused.resume_id, checkpoints.rows)
        self.assertEqual(session.events[-2:], ["rollback", "commit"])


class ChatRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = SimpleNamespace(get=lambda model, key: object() if key == CONNECTION_ID else None)
        app.dependency_overrides[get_database] = lambda: self.session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def post(self, connection_id, completion: FakeCompletion):
        app.dependency_overrides[get_chat_service] = lambda: make_service(completion)
        return self.client.post(
            "/api/v1/text2sql/chat", json={"connection_id": str(connection_id), "question": "câu hỏi"}
        )

    def test_returns_answer_with_preprocess(self) -> None:
        response = self.post(CONNECTION_ID, FakeCompletion())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "đáp án 1 / đáp án 2")
        self.assertEqual([item["position"] for item in body["answers"]], [1, 2])
        preprocess = body["preprocess"]
        self.assertEqual(preprocess["stages"], [[1], [2]])
        self.assertEqual(preprocess["questions"][1]["depends_on"], [1])
        self.assertEqual(preprocess["questions"][0]["knowledge"]["metrics"][0]["metric_id"], str(METRIC_ID))
        self.assertEqual(
            sorted(preprocess["questions"][0]["knowledge"]),
            ["columns", "expert_rules", "glossary", "metrics", "own_knowledge", "tables"],
        )

    def test_unknown_connection_is_not_found(self) -> None:
        response = self.post(uuid4(), FakeCompletion())
        self.assertEqual(response.status_code, 404)

    def test_llm_failure_is_service_unavailable(self) -> None:
        response = self.post(CONNECTION_ID, FakeCompletion(OutputParserException("bad json")))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], Text2SqlAgentUnavailable.message)

    def test_unknown_resume_id_is_not_found(self) -> None:
        app.dependency_overrides[get_chat_service] = lambda: clarifying_service(ClarifyingAgent())[0]
        response = self.client.post("/api/v1/text2sql/chat", json={
            "connection_id": str(CONNECTION_ID), "question": "Huế", "resume_id": str(uuid4()),
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], Text2SqlClarificationNotFound.message)

    def test_conversation_without_user_is_rejected(self) -> None:
        response = self.client.post("/api/v1/text2sql/chat", json={
            "connection_id": str(CONNECTION_ID), "question": "câu hỏi", "conversation_id": str(uuid4()),
        })
        self.assertEqual(response.status_code, 422)

    def test_blank_question_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/text2sql/chat", json={"connection_id": str(CONNECTION_ID), "question": "   "}
        )
        self.assertEqual(response.status_code, 422)


PARALLEL_REWRITE = {
    **REWRITE,
    "sub_questions": [{**item, "depends_on": []} for item in REWRITE["sub_questions"]],
    "execution_mode": "parallel",
}


class StreamSession(FakeSession):
    def get(self, model, key):
        return object() if key == CONNECTION_ID else None


class StreamingAgent(FakeAgent):
    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        self.prior[item.position] = [answer.position for answer in prior]
        step = AgentStepOut(
            tool="query_metric", arguments={"metric": "tong_luong_mua"}, sql="SELECT 1", columns=["thanh_pho", "mm"],
            rows=[["Huế", 182]], row_count=1,
        )
        if emit is not None:
            emit("tool", step_event(item.position, step))
        return QuestionAnswerOut(
            position=item.position, question=item.question, answer=f"đáp án {item.position}", steps=[step],
        )


def stream_service(
    completion: FakeCompletion, agent: FakeAgent | None = None, owned: SimpleNamespace | None = None,
) -> tuple[ChatService, StreamSession, FakeConversations, FakeCheckpoints]:
    session = StreamSession()
    conversations = FakeConversations(session, owned)
    checkpoints = FakeCheckpoints()
    service = ChatService(
        session, SimpleNamespace(), FakeEmbedding(), completion, agent or StreamingAgent(), conversations, checkpoints,
    )
    service.retrieval = FakeRetrieval()
    service.topic_search = FakeTopicSearch()
    service.text_completion = FakeText()
    return service, session, conversations, checkpoints


def read_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        lines = block.strip().splitlines()
        names = [line[len("event: "):] for line in lines if line.startswith("event: ")]
        data = [line[len("data: "):] for line in lines if line.startswith("data: ")]
        if names:
            events.append((names[0], json.loads(data[0])))
    return events


class ChatStreamRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def stream(self, service: ChatService, **body):
        app.dependency_overrides[get_chat_service_factory] = lambda: (lambda: nullcontext(service))
        payload = {"connection_id": str(CONNECTION_ID), "question": "câu hỏi", **body}
        return self.client.post("/api/v1/text2sql/chat/stream", json=payload)

    def test_streams_every_graph_step_then_done(self) -> None:
        service, *_ = stream_service(FakeCompletion())
        response = self.stream(service)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = read_events(response.text)
        self.assertEqual([name for name, _ in events], [
            "preprocess", "question_started", "tool", "question_answered", "question_started", "tool",
            "question_answered", "synthesize_started", "answer_delta", "answer", "done",
        ])
        self.assertEqual(events[8][1], {"position": None, "round": 0, "final": True, "text": "đáp án 1 / đáp án 2"})
        preprocess = events[0][1]
        self.assertEqual(preprocess["stages"], [[1], [2]])
        self.assertEqual(preprocess["questions"][0]["metrics"], [{"name": "tong_luong_mua", "label": "Tổng lượng mưa"}])
        self.assertEqual(preprocess["questions"][0]["glossary"], ["glossary"])
        tool = events[2][1]
        self.assertEqual((tool["position"], tool["tool"], tool["rows"]), (1, "query_metric", [["Huế", 182]]))
        self.assertEqual(events[3][1], {
            "position": 1, "question": "Thành phố nào mưa nhiều nhất tuần qua?", "answer": "đáp án 1",
            "exhausted": False,
        })
        self.assertEqual(events[-2][1], {"answer": "đáp án 1 / đáp án 2"})
        done = events[-1][1]
        self.assertEqual((done["status"], done["answer"]), ("answered", "đáp án 1 / đáp án 2"))
        self.assertIsNone(done["conversation_id"])
        self.assertIsNone(done["resume_id"])

    def test_parallel_branches_stream_their_steps(self) -> None:
        service, *_ = stream_service(FakeCompletion(rewrite=PARALLEL_REWRITE))
        events = read_events(self.stream(service).text)
        self.assertEqual(sorted(data["position"] for name, data in events if name == "tool"), [1, 2])
        self.assertEqual(sorted(data["position"] for name, data in events if name == "question_answered"), [1, 2])
        self.assertEqual(events[-1][0], "done")

    def test_recorded_turn_is_announced_first_and_completed(self) -> None:
        service, session, _, _ = stream_service(FakeCompletion(rewrite=SINGLE_REWRITE))
        events = read_events(self.stream(service, user_id="user-1").text)
        name, turn = events[0]
        self.assertEqual(name, "turn")
        self.assertIsNone(turn["continued_from"])
        done = events[-1][1]
        self.assertEqual((done["conversation_id"], done["turn_id"]), (turn["conversation_id"], turn["turn_id"]))
        self.assertEqual(session.events[-2:], ["complete:answered", "commit"])

    def test_failure_after_start_is_an_error_event(self) -> None:
        service, session, _, _ = stream_service(FakeCompletion(error=OutputParserException("hỏng")))
        response = self.stream(service, user_id="user-1")
        self.assertEqual(response.status_code, 200)
        events = read_events(response.text)
        self.assertEqual([name for name, _ in events], ["turn", "error"])
        self.assertEqual(events[1][1], {
            "code": "text2sql_agent_unavailable", "message": Text2SqlAgentUnavailable.message,
        })
        self.assertIn("complete:error", session.events)

    def test_errors_before_streaming_are_http_errors(self) -> None:
        service, *_ = stream_service(FakeCompletion())
        response = self.stream(service, connection_id=str(uuid4()))
        self.assertEqual(response.status_code, 404)
        response = self.stream(service, resume_id=str(uuid4()))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], Text2SqlClarificationNotFound.message)

    def test_clarification_event_then_resume_streams_the_rest(self) -> None:
        service, _, _, checkpoints = stream_service(FakeCompletion(), ClarifyingAgent())
        events = read_events(self.stream(service).text)
        names = [name for name, _ in events]
        self.assertEqual(names[-3:], ["question_waiting", "clarification", "done"])
        self.assertEqual(events[-3][1], {"position": 2, "question": "Thành phố nào?", "options": ["Huế", "Vinh"]})
        clarification, done = events[-2][1], events[-1][1]
        self.assertEqual(clarification["question"], "Thành phố nào?")
        self.assertEqual(clarification["options"], ["Huế", "Vinh"])
        self.assertIn(clarification["resume_id"], {str(key) for key in checkpoints.rows})
        self.assertEqual((done["status"], done["resume_id"]), ("needs_clarification", clarification["resume_id"]))
        resumed = read_events(self.stream(service, question="Huế", resume_id=clarification["resume_id"]).text)
        self.assertEqual([name for name, _ in resumed], [
            "question_started", "question_answered", "synthesize_started", "answer_delta", "answer", "done",
        ])
        self.assertTrue(resumed[0][1]["resumed"])
        self.assertEqual(resumed[-1][1]["answer"], "đáp án 1 / đáp án 2 (Huế)")
        self.assertEqual(checkpoints.rows, {})


class ChatStreamStopTests(unittest.TestCase):
    def test_stopped_stream_refuses_more_events(self) -> None:
        stream = ChatStream(lambda: nullcontext(None), SimpleNamespace())
        stream.stopped.set()
        with self.assertRaises(Text2SqlClientDisconnected):
            stream._emit("tool", {})

    def test_disconnect_stops_graph_and_marks_turn(self) -> None:
        agent = StreamingAgent()
        service, _, conversations, _ = stream_service(FakeCompletion(rewrite=SINGLE_REWRITE), agent)
        prepared = service.prepare(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        with self.assertRaises(Text2SqlClientDisconnected):
            service.execute(prepared, lambda event, data: None, should_stop=lambda: True)
        self.assertEqual(agent.prior, {})
        self.assertEqual(conversations.completed["status"], "error")
        self.assertEqual(conversations.completed["error_code"], "client_disconnected")

    def test_disconnect_during_resume_restores_checkpoint(self) -> None:
        service, _, _, checkpoints = stream_service(FakeCompletion(), ClarifyingAgent())
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        prepared = service.prepare(CONNECTION_ID, "Huế", [], resume_id=paused.resume_id)
        self.assertEqual(checkpoints.rows, {})
        with self.assertRaises(Text2SqlClientDisconnected):
            service.execute(prepared, lambda event, data: None, should_stop=lambda: True)
        self.assertIn(paused.resume_id, checkpoints.rows)


CHART = {"version": 1, "type": "bar", "encoding": {"x": {"field": "thanh_pho"}, "y": [{"field": "mm"}]}}


class ChartAgent(FakeAgent):
    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        step = AgentStepOut(
            tool="query_metric", arguments={"metric": "tong_luong_mua"}, sql="SELECT 1", columns=["thanh_pho", "mm"],
            rows=[["Huế", 182], ["Vinh", 3], ["Hà Nội", 1]], row_count=3, result_id=f"{item.position}-1",
            fields=[{"name": "thanh_pho", "label": "Thành phố", "type": "text"},
                    {"name": "mm", "label": "Lượng mưa", "type": "number", "role": "measure", "unit": "mm"}],
            explanations=[{"kind": "metric", "text": "Chỉ số: Tổng lượng mưa", "name": "tong_luong_mua"}],
            chart=CHART, chart_source="auto", chart_types=["bar", "table"], display="chart_if_last",
        )
        return QuestionAnswerOut(position=item.position, question=item.question, answer="đáp án", steps=[step])


class ChartFieldsTests(unittest.TestCase):
    def test_stored_steps_and_results_carry_chart_fields(self) -> None:
        service, _, conversations = persisted_service(FakeCompletion(), agent=ChartAgent())
        service.chat(CONNECTION_ID, "câu hỏi", [], user_id="user-1")
        step = conversations.completed["steps"][0]["steps"][0]
        self.assertEqual(step["result_id"], "1-1")
        self.assertEqual(step["explanations"], [{"kind": "metric", "text": "Chỉ số: Tổng lượng mưa",
                                                 "name": "tong_luong_mua"}])
        self.assertEqual((step["chart"], step["chart_source"], step["display"]), (CHART, "auto", "chart_if_last"))
        result = conversations.completed["results"][0]
        self.assertEqual(result["result_id"], "1-1")
        self.assertEqual([item["name"] for item in result["fields"]], ["thanh_pho", "mm"])
        self.assertEqual((result["chart"], result["chart_types"], result["display"]),
                         (CHART, ["bar", "table"], "chart_if_last"))

    def test_chat_json_has_new_step_fields(self) -> None:
        session = SimpleNamespace(get=lambda model, key: object())
        app.dependency_overrides[get_database] = lambda: session
        app.dependency_overrides[get_chat_service] = lambda: make_service(FakeCompletion(), agent=ChartAgent())
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/text2sql/chat", json={"connection_id": str(CONNECTION_ID), "question": "câu hỏi"},
                )
        finally:
            app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 200, response.text)
        step = response.json()["answers"][0]["steps"][0]
        self.assertEqual(step["result_id"], "1-1")
        self.assertEqual(step["fields"][1]["unit"], "mm")
        self.assertEqual(step["explanations"][0]["kind"], "metric")
        self.assertEqual((step["chart"]["type"], step["chart_source"], step["display"]),
                         ("bar", "auto", "chart_if_last"))
        self.assertEqual(step["chart_types"], ["bar", "table"])

    def test_old_snapshot_step_loads_and_result_ids_continue(self) -> None:
        old = {
            "tool": "query_metric", "arguments": {"metric": "tong_luong_mua"}, "sql": "SELECT 1",
            "columns": ["thanh_pho", "value"], "rows": [["Huế", 12.5]], "row_count": 1, "truncated": False,
            "notes": [], "error": None,
        }
        payload = ormsgpack.packb(ormsgpack.Ext(5, ormsgpack.packb([
            AgentStepOut.__module__, "AgentStepOut", old, "model_validate_json",
        ])))
        step = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES).loads_typed(("msgpack", payload))
        self.assertEqual((step.result_id, step.fields, step.chart, step.display), (None, [], None, None))
        def runner(sql, max_rows):
            return QueryRows(columns=["thanh_pho", "value"], rows=[("Huế", 12.5)], truncated=False, elapsed_ms=1)

        column = ColumnInfo("thanh_pho", "text", "Thành phố", None, (), False)
        table = TableInfo(TABLE_ID, "weather", "daily", "Thời tiết ngày", None, None, (column,))
        catalog = AgentCatalog(tables={TABLE_ID: table}, metrics={}, rules=[])
        toolkit = Text2SqlToolkit(catalog, QueryCache(runner=runner, max_rows=10), 50, [step])
        output = toolkit.run_sql("SELECT thanh_pho, 1 AS value FROM weather.daily", "Thử")
        self.assertEqual(output["result_id"], "1-2")


if __name__ == "__main__":
    unittest.main()
