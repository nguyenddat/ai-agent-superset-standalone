from uuid import UUID

from mcp.server import MCPServer
from pydantic import BaseModel

from backend.modules.text2sql.details.schemas import ColumnDescription
from backend.modules.text2sql.details.service import DetailService

from .common import (
    ConnectionId,
    QuestionText,
    RerankFlag,
    TopK10,
    clean_question,
    match_signal,
    rerank_warning,
    run_blocking,
    search_session,
)


class ColumnHit(BaseModel):
    score: float
    rerank_score: float | None
    description: ColumnDescription


class SearchColumnsOut(BaseModel):
    hits: list[ColumnHit]
    reranked: bool
    rerank_warning: str | None
    match: str
    note: str | None


def run_search_columns(connection_id: UUID, question: str, k: int, rerank: bool) -> SearchColumnsOut:
    with search_session(rerank) as (session, service, reranker):
        outcome = service.search(connection_id, "column", question, k, reranker)
        refs = [(hit.table_id, hit.entity_id) for hit in outcome.hits if hit.table_id is not None]
        descriptions = {
            item.column.column_id: item for item in DetailService(session).columns(connection_id, refs)
        }
    match, note = match_signal([hit.rerank_score for hit in outcome.hits], outcome.reranked)
    return SearchColumnsOut(
        hits=[
            ColumnHit(score=hit.score, rerank_score=hit.rerank_score, description=descriptions[hit.entity_id])
            for hit in outcome.hits if hit.entity_id in descriptions
        ],
        reranked=outcome.reranked, rerank_warning=rerank_warning(outcome.rerank_error), match=match, note=note,
    )


async def search_columns(
    connection_id: ConnectionId, question: QuestionText, k: TopK10 = 5, rerank: RerankFlag = False,
) -> SearchColumnsOut:
    return await run_blocking(run_search_columns, connection_id, clean_question(question), k, rerank)


def register_column_tools(server: MCPServer) -> None:
    server.tool(
        name="search_columns",
        description=(
            "Tìm các cột phù hợp nhất với câu hỏi (hybrid dense + BM25). Mỗi kết quả kèm toàn bộ mô tả có "
            "cấu trúc của cột (kiểu dữ liệu, khóa, vai trò ngữ nghĩa, thuật ngữ, đơn vị, định dạng, phép tổng hợp, "
            "từ đồng nghĩa, cột tham chiếu) và bảng chứa nó, nên không cần gọi thêm tool xem chi tiết."
        ),
    )(search_columns)
