import logging
from collections.abc import Callable, Generator, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from backend.agent_package.agents.analysis_agent import AnalysisAgent
from backend.agent_package.agents.dataset_plan_agent import DatasetPlanAgent
from backend.agent_package.agents.query_plan_agent import QueryPlanAgent
from backend.agent_package.agents.question_rewrite_agent import QuestionRewriteAgent
from backend.agent_package.get_chat_models import ReasoningDelta
from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.common.base_exceptions import AppError
from backend.core.database import get_session_factory
from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..common.errors import Text2SqlConnectionNotFound, Text2SqlInvalidRequest
from ..dataset.field_service import FieldService, FindFieldsOut
from ..dataset.join_schemas import JoinOption, JoinPlan
from ..dataset.join_service import JoinService
from ..dataset.schemas import DatasetQueryPlan
from ..dataset.selection import dataset_column_ids
from ..dataset.service import DatasetQueryService
from ..dataset.store import DatasetStore
from ..query.executor import run_read_only
from ..query.service import QueryService, Runner
from ..vector_store.ingestion.documents.context import CatalogContext, load_context
from ..vector_store.qdrant_db_service import QdrantDbService
from ..vector_store.rerank.base import Reranker
from ..vector_store.rerank.jev_reranker import JevReranker
from ..vector_store.retrieve.topic_search import TopicSearchService
from .analysis_context import ChatAnswer, build_analysis_context, dataset_report, metric_report
from .dataset_flow import (
    UUID_PATTERN,
    PlanMappingError,
    dataset_plan_context,
    describe_option,
    map_dataset_plan,
    sanitize_message,
)
from .events import ChatEvent, StepName, done, error, reasoning, step, token, turn
from .reasoning import (
    TO_DATASET,
    field_lines,
    join_lines,
    mapping_lines,
    metric_rule_lines,
    metric_search_lines,
    query_line,
    store_line,
)
from .schemas import RewriteInfo
from .service import NO_CANDIDATE_REASON, AskService, AskState, PreparedAsk
from .turns import JoinResume, TurnRecorder, TurnRequest, continuation_state, prepare_turn

logger = logging.getLogger("text2sql.chat")

CONFIRMATION = "not_supported"
INTERNAL_ERROR = "Hệ thống chưa xử lý được câu hỏi lúc này. Hãy thử lại sau."
NO_FIELDS_MESSAGE = (
    "Không tìm thấy cột dữ liệu nào đủ liên quan tới câu hỏi trong các bảng đã mô tả; hãy diễn đạt lại câu hỏi bằng "
    "tên trường hoặc thuật ngữ cụ thể hơn."
)
NOT_DECLARED_MESSAGE = (
    "Các bảng cần dùng chưa được khai báo quan hệ với nhau nên hệ thống không tự nối. {detail} Cần bổ sung khai báo "
    "quan hệ (cột tham chiếu) giữa các bảng trong data dictionary rồi hỏi lại."
)
AMBIGUOUS_MESSAGE = "Có nhiều cách nối các bảng cần dùng; hệ thống không tự chọn, người dùng cần chọn một cách nối."
PREVIOUSLY_USED = " (cách nối này đã được dùng và lưu trước đây)"
STORE_FAILED = "Không lưu được dataset cho lần truy vấn này; kết quả truy vấn vẫn hợp lệ."
DEFAULT_CLARIFICATION = "Bạn có thể nói rõ hơn câu hỏi không?"
CLARIFY_LINE = "Câu hỏi còn mơ hồ nên chưa chạy truy vấn mà hỏi lại người dùng."
INTERNAL_ITEM = "(mục nội bộ)"
RESUME_LINE = "Dùng cách nối người dùng đã chọn ở lượt trước; không viết lại câu hỏi hay lập lại kế hoạch."
ERROR_DETAIL_LENGTH = 2000
Draft = TypeVar("Draft")


