import logging
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, ElicitationResult, Resolve
from pydantic import BaseModel, Field
from sqlalchemy.engine import URL

from backend.modules.text2sql.dataset.compiler import DatasetCompiledQuery
from backend.modules.text2sql.dataset.join_schemas import JoinOption, JoinPlan
from backend.modules.text2sql.dataset.join_service import JoinService
from backend.modules.text2sql.dataset.schemas import DatasetQueryPlan, DatasetResult
from backend.modules.text2sql.dataset.selection import dataset_column_ids
from backend.modules.text2sql.dataset.service import DatasetQueryService
from backend.modules.text2sql.dataset.store import DatasetStore

from .common import ConnectionId, detail_session, run_blocking
from .join import RootId, TableIds, ViaIds
from .query import NOT_SUPPORTED, PiiConsent, client_can_elicit, confirmation_of, pii_message

logger = logging.getLogger("mcp.dataset")

AMBIGUOUS_HINT = "Hãy chọn một phương án trong options rồi gọi lại query_dataset với edge_ids của phương án đó."
NOT_DECLARED_MESSAGE = (
    "Chưa nối được các bảng vì thiếu quan hệ khai báo trong data dictionary. {detail} Cần bổ sung khai báo quan hệ "
    "(cột tham chiếu) trong data dictionary; hãy báo người dùng, không tự nối bảng."
)

PlanArgument = Annotated[
    DatasetQueryPlan,
    Field(description=(
        "Kế hoạch truy vấn: select (column_id kèm aggregation tùy chọn, hoặc expression viết cột dạng "
        "ten_bang.ten_cot), group_by, time, filters (placement where|join), order_by, limit. Không có from_sql: "
        "server tự tính phương án nối."
    )),
]


class DatasetInfo(BaseModel):
    dataset_id: UUID
    created: bool = Field(description="true nếu dataset vừa được tạo cho cách nối này.")
    selected_column_ids: list[UUID] = Field(description="Toàn bộ cột của dataset sau lần gọi này, theo thứ tự thêm.")
    added_column_ids: list[UUID] = Field(description="Các cột vừa được thêm vào dataset ở lần gọi này.")


class DatasetQueryOut(BaseModel):
    status: Literal["ok", "ambiguous", "not_declared"]
    join: JoinOption | None = Field(default=None, description="Phương án nối đã dùng khi status=ok.")
    options: list[JoinOption] = Field(default_factory=list, description="Các phương án nối khi status=ambiguous.")
    dataset: DatasetInfo | None = None
    result: DatasetResult | None = None
    message: str = ""


@dataclass
class PreparedDataset:
    join: JoinPlan
    compiled: DatasetCompiledQuery | None = None


@dataclass
class CompiledDataset:
    join: JoinOption
    plan: DatasetQueryPlan
    compiled: DatasetCompiledQuery
    source_url: URL
    service: DatasetQueryService


@dataclass
class StoredDataset:
    dataset: DatasetInfo
    warning: str | None = None


def run_prepare(
    connection_id: UUID, table_ids: list[UUID], root: UUID | None, via: list[UUID] | None, plan: DatasetQueryPlan,
) -> PreparedDataset:
    with detail_session() as session:
        join = JoinService(session).plan(connection_id, table_ids, via, root)
        if join.status != "ok":
            return PreparedDataset(join)
        return PreparedDataset(join, DatasetQueryService(session).prepare(connection_id, join.options[0], plan))


def run_compile(
    connection_id: UUID, table_ids: list[UUID], root: UUID | None, via: list[UUID] | None, plan: DatasetQueryPlan,
) -> PreparedDataset | CompiledDataset:
    with detail_session() as session:
        join = JoinService(session).plan(connection_id, table_ids, via, root)
        if join.status != "ok":
            return PreparedDataset(join)
        option = join.options[0]
        service = DatasetQueryService(session)
        compiled = service.prepare(connection_id, option, plan)
        return CompiledDataset(option, plan, compiled, service.resolve_source(connection_id), service)


def run_execute(prepared: CompiledDataset, confirmation: str) -> DatasetResult:
    return prepared.service.execute(prepared.compiled, prepared.source_url, confirmation)


