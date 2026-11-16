from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.agent_package.agents.query_plan_agent import PlanDraft, QueryPlanAgent
from backend.agent_package.agents.question_rewrite_agent import QuestionRewriteAgent, RewriteDraft
from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.core.setting import config

from ..common.errors import Text2SqlInvalidRequest
from ..query.service import QueryService
from ..vector_store.qdrant_db_service import QdrantDbService
from ..vector_store.rerank.base import Reranker
from ..vector_store.retrieve.service import RetrievalService
from ..vector_store.retrieve.topic_search import TopicSearchService
from .context import AskContext, ContextGatherer
from .planner import MetricCandidate, PlannedQuery, build_plan_context, linked_metrics, materialize
from .rewrite import RewriteOutcome, build_rewrite_context, rewrite_outcome
from .schemas import AskResult, CandidateTable, QueryOutcome, RewriteInfo, Text2SqlFallback

MAX_QUESTION_LENGTH = 2000
SEARCH_CANDIDATES = 5
MAX_CANDIDATES = 6
FALLBACK_TABLES = 3
NO_CANDIDATE_REASON = "Không tìm thấy metric liên quan."
FALLBACK_MESSAGE = (
    "Chưa có metric phù hợp để trả lời. Hãy dùng find_fields để tìm cột cần thiết, plan_join để xem cách nối bảng, "
    "rồi query_dataset để chạy truy vấn nhiều bảng; nếu báo not_declared thì cần bổ sung khai báo quan hệ trong data "
    "dictionary. Các bảng liên quan nhất được liệt kê để tham khảo."
)


@dataclass
class PreparedAsk:
    connection_id: UUID
    status: str
    rewrite: RewriteInfo
    planned: list[PlannedQuery] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    plan_analysis: list[str] = field(default_factory=list)
    message: str = ""
    clarification_question: str | None = None
    clarification_options: list[str] = field(default_factory=list)
    fallback: Text2SqlFallback | None = None

    @property
    def pii_columns(self) -> list[str]:
        return list(dict.fromkeys(name for item in self.planned for name in item.compiled.pii_columns))


@dataclass
class AskState:
    connection_id: UUID
    question: str
    today: date
    context: AskContext
    rewrite: RewriteOutcome


@dataclass
class RewriteRequest:
    connection_id: UUID
    question: str
    today: date
    context: AskContext
    history: list[dict] = field(default_factory=list)

    def payload(self) -> dict:
        return build_rewrite_context(self.question, self.today, self.context, self.history)


@dataclass(frozen=True)
class ScoredMetric:
    candidate: MetricCandidate
    score: float | None


@dataclass
class CandidateSearch:
    linked: list[MetricCandidate] = field(default_factory=list)
    kept: list[ScoredMetric] = field(default_factory=list)
    dropped: list[ScoredMetric] = field(default_factory=list)
    reranked: bool = False
    threshold: float = 0.0

    @property
    def candidates(self) -> list[MetricCandidate]:
        seen = {item.metric.id for item in self.linked}
        extra = [item.candidate for item in self.kept if item.candidate.metric.id not in seen]
        return (self.linked + extra)[:MAX_CANDIDATES]


def _today() -> date:
    return datetime.now(UTC).date()