@dataclass
class ChatClients:
    index: QdrantDbService
    embedding: OpenRouterEmbedding
    reranker: Reranker | None = None

    def close(self) -> None:
        for client in (self.index, self.embedding, self.reranker):
            closer = getattr(client, "close", None)
            if closer is None:
                continue
            try:
                closer()
            except Exception:
                logger.warning("Không đóng được client %s", type(client).__name__)


def open_clients() -> ChatClients:
    index = QdrantDbService()
    try:
        return ChatClients(index, OpenRouterEmbedding(), JevReranker())
    except Exception:
        index.close()
        raise


def _today() -> date:
    return datetime.now(UTC).date()


def _open_session() -> Session:
    return get_session_factory()()


def ensure_connection_ready(session: Session, connection_id: UUID) -> None:
    connection = session.get(DatabaseConnection, connection_id)
    if connection is None:
        raise Text2SqlConnectionNotFound()
    if not connection.is_active:
        raise Text2SqlInvalidRequest("Connection đang tạm dừng nên chưa thể truy vấn.")


def _safe_message(error_: AppError) -> str:
    return str(error_) or error_.message


def _detail(failure: Exception) -> str:
    return f"{type(failure).__name__}: {failure}"[:ERROR_DETAIL_LENGTH]


class ChatPipeline:
    def __init__(
        self,
        session_factory: Callable[[], Session] = _open_session,
        clients: Callable[[], ChatClients] = open_clients,
        rewriter: QuestionRewriteAgent | None = None,
        planner: QueryPlanAgent | None = None,
        dataset_planner: DatasetPlanAgent | None = None,
        analyst: AnalysisAgent | None = None,
        runner: Runner = run_read_only,
        today: Callable[[], date] = _today,
        max_rows_to_llm: int | None = None,
        max_stored_rows: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clients = clients
        self.rewriter = rewriter or QuestionRewriteAgent()
        self.planner = planner or QueryPlanAgent()
        self.dataset_planner = dataset_planner or DatasetPlanAgent()
        self.analyst = analyst or AnalysisAgent()
        self.runner = runner
        self.today = today
        self.max_rows_to_llm = max_rows_to_llm or config.text2sql_chat_max_rows_to_llm
        self.max_stored_rows = max_stored_rows

    def check(self, connection_id: UUID) -> None:
        with self.session_factory() as session:
            ensure_connection_ready(session, connection_id)

    def prepare_turn(
        self, connection_id: UUID, user_id: str, conversation_id: UUID | None = None,
        previous_turn_id: UUID | None = None, join_signature: str | None = None,
    ) -> TurnRequest:
        with self.session_factory() as session:
            return prepare_turn(session, connection_id, user_id, conversation_id, previous_turn_id, join_signature)

    def run(
        self, connection_id: UUID, question: str, user_id: str | None = None, turn_request: TurnRequest | None = None,
    ) -> Iterator[ChatEvent]:
        session: Session | None = None
        clients: ChatClients | None = None
        recorder: TurnRecorder | None = None
        chat: _ChatRun | None = None
        events: Iterator[ChatEvent] | None = None
        question = question.strip()
        try:
            if turn_request is not None:
                recorder = TurnRecorder(self.session_factory, self.max_stored_rows)
                try:
                    recorder.open(connection_id, question, turn_request)
                except AppError as failure:
                    logger.warning("Không mở được lượt hội thoại: %s", failure.code)
                    yield error(failure.code, _safe_message(failure))
                    return
                except Exception:
                    logger.exception("Không mở được lượt hội thoại")
                    yield error("internal_error", INTERNAL_ERROR)
                    return
                yield turn(**recorder.ids)
            resume = turn_request.resume if turn_request is not None else None
            try:
                session = self.session_factory()
                clients = None if resume is not None else self.clients()
            except Exception:
                logger.exception("Không khởi tạo được session hoặc client cho chat")
                yield _recorded(recorder, error("internal_error", INTERNAL_ERROR), None)
                return
            user = user_id.strip() if user_id and user_id.strip() else None
            history = recorder.history if recorder is not None else []
            chat = _ChatRun(self, session, clients, connection_id, question, user, history, resume)
            events = chat.events()
            for event in events:
                yield _recorded(recorder, event, chat.outcome)
        except GeneratorExit:
            if recorder is not None:
                recorder.finish(chat.outcome if chat else None, disconnected=True)
            raise
        finally:
            closer = getattr(events, "close", None)
            if closer is not None:
                closer()
            if recorder is not None:
                recorder.finish(chat.outcome if chat else None)
                recorder.close()
            if clients is not None:
                clients.close()
            if session is not None:
                session.close()


def _recorded(recorder: TurnRecorder | None, event: ChatEvent, answer: ChatAnswer | None) -> ChatEvent:
    if recorder is None:
        return event
    event = recorder.observe(event)
    if event.event in ("done", "error"):
        recorder.finish(answer)
    return event


class _ChatRun:
    def __init__(
        self, pipeline: ChatPipeline, session: Session, clients: ChatClients | None, connection_id: UUID,
        question: str, user_id: str | None, history: list[dict] | None = None, resume: JoinResume | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.session = session
        self.clients = clients
        self.connection_id = connection_id
        self.question = question
        self.user_id = user_id
        self.history = list(history or [])
        self.resume = resume
        self.reasoning_counts: dict[str, int] = {}
        self.catalog: CatalogContext | None = None
        self.outcome = ChatAnswer(question=question, today=pipeline.today())
        self.ask = AskService(
            session, clients.index, clients.embedding, rewriter=pipeline.rewriter, planner=pipeline.planner,
            today=pipeline.today, reranker=clients.reranker,
        ) if clients is not None else None

    def events(self) -> Iterator[ChatEvent]:
        answer = self.outcome
        try:
            yield from (self.resume_join(answer) if self.resume is not None else self.answer(answer))
        except AppError as failure:
            self.session.rollback()
            logger.warning("Chat dừng với lỗi %s", failure.code)
            answer.finish("error", _safe_message(failure))
            answer.error_code, answer.error_detail = failure.code, _detail(failure)
        except Exception as failure:
            self.session.rollback()
            logger.exception("Chat gặp lỗi không mong đợi")
            answer.finish("error", INTERNAL_ERROR)
            answer.error_code, answer.error_detail = "internal_error", _detail(failure)
        yield from self.analyse(answer)

    def explain(self, name: StepName, lines: Iterable[str]) -> Iterator[ChatEvent]:
        for line in lines:
            if line:
                index = self.reasoning_counts.get(name, 0)
                self.reasoning_counts[name] = index + 1
                yield reasoning(name, "server", index, line)

    def think(
        self, name: StepName, stream: Generator[ReasoningDelta, None, Draft],
    ) -> Generator[ChatEvent, None, Draft]:
        base = self.reasoning_counts.get(name, 0)
        try:
            while True:
                try:
                    delta = next(stream)
                except StopIteration as finished:
                    return finished.value
                index = base + delta.index
                self.reasoning_counts[name] = max(self.reasoning_counts.get(name, 0), index + 1)
                yield reasoning(name, "model", index, delta.text)
        finally:
            stream.close()

    def answer(self, answer: ChatAnswer) -> Iterator[ChatEvent]:
        yield step("rewrite", "started")
        assert self.ask is not None
        request = self.ask.start(self.connection_id, self.question, self.user_id, self.history)
        draft = yield from self.think("rewrite", self.pipeline.rewriter.stream(request.payload()))
        state = self.ask.rewritten(request, draft)
        info = state.rewrite.info
        answer.rewrite = info
        self.catalog = state.context.catalog
        yield step("rewrite", "done", {
            "original_question": info.original_question, "rewritten_question": info.rewritten_question,
            "glossary_terms": [item.name for item in info.glossary_terms],
            "rules": [item.name for item in info.rules],
            "own_knowledge": [item.name for item in info.own_knowledge], "changes": info.changes,
        })
        yield step("metric_search", "started")
        search = self.ask.search_candidates(state)
        candidates = search.candidates
        yield from self.explain("metric_search", metric_search_lines(search))
        yield step("metric_search", "done", {"candidates": [
            {"name": item.metric.name, "label": item.metric.label or item.metric.name, "source": item.source}
            for item in candidates
        ]})
        if not candidates:
            yield step("metric_query", "skipped", {"reason": NO_CANDIDATE_REASON})
            yield from self.dataset(state, answer)
            return
        yield step("metric_query", "started")
        answer.flow = "metric"
        catalog = state.context.catalog
        draft = yield from self.think("metric_query", self.pipeline.planner.stream(
            self.ask.plan_context(state, candidates),
        ))
        try:
            prepared = self.ask.planned(state, candidates, draft)
        except Text2SqlInvalidRequest as failure:
            message = sanitize_message(str(failure), catalog)
            answer.finish("cannot_answer", message)
            yield from self.explain("metric_query", [f"Không dựng được truy vấn metric: {message}"])
            yield step("metric_query", "done", {"outcome": "cannot_answer"})
            return
        if prepared.status == "needs_clarification":
            answer.assumptions = prepared.assumptions
            answer.finish(
                "needs_clarification", prepared.message, prepared.clarification_question,
                prepared.clarification_options,
            )
            yield from self.explain("metric_query", [CLARIFY_LINE])
            yield step("metric_query", "done", {"outcome": "needs_clarification"})
            return
        if prepared.status == "ready":
            yield from self.metric(prepared, answer, catalog)
            return
        answer.flow = "none"
        reason = sanitize_message(prepared.message, catalog) if prepared.message else NO_CANDIDATE_REASON
        yield from self.explain("metric_query", [f"Kế hoạch không chọn được metric phù hợp ({reason}). {TO_DATASET}"])
        yield step("metric_query", "skipped", {"reason": prepared.message or NO_CANDIDATE_REASON})
        yield from self.dataset(state, answer)

    def metric(self, prepared: PreparedAsk, answer: ChatAnswer, catalog: CatalogContext) -> Iterator[ChatEvent]:
        answer.assumptions = prepared.assumptions
        service = QueryService(self.session, self.pipeline.runner)
        source_url = service.resolve_source(self.connection_id)
        yield from self.explain("metric_query", metric_rule_lines(prepared.planned))
        for item in prepared.planned:
            report = metric_report(item, service.execute(item.compiled, source_url, CONFIRMATION), catalog)
            answer.queries.append(report)
            yield ChatEvent("data", report.event_payload())
            yield from self.explain("metric_query", [query_line(report, item.metric.label or item.metric.name)])
        answer.finish("answered", prepared.message)
        yield step("metric_query", "done", {"outcome": "answered", "queries": len(answer.queries)})

    def find_fields(self, rewritten: str) -> FindFieldsOut:
        assert self.clients is not None
        search = TopicSearchService(self.session, self.clients.index, self.clients.embedding)
        return FieldService(self.session, search, self.clients.reranker).find(self.connection_id, rewritten)

    def dataset(self, state: AskState, answer: ChatAnswer) -> Iterator[ChatEvent]:
        answer.flow = "dataset"
        catalog = state.context.catalog
        rewritten = state.rewrite.info.rewritten_question
        yield step("field_search", "started")
        found = self.find_fields(rewritten)
        yield from self.explain("field_search", field_lines(found))
        yield step("field_search", "done", {
            "match": found.match, "note": found.note,
            "tables": [
                {"name": table.name, "display_name": table.display_name,
                 "fields": [item.display_name for item in table.fields]}
                for table in found.tables
            ],
        })
        if found.match == "none" or not found.tables:
            answer.finish("cannot_answer", NO_FIELDS_MESSAGE)
            return
        yield step("dataset_plan", "started")
        draft = yield from self.think("dataset_plan", self.pipeline.dataset_planner.stream(dataset_plan_context(
            state.question, rewritten, state.today, found.tables, state.context,
        )))
        answer.assumptions = draft.assumptions
        if draft.status == "needs_clarification":
            answer.finish(
                "needs_clarification", draft.reason, draft.clarification_question or DEFAULT_CLARIFICATION,
                draft.clarification_options,
            )
            yield from self.explain("dataset_plan", [CLARIFY_LINE])
            yield step("dataset_plan", "done", {"outcome": "needs_clarification"})
            return
        if draft.status == "cannot_answer":
            answer.finish("cannot_answer", draft.reason or "Các trường tìm được chưa đủ để trả lời câu hỏi.")
            yield from self.explain("dataset_plan", ["Kế hoạch kết luận các trường tìm được chưa đủ để trả lời."])
            yield step("dataset_plan", "done", {"outcome": "cannot_answer"})
            return
        try:
            mapped = map_dataset_plan(draft, catalog, found.tables)
        except PlanMappingError as failure:
            answer.finish("cannot_answer", str(failure))
            yield from self.explain("dataset_plan", [f"Không ánh xạ được kế hoạch về bảng và cột thật: {failure}"])
            yield step("dataset_plan", "done", {"outcome": "cannot_answer", "reason": str(failure)})
            return
        yield from self.explain("dataset_plan", mapping_lines(mapped, catalog))
        yield step("dataset_plan", "done", {
            "outcome": "ok", "root_table": catalog.tables[mapped.root_table_id].label,
            "tables": [catalog.tables[item].label for item in mapped.table_ids], "added_tables": mapped.added_tables,
        })
        yield step("join_plan", "started")
        join = JoinService(self.session).plan(self.connection_id, mapped.table_ids, root=mapped.root_table_id)
        option = yield from self.resolve_join(join, answer, state)
        if option is None:
            if join.status == "ambiguous":
                answer.continuation = continuation_state(
                    state.rewrite.info, mapped, draft.assumptions, draft.reason, join.options,
                )
            return
        yield from self.run_dataset(option, mapped.plan, answer, catalog, draft.reason)

    def resume_join(self, answer: ChatAnswer) -> Iterator[ChatEvent]:
        assert self.resume is not None
        resume, state = self.resume, self.resume.state
        answer.flow = "dataset"
        answer.assumptions = [item for item in state.get("assumptions") or [] if isinstance(item, str)]
        answer.rewrite = RewriteInfo.model_validate(state["rewrite"]) if state.get("rewrite") else None
        catalog = load_context(self.session, self.connection_id)
        self.catalog = catalog
        yield step("join_plan", "started")
        described = describe_option(catalog, resume.option)
        answer.join = {"status": "ok", "options": [described["description"]], "message": ""}
        yield from self.explain("join_plan", [RESUME_LINE])
        yield from self.explain("join_plan", join_lines(JoinPlan(status="ok", options=[resume.option]), catalog))
        yield step("join_plan", "done", {
            "status": "ok", "chosen": True, "signature": resume.option.signature, **described,
        })
        yield from self.run_dataset(resume.option, resume.plan, answer, catalog, str(state.get("reason") or ""))

    def resolve_join(
        self, join: JoinPlan, answer: ChatAnswer, state: AskState,
    ) -> Generator[ChatEvent, None, JoinOption | None]:
        catalog = state.context.catalog
        if join.status == "not_declared":
            answer.join = {"status": "not_declared", "options": [], "message": join.message}
            answer.finish("join_not_declared", NOT_DECLARED_MESSAGE.format(detail=join.message))
            yield from self.explain("join_plan", join_lines(join, catalog))
            yield step("join_plan", "done", {"status": "not_declared", "message": join.message})
            return None
        if join.status == "ambiguous":
            used = DatasetStore(self.session).saved_signatures(self.connection_id, join.options)
            options: list[dict[str, Any]] = []
            for number, option in enumerate(join.options, start=1):
                described = describe_option(catalog, option)
                options.append({
                    "number": number, "signature": option.signature, **described,
                    "previously_used": option.signature in used,
                })
            answer.join = {
                "status": "ambiguous", "message": AMBIGUOUS_MESSAGE,
                "options": [
                    item["description"] + (PREVIOUSLY_USED if item["previously_used"] else "") for item in options
                ],
            }
            answer.finish("join_ambiguous", AMBIGUOUS_MESSAGE)
            yield from self.explain("join_plan", join_lines(join, catalog, used))
            yield step("join_plan", "done", {"status": "ambiguous", "options": options})
            return None
        option = join.options[0]
        described = describe_option(catalog, option)
        answer.join = {"status": "ok", "options": [described["description"]], "message": ""}
        yield from self.explain("join_plan", join_lines(join, catalog))
        yield step("join_plan", "done", {"status": "ok", **described})
        return option

    def run_dataset(
        self, option: JoinOption, plan: DatasetQueryPlan, answer: ChatAnswer, catalog: CatalogContext, reason: str,
    ) -> Iterator[ChatEvent]:
        yield step("dataset_query", "started")
        service = DatasetQueryService(self.session, self.pipeline.runner)
        try:
            compiled = service.prepare(self.connection_id, option, plan)
        except Text2SqlInvalidRequest as failure:
            message = sanitize_message(str(failure), catalog)
            answer.finish("cannot_answer", message)
            yield from self.explain("dataset_query", [f"Không dựng được truy vấn an toàn: {message}"])
            yield step("dataset_query", "done", {"outcome": "cannot_answer", "reason": message})
            return
        result = service.execute(compiled, service.resolve_source(self.connection_id), CONFIRMATION)
        stored = self.store(option, plan)
        time = plan.time
        report = dataset_report(
            result, [stored.warning] if stored.warning else [], catalog, time.granularity if time else None,
        )
        answer.queries.append(report)
        answer.dataset_id = stored.dataset_id
        yield ChatEvent("data", report.event_payload())
        yield from self.explain("dataset_query", [
            query_line(report), store_line(stored.dataset_id is not None, stored.created, stored.added, stored.warning),
        ])
        answer.finish("answered", reason)
        yield step("dataset_query", "done", {
            "outcome": "answered", "dataset_id": str(stored.dataset_id) if stored.dataset_id else None,
            "created": stored.created, "added_columns": stored.added,
        })

    def store(self, option: JoinOption, plan: DatasetQueryPlan) -> "_Stored":
        try:
            store = DatasetStore(self.session)
            dataset, created = store.get_or_create(self.connection_id, option)
            addition = store.add_columns(dataset, dataset_column_ids(self.session, option, plan))
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Không lưu được dataset sau khi truy vấn thành công")
            return _Stored(warning=STORE_FAILED)
        return _Stored(dataset.id, created, len(addition.added), addition.warning)

    def analyse(self, answer: ChatAnswer) -> Iterator[ChatEvent]:
        yield step("analysis", "started")
        stream = None
        try:
            stream = self.pipeline.analyst.stream(build_analysis_context(answer, self.pipeline.max_rows_to_llm))
            for chunk in stream:
                if chunk:
                    yield token(chunk)
        except AppError as failure:
            logger.warning("Phân tích lỗi %s", failure.code)
            answer.error_code, answer.error_detail = failure.code, _detail(failure)
            yield error(failure.code, _safe_message(failure))
            return
        except Exception as failure:
            logger.exception("Phân tích gặp lỗi không mong đợi")
            answer.error_code, answer.error_detail = "internal_error", _detail(failure)
            yield error("internal_error", INTERNAL_ERROR)
            return
        finally:
            closer = getattr(stream, "close", None)
            if closer is not None:
                closer()
        yield step("analysis", "done")
        yield done(
            answer.status, answer.flow, str(answer.dataset_id) if answer.dataset_id else None,
            assumptions=[self.client_text(item) for item in answer.assumptions if item],
            message=self.client_text(answer.message),
            clarification_question=self.client_text(answer.clarification_question) or None,
            clarification_options=[
                text for text in (self.client_text(item) for item in answer.clarification_options) if text
            ] or None,
        )

    def client_text(self, text: str | None) -> str:
        if not text:
            return ""
        if self.catalog is not None:
            return sanitize_message(text, self.catalog)
        return UUID_PATTERN.sub(INTERNAL_ITEM, text)


@dataclass
class _Stored:
    dataset_id: UUID | None = None
    created: bool = False
    added: int = 0
    warning: str | None = None
