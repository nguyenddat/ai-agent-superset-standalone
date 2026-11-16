import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated, Any
from uuid import UUID

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.common.base_exceptions import AppError
from backend.core.database import get_session_factory
from backend.modules.text2sql.vector_store.qdrant_db_service import QdrantDbService
from backend.modules.text2sql.vector_store.rerank.base import Reranker
from backend.modules.text2sql.vector_store.rerank.jev_reranker import JevReranker
from backend.modules.text2sql.vector_store.retrieve.topic_search import TopicSearchService

ConnectionId = Annotated[UUID, Field(description="ID của connection (database nguồn đã đăng ký).")]
QuestionText = Annotated[str, Field(min_length=1, max_length=2000, description="Câu hỏi của người dùng.")]
UserId = Annotated[
    str, Field(min_length=1, max_length=255, description="ID của người dùng đang hỏi; chỉ thấy tri thức riêng của họ.")
]
RerankFlag = Annotated[
    bool,
    Field(description=(
        "Xếp hạng lại các ứng viên bằng Jev (qua OpenRouter) để chính xác hơn, đổi lại chậm hơn và tốn thêm "
        "chi phí. Nếu Jev lỗi thì kết quả vẫn trả về theo thứ tự gốc kèm rerank_warning."
    )),
]


def top_k(maximum: int) -> Any:
    return Annotated[int, Field(ge=1, le=maximum, description="Số kết quả trả về.")]


class SearchHit(BaseModel):
    id: str
    name: str
    summary: str
    table_id: str | None
    score: float
    rerank_score: float | None


class SearchOut(BaseModel):
    hits: list[SearchHit]
    reranked: bool
    rerank_warning: str | None
    match: str = Field(description="none, weak, ok hoặc unverified; xem note.")
    note: str | None = None


WEAK_RERANK_SCORE = 0.2


def match_signal(rerank_scores: list[float | None], reranked: bool) -> tuple[str, str | None]:
    if not rerank_scores:
        return "none", "Không tìm thấy kết quả nào; đừng suy đoán, hãy hỏi lại người dùng hoặc đổi cách diễn đạt."
    top = rerank_scores[0]
    if reranked and top is not None:
        if top < WEAK_RERANK_SCORE:
            return "weak", "Kết quả đầu có điểm liên quan thấp; có thể không có mục nào thật sự khớp, hãy kiểm tra kỹ."
        return "ok", None
    return "unverified", "Chưa xếp hạng lại nên chưa đánh giá được mức khớp; kết quả luôn là top-k gần nhất."


def rerank_warning(error_code: str | None) -> str | None:
    if not error_code:
        return None
    return f"Không xếp hạng lại được ({error_code}); kết quả theo thứ tự truy hồi gốc."


def clean_question(question: str) -> str:
    question = question.strip()
    if not question:
        raise ToolError("Câu hỏi không được để trống.")
    return question


async def run_blocking(function: Callable[..., Any], *args: Any) -> Any:
    try:
        return await asyncio.to_thread(function, *args)
    except AppError as error:
        raise ToolError(str(error)) from error


@contextmanager
def search_clients(rerank: bool) -> Iterator[tuple[QdrantDbService, OpenRouterEmbedding, Reranker | None]]:
    index = QdrantDbService()
    embedding = OpenRouterEmbedding()
    reranker = JevReranker() if rerank else None
    try:
        yield index, embedding, reranker
    finally:
        index.close()
        embedding.close()
        if reranker is not None:
            reranker.close()


@contextmanager
def search_session(rerank: bool) -> Iterator[tuple[Session, TopicSearchService, Reranker | None]]:
    with search_clients(rerank) as (index, embedding, reranker), get_session_factory()() as session:
        yield session, TopicSearchService(session, index, embedding), reranker


def search_topic(
    topic: str, connection_id: UUID, question: str, k: int, rerank: bool, user_id: str | None = None
) -> SearchOut:
    with search_session(rerank) as (_, service, reranker):
        outcome = service.search(connection_id, topic, question, k, reranker, user_id)
    match, note = match_signal([hit.rerank_score for hit in outcome.hits], outcome.reranked)
    return SearchOut(
        match=match, note=note,
        hits=[
            SearchHit(
                id=str(hit.entity_id), name=hit.display_name, summary=hit.text,
                table_id=str(hit.table_id) if hit.table_id else None, score=hit.score,
                rerank_score=hit.rerank_score,
            )
            for hit in outcome.hits
        ],
        reranked=outcome.reranked, rerank_warning=rerank_warning(outcome.rerank_error),
    )


@contextmanager
def detail_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session


TopK5 = top_k(5)
TopK10 = top_k(10)
