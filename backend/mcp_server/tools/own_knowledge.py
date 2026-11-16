from uuid import UUID

from mcp.server import MCPServer

from backend.modules.text2sql.details.schemas import OwnKnowledgeDetail
from backend.modules.text2sql.details.service import DetailService

from .common import (
    ConnectionId,
    QuestionText,
    RerankFlag,
    SearchOut,
    TopK10,
    UserId,
    clean_question,
    detail_session,
    run_blocking,
    search_topic,
)


def run_get_own_knowledge(connection_id: UUID, user_id: str, entry_id: UUID) -> OwnKnowledgeDetail:
    with detail_session() as session:
        return DetailService(session).own_entry(connection_id, user_id, entry_id)


async def search_own_knowledge(
    connection_id: ConnectionId, user_id: UserId, question: QuestionText, k: TopK10 = 5,
    rerank: RerankFlag = False,
) -> SearchOut:
    return await run_blocking(
        search_topic, "own_knowledge", connection_id, clean_question(question), k, rerank, user_id
    )


async def get_own_knowledge(connection_id: ConnectionId, user_id: UserId, entry_id: UUID) -> OwnKnowledgeDetail:
    return await run_blocking(run_get_own_knowledge, connection_id, user_id, entry_id)


def register_own_knowledge_tools(server: MCPServer) -> None:
    server.tool(
        name="search_own_knowledge",
        description=(
            "Tìm cách hiểu riêng mà chính người dùng này đã xác nhận trước đây (chỉ của user_id được truyền). "
            "Ưu tiên thuật ngữ, metric, quy tắc của hệ thống; chỉ dùng tri thức riêng khi hệ thống chưa có. "
            "Chọn được mục thì gọi get_own_knowledge để xem đầy đủ."
        ),
    )(search_own_knowledge)
    server.tool(
        name="get_own_knowledge",
        description=(
            "Xem chi tiết một cách hiểu riêng của người dùng: định nghĩa, loại, bảng ngữ cảnh, trạng thái duyệt."
        ),
    )(get_own_knowledge)