def run_store(prepared: CompiledDataset) -> StoredDataset:
    with detail_session() as session:
        try:
            store = DatasetStore(session)
            dataset, created = store.get_or_create(prepared.compiled.connection_id, prepared.join)
            addition = store.add_columns(dataset, dataset_column_ids(session, prepared.join, prepared.plan))
            info = DatasetInfo(
                dataset_id=dataset.id, created=created, added_column_ids=addition.added,
                selected_column_ids=[UUID(item) for item in dataset.selected_column_ids],
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
    return StoredDataset(info, addition.warning)


def unresolved(join: JoinPlan) -> DatasetQueryOut:
    if join.status == "ambiguous":
        return DatasetQueryOut(status="ambiguous", options=join.options, message=f"{join.message} {AMBIGUOUS_HINT}")
    return DatasetQueryOut(status="not_declared", message=NOT_DECLARED_MESSAGE.format(detail=join.message))


async def dataset_consent(
    ctx: Context, connection_id: UUID, table_ids: list[UUID], plan: DatasetQueryPlan,
    root_table_id: UUID | None, edge_ids: list[UUID] | None,
) -> Elicit[PiiConsent] | str | None:
    prepared = await run_blocking(run_prepare, connection_id, table_ids, root_table_id, edge_ids, plan)
    if prepared.compiled is None or not prepared.compiled.pii_columns:
        return None
    if not client_can_elicit(ctx):
        logger.info("Client không hỗ trợ xác nhận; tiếp tục với dữ liệu đã che.")
        return NOT_SUPPORTED
    return Elicit(message=pii_message(prepared.compiled.pii_columns), schema=PiiConsent)


async def query_dataset(
    connection_id: ConnectionId,
    table_ids: TableIds,
    plan: PlanArgument,
    consent: Annotated[ElicitationResult[PiiConsent], Resolve(dataset_consent)],
    root_table_id: RootId = None,
    edge_ids: ViaIds = None,
) -> DatasetQueryOut:
    confirmation = confirmation_of(consent)
    prepared = await run_blocking(run_compile, connection_id, table_ids, root_table_id, edge_ids, plan)
    if isinstance(prepared, PreparedDataset):
        return unresolved(prepared.join)
    result = await run_blocking(run_execute, prepared, confirmation)
    stored = await run_blocking(run_store, prepared)
    return DatasetQueryOut(
        status="ok", join=prepared.join, dataset=stored.dataset, result=result, message=stored.warning or "",
    )


def register_dataset_tools(server: MCPServer) -> None:
    server.tool(
        name="query_dataset",
        description=(
            "Trả lời câu hỏi số liệu cần nối nhiều bảng khi ask_data báo no_metric. Quy trình: find_fields (tìm cột "
            "và bảng chứa chúng), plan_join (xem cách nối), rồi query_dataset. Bạn KHÔNG viết SQL hay FROM: server tự "
            "tính phương án nối từ quan hệ đã khai báo trong data dictionary, lưu thành dataset dùng lại (cùng cách "
            "nối thì chỉ thêm cột), dựng một câu SELECT, chạy chỉ đọc có timeout và giới hạn dòng. Chọn "
            "root_table_id theo câu hỏi: 'doanh thu theo khách' gốc là đơn hàng, 'khách chưa có đơn' gốc là khách "
            "hàng; các bảng khác LEFT JOIN từ gốc. Lọc cột của bảng được nối với placement=join để giữ dòng gốc không "
            "khớp; placement=where loại chúng. Biểu thức viết cột dạng ten_bang.ten_cot, ví dụ "
            "SUM(orders.total) / NULLIF(COUNT(DISTINCT orders.customer_id), 0). status=ambiguous: chọn một phương án "
            "trong options rồi gọi lại với edge_ids. status=not_declared: báo người dùng bổ sung khai báo quan hệ "
            "trong data dictionary, không tự nối. Dữ liệu cá nhân được che bằng placeholder, không lọc hay tính "
            "toán trên cột PII; chọn cột PII sẽ hỏi xác nhận người dùng. NULL là không có dữ liệu, không phải 0. "
            "Kết quả kèm sql đã chạy và cảnh báo nhân dòng."
        ),
    )(query_dataset)
