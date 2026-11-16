from uuid import UUID

from mcp.server import MCPServer

from backend.modules.text2sql.details.schemas import GlossaryTermDetail
from backend.modules.text2sql.details.service import DetailService

from .common import (
    ConnectionId,
    QuestionText,
    RerankFlag,
    SearchOut,
    TopK10,
    clean_question,
    detail_session,
    run_blocking,
    search_topic,
)


def run_get_glossary_term(connection_id: UUID, term_id: UUID) -> GlossaryTermDetail:
    with detail_session() as session:
        return DetailService(session).glossary_term(connection_id, term_id)


async def search_glossary_terms(
    connection_id: ConnectionId, question: QuestionText, k: TopK10 = 5, rerank: RerankFlag = False,
) -> SearchOut:
    return await run_blocking(search_topic, "glossary", connection_id, clean_question(question), k, rerank)


async def get_glossary_term(connection_id: ConnectionId, term_id: UUID) -> GlossaryTermDetail:
    return await run_blocking(run_get_glossary_term, connection_id, term_id)


def register_glossary_tools(server: MCPServer) -> None:
    server.tool(
        name="search_glossary_terms",
        description=(
            "Tìm thuật ngữ nghiệp vụ (đã duyệt) liên quan đến câu hỏi, kể cả khi câu hỏi dùng từ đồng nghĩa. "
            "Chọn được thuật ngữ thì gọi get_glossary_term để xem đầy đủ."
        ),
    )(search_glossary_terms)
    server.tool(
        name="get_glossary_term",
        description="Xem chi tiết một thuật ngữ: định nghĩa, từ đồng nghĩa và các bảng, cột, metric được liên kết.",
    )(get_glossary_term)
