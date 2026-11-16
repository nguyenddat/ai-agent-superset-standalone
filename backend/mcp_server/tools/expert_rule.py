from uuid import UUID

from mcp.server import MCPServer

from backend.modules.text2sql.details.schemas import ExpertRuleDetail
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


def run_get_expert_rule(connection_id: UUID, rule_id: UUID) -> ExpertRuleDetail:
    with detail_session() as session:
        return DetailService(session).expert_rule(connection_id, rule_id)


async def search_expert_rules(
    connection_id: ConnectionId, question: QuestionText, k: TopK10 = 5, rerank: RerankFlag = False,
) -> SearchOut:
    return await run_blocking(search_topic, "expert_rule", connection_id, clean_question(question), k, rerank)


async def get_expert_rule(connection_id: ConnectionId, rule_id: UUID) -> ExpertRuleDetail:
    return await run_blocking(run_get_expert_rule, connection_id, rule_id)


def register_expert_rule_tools(server: MCPServer) -> None:
    server.tool(
        name="search_expert_rules",
        description=(
            "Tìm quy tắc chuyên gia (đang áp dụng) có thể áp dụng cho câu hỏi. "
            "Chọn được quy tắc thì gọi get_expert_rule để xem đầy đủ điều kiện và ngoại lệ."
        ),
    )(search_expert_rules)
    server.tool(
        name="get_expert_rule",
        description=(
            "Xem chi tiết một quy tắc chuyên gia: bảng áp dụng, điều kiện có cấu trúc (kèm câu đọc được), "
            "ngoại lệ, câu hỏi ví dụ, thuật ngữ và metric liên quan."
        ),
    )(get_expert_rule)
