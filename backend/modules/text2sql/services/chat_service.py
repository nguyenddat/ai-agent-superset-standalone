import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from langchain_core.exceptions import OutputParserException
from openai import OpenAIError
from sqlalchemy.orm import Session

from backend.agent_package.get_chat_completion import get_chat_completion
from backend.agent_package.get_chat_text import get_chat_text
from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.agent_package.prompts.prompt_synthesize import synthesize_prompt
from backend.common.base_exceptions import AppError
from backend.common.base_model import utc_now
from backend.core.setting import config
from backend.modules.conversation.models import Conversation, ConversationTurn
from backend.modules.conversation.services import ConversationService, HistoryTurn
from backend.modules.conversation.services.conversation_service import (
    HISTORY_ANSWER_LENGTH,
    clip,
)

from ..models import ChatCheckpoint
from ..repositories import ChatCheckpointRepository, QdrantRepository
from ..schemas import (
    AgentStepOut,
    CandidateOut,
    ChatHistoryTurnIn,
    ChatOut,
    KnowledgeHitOut,
    PreprocessedQuestionOut,
    PreprocessOut,
    QuestionAnswerOut,
    QuestionKnowledgeOut,
)
from ..utils.exceptions import (
    Text2SqlAgentUnavailable,
    Text2SqlClarificationNotFound,
    Text2SqlInvalidRequest,
)
from ..utils.topics import COLUMN, EXPERT_RULE, GLOSSARY, OWN_KNOWLEDGE, TABLE
from .chat_events import Emit
from .chat_graph import ChatGraphContext, ChatRun, TextCallback, never, run_chat_graph
from .display_format import today_label
from .retrieval_service import RetrievalService
from .text2sql_agent_service import EMPTY_ANSWER, AgentRun, Text2SqlAgentService
from .topic_search_service import TopicSearchService

logger = logging.getLogger("text2sql.chat")

CLARIFICATION_KIND = "text2sql_clarification"
HISTORY_LIMIT = 6
MAX_PARALLEL_CALLS = 4
TOP_K = 5
KNOWLEDGE_TOPICS = (("tables", TABLE), ("columns", COLUMN), ("glossary", GLOSSARY), ("expert_rules", EXPERT_RULE))

DATA_TOOLS = {"query_metric": "metric", "run_sql": "sql", "get_column_values": "column_values"}

Completion = Callable[[str, dict[str, Any]], dict[str, Any]]
TextCompletion = Callable[[str, dict[str, Any], TextCallback | None], str]
History = Sequence[ChatHistoryTurnIn | HistoryTurn]


@dataclass
class TurnRecord:
    conversation: Conversation
    turn: ConversationTurn
    started: float


@dataclass(frozen=True)
class PausedRun:
    id: UUID
    connection_id: UUID
    user_id: str | None
    conversation_id: UUID | None
    turn_id: UUID | None
    snapshot: bytes
    expires_at: datetime


@dataclass(frozen=True)
class SavedPause:
    id: UUID
    expires_at: datetime


@dataclass(frozen=True)
class PreparedChat:
    connection_id: UUID
    question: str
    user_id: str | None
    history: History
    agent_run: AgentRun
    paused: PausedRun | None
    record: TurnRecord | None


@dataclass(frozen=True)
class TurnOutcome:
    status: str
    answer: str
    clarification_question: str | None = None
    clarification_options: list[str] = field(default_factory=list)


def turn_outcome(run: ChatRun) -> TurnOutcome:
    clarification = run.clarification
    if clarification is not None:
        return TurnOutcome(
            "needs_clarification", clarification.question, clarification.question, list(clarification.options),
        )
    return TurnOutcome("answered", run.state["answer"])


def stored_rewrite(preprocess: PreprocessOut) -> dict[str, Any]:
    return {
        "rewritten_question": preprocess.rewritten_question, "is_split": preprocess.is_split,
        "execution_mode": preprocess.execution_mode, "stages": preprocess.stages,
        "questions": [
            {
                "position": item.position, "question": item.question, "depends_on": item.depends_on,
                "question_type": item.question_type, "business_concepts": item.business_concepts,
                "metrics": [metric.name for metric in item.knowledge.metrics],
            }
            for item in preprocess.questions
        ],
    }


