from uuid import UUID

from mcp.server import MCPServer
from pydantic import BaseModel

from backend.core.database import get_session_factory
from backend.modules.text2sql.details.schemas import MetricDetail
from backend.modules.text2sql.details.service import DetailService
from backend.modules.text2sql.vector_store.retrieve.service import RetrievalService

from .common import (
    ConnectionId,
    QuestionText,
    RerankFlag,
    TopK10,
    clean_question,
    detail_session,
    rerank_warning,
    run_blocking,
    search_clients,
)


class MetricCandidateOut(BaseModel):
    metric_id: str
    table_id: str
    name: str
    label: str | None
    description: str | None
    score: float
    rerank_score: float | None
    matched_topics: list[str]


class SearchMetricsOut(BaseModel):
    candidates: list[MetricCandidateOut]
    reranked: bool
    rerank_warning: str | None


def run_search(connection_id: UUID, question: str, k: int, rerank: bool) -> SearchMetricsOut:
    with search_clients(rerank) as (index, embedding, reranker), get_session_factory()() as session:
        outcome = RetrievalService(session, index, embedding).search(connection_id, question, k, reranker)
    return SearchMetricsOut(
        candidates=[
            MetricCandidateOut(
                metric_id=str(candidate.metric_id), table_id=str(candidate.table_id), name=candidate.name,
                label=candidate.label, description=candidate.description, score=candidate.score,
                rerank_score=candidate.rerank_score, matched_topics=candidate.matched_topics,
            )
            for candidate in outcome.candidates
        ],
        reranked=outcome.reranked, rerank_warning=rerank_warning(outcome.rerank_error),
    )


def run_get_metric(connection_id: UUID, metric_id: UUID) -> MetricDetail:
    with detail_session() as session:
        return DetailService(session).metric(connection_id, metric_id)


async def search_metrics(
    connection_id: ConnectionId, question: QuestionText, k: TopK10 = 5, rerank: RerankFlag = False,
) -> SearchMetricsOut:
    return await run_blocking(run_search, connection_id, clean_question(question), k, rerank)


async def get_metric(connection_id: ConnectionId, metric_id: UUID) -> MetricDetail:
    return await run_blocking(run_get_metric, connection_id, metric_id)


def register_metric_tools(server: MCPServer) -> None:
    server.tool(
        name="search_metrics",
        description=(
            "Tìm tối đa k metric phù hợp nhất với câu hỏi trong một connection bằng truy hồi hybrid "
            "(dense + BM25, kết hợp tín hiệu từ bảng và cột). Không sinh SQL và không chạy truy vấn. "
            "Chọn được metric thì gọi get_metric để xem đầy đủ."
        ),
    )(search_metrics)
    server.tool(
        name="get_metric",
        description=(
            "Xem chi tiết một metric đã chọn: biểu thức, định dạng, loại, cảnh báo khi dùng, bảng và các cột "
            "mà biểu thức tham chiếu."
        ),
    )(get_metric)
