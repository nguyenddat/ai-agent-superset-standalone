from uuid import UUID

from mcp.server import MCPServer
from pydantic import BaseModel

from backend.modules.data_dictionary.schemas.schema_data_dictionary import ColumnDictionaryOut, TableDictionaryOut
from backend.modules.text2sql.details.service import DetailService

from .common import (
    ConnectionId,
    QuestionText,
    RerankFlag,
    TopK5,
    clean_question,
    match_signal,
    rerank_warning,
    run_blocking,
    search_session,
)


class TableColumn(BaseModel):
    column_id: UUID
    name: str
    display_name: str
    data_type: str
    semantic_role: str
    description: str | None = None
    unit: str | None = None
    synonyms: list[str] | None = None
    references: str | None = None
    contains_pii: bool | None = None


class TableHit(BaseModel):
    table_id: UUID
    name: str
    display_name: str
    description: str | None
    grain: str | None
    kind: str | None
    contains_pii: bool
    score: float
    rerank_score: float | None
    columns: list[TableColumn]


class SearchTablesOut(BaseModel):
    hits: list[TableHit]
    reranked: bool
    rerank_warning: str | None
    match: str
    note: str | None


def compact_column(column: ColumnDictionaryOut) -> TableColumn:
    reference = column.referenced_column
    return TableColumn(
        column_id=column.column_id, name=column.name, display_name=column.display_name, data_type=column.data_type,
        semantic_role=column.semantic_role, description=column.description or None, unit=column.unit,
        synonyms=column.synonyms or None,
        references=f"{reference.table_name}.{reference.column_name}" if reference else None,
        contains_pii=True if column.contains_pii else None,
    )


def compact_table(table: TableDictionaryOut, score: float, rerank_score: float | None) -> TableHit:
    return TableHit(
        table_id=table.table_id, name=f"{table.schema_name}.{table.table_name}", display_name=table.display_name,
        description=table.description, grain=table.grain_description, kind=table.table_kind,
        contains_pii=table.contains_pii, score=score, rerank_score=rerank_score,
        columns=[compact_column(column) for column in table.columns],
    )


def run_search_tables(connection_id: UUID, question: str, k: int, rerank: bool) -> SearchTablesOut:
    with search_session(rerank) as (session, service, reranker):
        outcome = service.search(connection_id, "table", question, k, reranker)
        table_ids = [hit.entity_id for hit in outcome.hits]
        descriptions = {item.table.table_id: item for item in DetailService(session).tables(connection_id, table_ids)}
    match, note = match_signal([hit.rerank_score for hit in outcome.hits], outcome.reranked)
    return SearchTablesOut(
        hits=[
            compact_table(descriptions[hit.entity_id].table, hit.score, hit.rerank_score)
            for hit in outcome.hits if hit.entity_id in descriptions
        ],
        reranked=outcome.reranked, rerank_warning=rerank_warning(outcome.rerank_error), match=match, note=note,
    )


async def search_tables(
    connection_id: ConnectionId, question: QuestionText, k: TopK5 = 3, rerank: RerankFlag = False,
) -> SearchTablesOut:
    return await run_blocking(run_search_tables, connection_id, clean_question(question), k, rerank)


def register_table_tools(server: MCPServer) -> None:
    server.tool(
        name="search_tables",
        description=(
            "Tìm các bảng phù hợp nhất với câu hỏi (hybrid dense + BM25). Mỗi kết quả gồm mô tả, grain, loại bảng "
            "và danh sách cột rút gọn (ID, tên, kiểu, vai trò ngữ nghĩa, mô tả, đơn vị, từ đồng nghĩa, tham chiếu; "
            "trường rỗng được lược bỏ), nên không cần gọi thêm tool xem chi tiết. Trường `match` báo mức khớp: "
            "none (không có kết quả), weak (điểm liên quan thấp), ok, unverified (chưa rerank); đọc `note` khi có."
        ),
    )(search_tables)