def dumped(item: Any, exclude_none: bool = False) -> dict[str, Any]:
    if isinstance(item, dict):
        return {key: value for key, value in item.items() if value is not None or not exclude_none}
    return item.model_dump(mode="json", exclude_none=exclude_none)


def stored_step(step: AgentStepOut) -> dict[str, Any]:
    stored: dict[str, Any] = {
        "tool": step.tool, "arguments": step.arguments, "sql": step.sql, "row_count": step.row_count,
        "truncated": step.truncated, "notes": step.notes, "error": step.error,
    }
    if step.result_id is not None:
        stored["result_id"] = step.result_id
    if step.explanations:
        stored["explanations"] = [dumped(item, exclude_none=True) for item in step.explanations]
    if step.chart is not None:
        stored.update({"chart": step.chart, "chart_source": step.chart_source, "display": step.display})
    return stored


def stored_steps(answers: Sequence[QuestionAnswerOut]) -> list[dict[str, Any]]:
    return [
        {
            "position": item.position, "question": item.question, "answer": item.answer,
            "exhausted": item.exhausted,
            "steps": [stored_step(step) for step in item.steps],
        }
        for item in answers
    ]


def stored_results(answers: Sequence[QuestionAnswerOut]) -> list[dict[str, Any]]:
    results = []
    for item in answers:
        for step in item.steps:
            if step.error is not None or step.tool not in DATA_TOOLS:
                continue
            result: dict[str, Any] = {
                "position": item.position, "kind": DATA_TOOLS[step.tool], "tool": step.tool, "sql": step.sql,
                "columns": step.columns, "rows": step.rows, "row_count": step.row_count, "truncated": step.truncated,
            }
            if step.tool == "query_metric":
                result["metric"] = {"name": step.arguments.get("metric")}
            if step.result_id is not None:
                result.update({
                    "result_id": step.result_id,
                    "fields": [dumped(item) for item in step.fields],
                    "chart": step.chart, "chart_source": step.chart_source, "chart_types": step.chart_types,
                    "display": step.display,
                })
            results.append(result)
    return results


def turn_flow(results: Sequence[dict[str, Any]]) -> str:
    kinds = {result["kind"] for result in results}
    if "metric" in kinds:
        return "metric"
    return "dataset" if "sql" in kinds else "none"


def execution_stages(depends_on: Sequence[Sequence[int]]) -> list[list[int]]:
    levels: list[int] = []
    for dependencies in depends_on:
        levels.append(1 + max((levels[dependency - 1] for dependency in dependencies), default=-1))
    return [
        [position for position, level in enumerate(levels, start=1) if level == stage]
        for stage in range(max(levels, default=-1) + 1)
    ]


