import logging
from typing import Annotated, Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, ElicitationResult, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from backend.modules.text2sql.query.compiler import CompiledQuery
from backend.modules.text2sql.query.schemas import QueryFilter, QueryOrder, QueryPlan, QueryResult, QueryTime
from backend.modules.text2sql.query.service import QueryService

from .common import ConnectionId, detail_session, run_blocking

logger = logging.getLogger("mcp.query")

NOT_SUPPORTED = "not_supported"
Confirmation = Literal["not_required", "confirmed", "not_supported"]


class PiiConsent(BaseModel):
    proceed: bool = Field(description="Đồng ý chạy truy vấn; giá trị cá nhân sẽ được thay bằng placeholder.")


def run_prepare(connection_id: UUID, plan: QueryPlan) -> CompiledQuery:
    with detail_session() as session:
        return QueryService(session).prepare(connection_id, plan)


def run_execute(compiled: CompiledQuery, confirmation: str) -> QueryResult:
    with detail_session() as session:
        service = QueryService(session)
        source_url = service.resolve_source(compiled.connection_id)
    return service.execute(compiled, source_url, confirmation)


def client_can_elicit(ctx: Context) -> bool:
    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    return elicitation is not None and (elicitation.form is not None or elicitation.url is None)


def pii_message(columns: list[str]) -> str:
    return (
        f"Truy vấn sẽ đọc cột có dữ liệu cá nhân: {', '.join(columns)}. Giá trị gốc sẽ KHÔNG gửi cho AI: chúng được "
        "thay bằng placeholder (ví dụ <PII_1>) trước khi trả về. Tiếp tục chạy truy vấn?"
    )


async def pii_consent(
    ctx: Context, connection_id: UUID, metric_id: UUID, group_by: list[UUID], time: QueryTime | None,
    filters: list[QueryFilter], order_by: list[QueryOrder], limit: int,
) -> Elicit[PiiConsent] | str | None:
    plan = QueryPlan(
        metric_id=metric_id, group_by=group_by, time=time, filters=filters, order_by=order_by, limit=limit,
    )
    compiled = await run_blocking(run_prepare, connection_id, plan)
    if not compiled.pii_columns:
        return None
    if not client_can_elicit(ctx):
        logger.info("Client không hỗ trợ xác nhận; tiếp tục với dữ liệu đã che.")
        return NOT_SUPPORTED
    return Elicit(message=pii_message(compiled.pii_columns), schema=PiiConsent)


def confirmation_of(consent: ElicitationResult[PiiConsent]) -> Confirmation:
    data = getattr(consent, "data", None)
    if getattr(consent, "action", None) != "accept":
        raise ToolError("Người dùng không đồng ý đọc dữ liệu cá nhân nên truy vấn đã bị hủy.")
    if data is None:
        return "not_required"
    if data == NOT_SUPPORTED:
        return "not_supported"
    if isinstance(data, PiiConsent) and data.proceed:
        return "confirmed"
    raise ToolError("Người dùng không đồng ý đọc dữ liệu cá nhân nên truy vấn đã bị hủy.")


async def query_metric(
    connection_id: ConnectionId,
    metric_id: Annotated[UUID, Field(description="ID metric (từ search_metrics).")],
    consent: Annotated[ElicitationResult[PiiConsent], Resolve(pii_consent)],
    group_by: Annotated[
        list[UUID], Field(max_length=5, description="ID các cột để nhóm kết quả (từ search_tables/search_columns).")
    ] = [],  # noqa: B006
    time: Annotated[
        QueryTime | None,
        Field(description="Cột thời gian: khoảng [start, end) và/hoặc nhóm theo ngày, tuần, tháng, quý, năm."),
    ] = None,
    filters: Annotated[list[QueryFilter], Field(max_length=10, description="Điều kiện lọc, nối bằng AND.")] = [],  # noqa: B006
    order_by: Annotated[
        list[QueryOrder], Field(max_length=3, description='Sắp xếp theo "metric", "time" hoặc cột trong group_by.')
    ] = [],  # noqa: B006
    limit: Annotated[int, Field(ge=1, le=5000, description="Số dòng tối đa (bị giới hạn bởi cấu hình server).")] = 100,
) -> QueryResult:
    confirmation = confirmation_of(consent)
    plan = QueryPlan(
        metric_id=metric_id, group_by=group_by, time=time, filters=filters, order_by=order_by, limit=limit,
    )
    compiled = await run_blocking(run_prepare, connection_id, plan)
    return await run_blocking(run_execute, compiled, confirmation)


def register_query_tools(server: MCPServer) -> None:
    server.tool(
        name="query_metric",
        description=(
            "Chạy một metric đã chọn trên database nguồn và trả số liệu. Bạn KHÔNG viết SQL: gửi plan gồm metric_id, "
            "group_by, time, filters, order_by, limit; server tự dựng đúng một câu SELECT tổng hợp trên bảng của "
            "metric (không join), bind tham số, chạy trong transaction chỉ đọc có timeout và giới hạn số dòng. "
            "Quy trình: search_metrics, get_metric, rồi search_columns/search_tables để lấy ID cột. Không tự thêm "
            "khoảng thời gian nếu câu hỏi không nói. Giá trị NULL nghĩa là không có dữ liệu, không phải 0. "
            "Dữ liệu cá nhân (cột PII, số điện thoại, email, CCCD...) được thay bằng placeholder; không lọc được "
            "theo cột PII, và nhóm theo cột PII sẽ hỏi xác nhận người dùng. Kết quả kèm sql đã chạy để kiểm tra."
        ),
    )(query_metric)
