from typing import Annotated
from uuid import UUID

from mcp.server import MCPServer
from pydantic import Field

from backend.modules.text2sql.dataset.field_service import FieldService, FindFieldsOut
from backend.modules.text2sql.dataset.join_schemas import JoinPlan
from backend.modules.text2sql.dataset.join_service import JoinService
from backend.modules.text2sql.vector_store.retrieve.topic_search import TopicSearchService

from .common import ConnectionId, QuestionText, clean_question, detail_session, run_blocking, search_clients

TableIds = Annotated[list[UUID], Field(min_length=1, max_length=8, description="ID các bảng cần nối.")]
RootId = Annotated[
    UUID | None,
    Field(description=(
        "ID bảng gốc: bảng định nghĩa tập đối tượng đang hỏi (grain kết quả). Các bảng còn lại được LEFT JOIN "
        "từ gốc ra ngoài. Bỏ trống thì chọn bảng ít làm nhân dòng nhất."
    )),
]
ViaIds = Annotated[
    list[UUID] | None,
    Field(max_length=8, description="edge_ids của phương án đã chọn khi kết quả trước là ambiguous."),
]


def run_find_fields(connection_id: UUID, question: str) -> FindFieldsOut:
    with search_clients(True) as (index, embedding, reranker), detail_session() as session:
        search = TopicSearchService(session, index, embedding)
        return FieldService(session, search, reranker).find(connection_id, question)


def run_plan_join(
    connection_id: UUID, table_ids: list[UUID], via: list[UUID] | None, root: UUID | None = None,
) -> JoinPlan:
    with detail_session() as session:
        return JoinService(session).plan(connection_id, table_ids, via, root)


async def find_fields(connection_id: ConnectionId, question: QuestionText) -> FindFieldsOut:
    return await run_blocking(run_find_fields, connection_id, clean_question(question))


async def plan_join(
    connection_id: ConnectionId, table_ids: TableIds, edge_ids: ViaIds = None, root_table_id: RootId = None,
) -> JoinPlan:
    return await run_blocking(run_plan_join, connection_id, table_ids, edge_ids, root_table_id)


def register_join_tools(server: MCPServer) -> None:
    server.tool(
        name="find_fields",
        description=(
            "Tìm các trường thông tin (cột) cần cho câu hỏi và cho biết chúng nằm ở bảng nào. Kết quả nhóm theo bảng, "
            "mỗi cột kèm điểm liên quan đã xếp hạng lại bằng Jev; chỉ giữ cột có điểm từ ngưỡng cấu hình trở lên. "
            "`match=none` nghĩa là không có cột nào phù hợp: hãy hỏi lại người dùng, đừng đoán. Dùng khi chưa có "
            "metric phù hợp, rồi gọi plan_join với các bảng cần nối."
        ),
    )(find_fields)
    server.tool(
        name="plan_join",
        description=(
            "Tính cách nối các bảng bằng đồ thị quan hệ đã khai báo trong data dictionary (không suy đoán theo tên "
            "cột). Trả về phương án JOIN (không kèm cột select), chữ ký join và cảnh báo nhân dòng. `ambiguous`: "
            "có nhiều cách nối, chọn một phương án rồi gọi lại với edge_ids. `not_declared`: thiếu quan hệ khai báo, "
            "hãy báo người dùng bổ sung data dictionary thay vì tự nối. "
            "Hãy truyền root_table_id theo câu hỏi: 'doanh thu theo khách' gốc là đơn hàng, "
            "'khách chưa có đơn' gốc là khách hàng."
        ),
    )(plan_join)