class ChatService:
    def __init__(
        self, session: Session, index: QdrantRepository, embedding: OpenRouterEmbedding,
        completion: Completion = get_chat_completion, agent: Text2SqlAgentService | None = None,
        conversations: ConversationService | None = None, checkpoints: ChatCheckpointRepository | None = None,
        text_completion: TextCompletion = get_chat_text,
    ) -> None:
        self.session = session
        self.embedding = embedding
        self.completion = completion
        self.text_completion = text_completion
        self.agent = agent or Text2SqlAgentService(session)
        self.conversations = conversations or ConversationService(session)
        self.checkpoints = checkpoints or ChatCheckpointRepository(session)
        self.retrieval = RetrievalService(session, index, embedding)
        self.topic_search = TopicSearchService(session, index, embedding)

    def chat(
        self, connection_id: UUID, question: str, chat_history: Sequence[ChatHistoryTurnIn],
        user_id: str | None = None, conversation_id: UUID | None = None, resume_id: UUID | None = None,
    ) -> ChatOut:
        return self.execute(self.prepare(connection_id, question, chat_history, user_id, conversation_id, resume_id))

    def prepare(
        self, connection_id: UUID, question: str, chat_history: Sequence[ChatHistoryTurnIn],
        user_id: str | None = None, conversation_id: UUID | None = None, resume_id: UUID | None = None,
    ) -> PreparedChat:
        user = (user_id or "").strip() or None
        if conversation_id is not None and user is None:
            raise Text2SqlInvalidRequest("Cần user_id khi gửi conversation_id.")
        conversation = self._owned_conversation(connection_id, user, conversation_id)
        paused = self._claim(resume_id, connection_id, user, conversation) if resume_id is not None else None
        history: History = [] if paused is not None else chat_history if user is None else (
            self.conversations.recent_history(conversation.id, HISTORY_LIMIT) if conversation else []
        )
        agent_run = self.agent.start(connection_id)
        record = self._begin_turn(connection_id, user, conversation, question, paused) if user else None
        if record is None and paused is not None:
            self.session.commit()
        return PreparedChat(connection_id, question, user, history, agent_run, paused, record)

    def execute(
        self, prepared: PreparedChat, emit: Emit | None = None, should_stop: Callable[[], bool] = never,
    ) -> ChatOut:
        connection_id, user, paused, record = prepared.connection_id, prepared.user_id, prepared.paused, prepared.record
        thread_id = paused.id if paused is not None else uuid4()
        try:
            if emit is not None and record is not None:
                emit("turn", {
                    "conversation_id": record.conversation.id, "turn_id": record.turn.id,
                    "continued_from": paused.turn_id if paused is not None else None,
                })
            today = prepared.agent_run.today

            def synthesize(
                preprocess: PreprocessOut, answers: list[QuestionAnswerOut], on_text: TextCallback | None = None,
            ) -> str:
                return self._synthesize(preprocess, answers, on_text, today)

            result = run_chat_graph(
                ChatGraphContext(
                    preprocess=lambda: self.preprocess(connection_id, prepared.question, prepared.history, user),
                    answer_question=prepared.agent_run.answer, synthesize=synthesize,
                    should_stop=should_stop, streaming=emit is not None,
                ),
                str(thread_id), reply=prepared.question if paused is not None else None,
                snapshot=paused.snapshot if paused is not None else None, on_event=emit,
            )
            state = result.state
            answers = [state["answers"][position] for position in sorted(state.get("answers", {}))]
            outcome = turn_outcome(result)
            pause = None
            if result.snapshot is not None:
                pause = self._save_pause(thread_id, connection_id, user, record, result.snapshot)
            if record is not None:
                self._complete_turn(record, outcome, state["preprocess"], answers, pause)
            elif pause is not None:
                self.session.commit()
        except Exception as error:
            if record is not None:
                self._fail_turn(record, error)
            if paused is not None:
                self._restore(paused)
            raise
        return ChatOut(
            answer=outcome.answer, status=outcome.status, clarification_question=outcome.clarification_question,
            clarification_options=outcome.clarification_options,
            resume_id=pause.id if pause else None, resume_expires_at=pause.expires_at if pause else None,
            preprocess=state["preprocess"], answers=answers,
            conversation_id=record.conversation.id if record else None, turn_id=record.turn.id if record else None,
        )

    def _claim(
        self, resume_id: UUID, connection_id: UUID, user_id: str | None, conversation: Conversation | None,
    ) -> PausedRun:
        row = self.checkpoints.locked(resume_id, utc_now())
        owner = (connection_id, user_id, conversation.id if conversation is not None else None)
        if row is None or (row.connection_id, row.user_id, row.conversation_id) != owner:
            raise Text2SqlClarificationNotFound()
        if conversation is not None and row.turn_id is not None:
            self.conversations.continuable_turn(conversation, row.turn_id)
        paused = PausedRun(
            id=row.id, connection_id=row.connection_id, user_id=row.user_id, conversation_id=row.conversation_id,
            turn_id=row.turn_id, snapshot=row.snapshot, expires_at=row.expires_at,
        )
        self.checkpoints.remove(row)
        return paused

    def _save_pause(
        self, thread_id: UUID, connection_id: UUID, user_id: str | None, record: TurnRecord | None, snapshot: bytes,
    ) -> SavedPause:
        now = utc_now()
        expires_at = now + timedelta(minutes=config.text2sql_clarification_ttl_minutes)
        self.checkpoints.purge_expired(now)
        self.checkpoints.add(ChatCheckpoint(
            id=thread_id, connection_id=connection_id, user_id=user_id,
            conversation_id=record.conversation.id if record else None, turn_id=record.turn.id if record else None,
            snapshot=snapshot, expires_at=expires_at,
        ))
        return SavedPause(thread_id, expires_at)

    def _restore(self, paused: PausedRun) -> None:
        try:
            self.session.rollback()
            self.checkpoints.add(ChatCheckpoint(
                id=paused.id, connection_id=paused.connection_id, user_id=paused.user_id,
                conversation_id=paused.conversation_id, turn_id=paused.turn_id, snapshot=paused.snapshot,
                expires_at=paused.expires_at,
            ))
            self.session.commit()
        except Exception:
            logger.exception("Không khôi phục được câu hỏi lại %s", paused.id)
            self.session.rollback()

    def _owned_conversation(
        self, connection_id: UUID, user_id: str | None, conversation_id: UUID | None
    ) -> Conversation | None:
        if user_id is None or conversation_id is None:
            return None
        conversation = self.conversations.get_owned(conversation_id, user_id)
        if conversation.connection_id != connection_id:
            raise Text2SqlInvalidRequest("Hội thoại thuộc connection khác.")
        return conversation

    def _begin_turn(
        self, connection_id: UUID, user_id: str, conversation: Conversation | None, question: str,
        paused: PausedRun | None = None,
    ) -> TurnRecord:
        conversation = conversation or self.conversations.start(connection_id, user_id, question)
        turn = self.conversations.begin_turn(
            conversation, question, continued_from=paused.turn_id if paused is not None else None,
        )
        self.session.commit()
        return TurnRecord(conversation, turn, time.monotonic())

    def _complete_turn(
        self, record: TurnRecord, outcome: TurnOutcome, preprocess: PreprocessOut, answers: list[QuestionAnswerOut],
        pause: SavedPause | None = None,
    ) -> None:
        results = stored_results(answers)
        continuation = {
            "kind": CLARIFICATION_KIND, "resume_id": str(pause.id), "expires_at": pause.expires_at.isoformat(),
        } if pause is not None else None
        self.conversations.complete_turn(
            record.turn, status=outcome.status, flow=turn_flow(results), answer=outcome.answer,
            rewritten_question=preprocess.rewritten_question, steps=stored_steps(answers), results=results,
            rewrite=stored_rewrite(preprocess), duration_ms=self._elapsed(record),
            clarification_question=outcome.clarification_question,
            clarification_options=outcome.clarification_options, continuation=continuation,
        )
        self.session.commit()

    def _fail_turn(self, record: TurnRecord, error: Exception) -> None:
        known = isinstance(error, AppError)
        try:
            self.session.rollback()
            self.conversations.complete_turn(
                record.turn, status="error", error_code=error.code if known else "internal_error",
                error_message=str(error) if known else type(error).__name__, duration_ms=self._elapsed(record),
            )
            self.session.commit()
        except Exception:
            logger.exception("Không ghi được lỗi của lượt %s", record.turn.id)
            self.session.rollback()

    @staticmethod
    def _elapsed(record: TurnRecord) -> int:
        return int((time.monotonic() - record.started) * 1000)

    def preprocess(
        self, connection_id: UUID, question: str, chat_history: History, user_id: str | None = None,
    ) -> PreprocessOut:
        rewrite = self._complete("rewrite", {"question": question, "chat_history": self._history(chat_history)})
        questions = rewrite["sub_questions"] or [{"question": rewrite["rewritten_question"], "depends_on": []}]
        texts = [item["question"] for item in questions]
        with ThreadPoolExecutor(max_workers=min(len(texts), MAX_PARALLEL_CALLS)) as pool:
            intent_futures = [pool.submit(self._complete, "intent_classify", {"question": text}) for text in texts]
            knowledge = self._retrieve(connection_id, texts, user_id)
            intents = [future.result() for future in intent_futures]
        return PreprocessOut(
            rewritten_question=rewrite["rewritten_question"],
            is_split=bool(rewrite["sub_questions"]),
            execution_mode=rewrite["execution_mode"],
            questions=[
                PreprocessedQuestionOut(
                    position=position, question=item["question"], depends_on=item["depends_on"],
                    question_type=intent["question_type"], business_concepts=intent["business_concepts"],
                    knowledge=item_knowledge,
                )
                for position, (item, intent, item_knowledge) in enumerate(
                    zip(questions, intents, knowledge, strict=True), start=1
                )
            ],
            stages=execution_stages([item["depends_on"] for item in questions]),
        )

    def _retrieve(self, connection_id: UUID, texts: list[str], user_id: str | None) -> list[QuestionKnowledgeOut]:
        vectors = self.embedding.embed(texts)
        return [
            self._knowledge(connection_id, text, vector, user_id)
            for text, vector in zip(texts, vectors, strict=True)
        ]

    def _knowledge(
        self, connection_id: UUID, text: str, vector: list[float], user_id: str | None
    ) -> QuestionKnowledgeOut:
        metrics = self.retrieval.search(connection_id, text, TOP_K, vector=vector).candidates
        hits = {field: self._hits(connection_id, topic, text, vector) for field, topic in KNOWLEDGE_TOPICS}
        own_knowledge = (
            self._hits(connection_id, OWN_KNOWLEDGE, text, vector, user_id) if user_id and user_id.strip() else []
        )
        return QuestionKnowledgeOut(
            metrics=[CandidateOut.model_validate(candidate.__dict__) for candidate in metrics],
            own_knowledge=own_knowledge, **hits,
        )

    def _hits(
        self, connection_id: UUID, topic: str, text: str, vector: list[float], user_id: str | None = None
    ) -> list[KnowledgeHitOut]:
        outcome = self.topic_search.search(connection_id, topic, text, TOP_K, user_id=user_id, vector=vector)
        return [
            KnowledgeHitOut(
                entity_id=hit.entity_id, table_id=hit.table_id, name=hit.name, display_name=hit.display_name,
                text=hit.text, score=hit.score,
            )
            for hit in outcome.hits
        ]

    def _history(self, chat_history: History) -> list[HistoryTurn]:
        return [
            turn if isinstance(turn, HistoryTurn) else HistoryTurn(
                question=turn.question, rewritten_question=turn.rewritten_question,
                answer=clip(turn.answer, HISTORY_ANSWER_LENGTH) if turn.answer else None,
                status=turn.status, clarification_question=turn.clarification_question,
            )
            for turn in list(chat_history)[-HISTORY_LIMIT:]
        ]

    def _synthesize(
        self, preprocess: PreprocessOut, answers: list[QuestionAnswerOut], on_text: TextCallback | None = None,
        today: date | None = None,
    ) -> str:
        types = {item.position: item.question_type for item in preprocess.questions}
        params = {
            "question": preprocess.rewritten_question,
            "today": today_label(today or date.today()),
            "answers": [
                {
                    "position": item.position, "question": item.question,
                    "question_type": types.get(item.position), "answer": item.answer,
                }
                for item in answers
            ],
        }
        try:
            text = self.text_completion(synthesize_prompt, params, on_text)
        except OpenAIError as error:
            logger.warning("LLM task 'synthesize' lỗi: %s", type(error).__name__)
            raise Text2SqlAgentUnavailable() from error
        return text or EMPTY_ANSWER

    def _complete(self, task: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.completion(task, params)
        except (OutputParserException, OpenAIError) as error:
            logger.warning("LLM task '%s' lỗi: %s", task, type(error).__name__)
            raise Text2SqlAgentUnavailable() from error