class AskService:
    def __init__(
        self, session: Session, index: QdrantDbService, embedding: OpenRouterEmbedding,
        rewriter: QuestionRewriteAgent | None = None, planner: QueryPlanAgent | None = None,
        today: Callable[[], date] = _today, reranker: Reranker | None = None,
    ) -> None:
        self.session = session
        self.index = index
        self.embedding = embedding
        self.rewriter = rewriter or QuestionRewriteAgent()
        self.planner = planner or QueryPlanAgent()
        self.today = today
        self.reranker = reranker

    def prepare(self, connection_id: UUID, question: str, user_id: str | None = None) -> PreparedAsk:
        state = self.rewrite(connection_id, question, user_id)
        candidates = self.candidates(state)
        if not candidates:
            return self.fallback(state, NO_CANDIDATE_REASON)
        prepared = self.plan(state, candidates)
        if prepared.status == "no_metric":
            return self.fallback(state, prepared.message, prepared.plan_analysis)
        return prepared

    def rewrite(self, connection_id: UUID, question: str, user_id: str | None = None) -> AskState:
        request = self.start(connection_id, question, user_id)
        return self.rewritten(request, self.rewriter.run(request.payload()))

    def start(
        self, connection_id: UUID, question: str, user_id: str | None = None, history: list[dict] | None = None,
    ) -> RewriteRequest:
        question = question.strip()
        if not question or len(question) > MAX_QUESTION_LENGTH:
            raise Text2SqlInvalidRequest(f"Câu hỏi phải từ 1 đến {MAX_QUESTION_LENGTH} ký tự.")
        search = question
        if history:
            last = history[-1]
            previous = last.get("rewritten_question") or last.get("question") or ""
            search = f"{previous}\n{question}".strip()
        context = ContextGatherer(self.session, self.index, self.embedding).gather(connection_id, search, user_id)
        return RewriteRequest(connection_id, question, self.today(), context, list(history or []))

    def rewritten(self, request: RewriteRequest, draft: RewriteDraft) -> AskState:
        rewrite = rewrite_outcome(draft, request.question, request.context)
        return AskState(request.connection_id, request.question, request.today, request.context, rewrite)

    def candidates(self, state: AskState) -> list[MetricCandidate]:
        return self.search_candidates(state).candidates

    def search_candidates(self, state: AskState) -> CandidateSearch:
        found = self._searched_metrics(state.connection_id, state.rewrite, state.context)
        found.linked = linked_metrics(state.context, state.rewrite)
        return found

    def plan(self, state: AskState, candidates: list[MetricCandidate]) -> PreparedAsk:
        return self.planned(state, candidates, self.planner.run(self.plan_context(state, candidates)))

    def plan_context(self, state: AskState, candidates: list[MetricCandidate]) -> dict:
        return build_plan_context(
            state.question, state.rewrite.info.rewritten_question, state.today, candidates, state.context,
        )

    def planned(self, state: AskState, candidates: list[MetricCandidate], draft: PlanDraft) -> PreparedAsk:
        rewrite = state.rewrite
        if draft.status == "needs_clarification":
            return PreparedAsk(
                connection_id=state.connection_id, status="needs_clarification", rewrite=rewrite.info,
                assumptions=draft.assumptions, plan_analysis=draft.analysis, message=draft.reason,
                clarification_question=draft.clarification_question or "Bạn có thể nói rõ hơn câu hỏi không?",
                clarification_options=list(draft.clarification_options),
            )
        if draft.status == "no_metric" or not draft.queries:
            return PreparedAsk(
                connection_id=state.connection_id, status="no_metric", rewrite=rewrite.info, message=draft.reason,
                plan_analysis=draft.analysis,
            )
        planned = materialize(
            draft, candidates, state.context, state.connection_id, config.text2sql_query_max_rows,
        )
        return PreparedAsk(
            connection_id=state.connection_id, status="ready", rewrite=rewrite.info, planned=planned,
            assumptions=draft.assumptions, plan_analysis=draft.analysis, message=draft.reason,
        )

    def fallback(self, state: AskState, reason: str, analysis: list[str] | None = None) -> PreparedAsk:
        return self._no_metric(state.connection_id, state.rewrite, reason, analysis)

    def _searched_metrics(
        self, connection_id: UUID, rewrite: RewriteOutcome, context: AskContext,
    ) -> CandidateSearch:
        outcome = RetrievalService(self.session, self.index, self.embedding).search(
            connection_id, rewrite.info.rewritten_question, SEARCH_CANDIDATES, self.reranker,
        )
        threshold = config.text2sql_ask_metric_min_score
        found = CandidateSearch(reranked=outcome.reranked, threshold=threshold)
        for item in outcome.candidates:
            metric = context.catalog.metrics_by_id.get(item.metric_id)
            if metric is None:
                continue
            scored = ScoredMetric(MetricCandidate(metric, "search"), item.rerank_score if outcome.reranked else None)
            if outcome.reranked and (item.rerank_score or 0.0) < threshold:
                found.dropped.append(scored)
            else:
                found.kept.append(scored)
        return found

    def _no_metric(
        self, connection_id: UUID, rewrite: RewriteOutcome, reason: str, analysis: list[str] | None = None,
    ) -> PreparedAsk:
        tables = TopicSearchService(self.session, self.index, self.embedding).search(
            connection_id, "table", rewrite.info.rewritten_question, FALLBACK_TABLES,
        ).hits
        return PreparedAsk(
            connection_id=connection_id, status="no_metric", rewrite=rewrite.info,
            message=reason or FALLBACK_MESSAGE, plan_analysis=analysis or [],
            fallback=Text2SqlFallback(
                message=FALLBACK_MESSAGE,
                candidate_tables=[
                    CandidateTable(
                        table_id=hit.entity_id, name=hit.payload.get("name", hit.name), display_name=hit.display_name,
                        description=hit.text[:300] or None,
                    )
                    for hit in tables
                ],
            ),
        )




def _message(prepared: PreparedAsk) -> str:
    lines: list[str] = []
    for item in prepared.planned:
        label = item.metric.label or item.metric.name
        applied = [rule for rule in item.rules if rule.filters]
        if applied:
            lines.append(f"{label}: đã áp dụng quy tắc " + "; ".join(
                f"'{rule.name}' ({', '.join(rule.filters)})" for rule in applied
            ))
        for rule in item.rules:
            if rule.overridden:
                lines.append(
                    f"{label}: quy tắc '{rule.name}' không áp dụng điều kiện {', '.join(rule.overridden)} "
                    "vì câu hỏi đã lọc riêng trên cùng cột"
                )
    lines += [f"Giả định: {item}" for item in prepared.assumptions]
    return "\n".join(lines) or prepared.message


def execute_ask(
    prepared: PreparedAsk, query_service: QueryService, source_url: URL | None, confirmation: str,
) -> AskResult:
    if prepared.status != "ready" or source_url is None:
        return AskResult(
            status=prepared.status, message=prepared.message, rewrite=prepared.rewrite,  # type: ignore[arg-type]
            assumptions=prepared.assumptions, plan_analysis=prepared.plan_analysis,
            clarification_question=prepared.clarification_question,
            text2sql=prepared.fallback,
        )
    outcomes = [
        QueryOutcome(
            metric=item.metric, plan=item.plan, rules=item.rules,
            result=query_service.execute(item.compiled, source_url, confirmation),
        )
        for item in prepared.planned
    ]
    return AskResult(
        status="answered", message=_message(prepared), rewrite=prepared.rewrite, queries=outcomes,
        assumptions=prepared.assumptions, plan_analysis=prepared.plan_analysis,
    )
