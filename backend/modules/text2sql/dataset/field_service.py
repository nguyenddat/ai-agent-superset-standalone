from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.setting import config

from ..details.service import DetailService
from ..vector_store.rerank.base import Reranker
from ..vector_store.retrieve.topic_search import TopicSearchService

FIELD_POOL = 15
NONE_NOTE = "Không có cột nào đủ liên quan; đừng suy đoán, hãy hỏi lại người dùng hoặc đổi cách diễn đạt."
UNVERIFIED_NOTE = "Chưa lọc được theo điểm liên quan (Jev lỗi hoặc không bật); kiểm tra kỹ trước khi dùng."


class FieldItem(BaseModel):
    column_id: UUID
    name: str
    display_name: str
    data_type: str
    semantic_role: str
    description: str | None = None
    unit: str | None = None
    contains_pii: bool | None = None
    score: float | None


class FieldTable(BaseModel):
    table_id: UUID
    name: str
    display_name: str
    description: str | None
    grain: str | None
    fields: list[FieldItem]


class FindFieldsOut(BaseModel):
    tables: list[FieldTable]
    match: str
    note: str | None
    reranked: bool


class FieldService:
    def __init__(self, session: Session, search: TopicSearchService, reranker: Reranker | None) -> None:
        self.session = session
        self.search = search
        self.reranker = reranker

    def find(self, connection_id: UUID, question: str, k: int = FIELD_POOL) -> FindFieldsOut:
        outcome = self.search.search(connection_id, "column", question, k, self.reranker)
        hits = outcome.hits
        if outcome.reranked:
            hits = [hit for hit in hits if (hit.rerank_score or 0.0) >= config.text2sql_field_min_score]
        if not hits:
            return FindFieldsOut(tables=[], match="none", note=NONE_NOTE, reranked=outcome.reranked)
        scores = {hit.entity_id: hit.rerank_score if outcome.reranked else hit.score for hit in hits}
        table_order = list(dict.fromkeys(hit.table_id for hit in hits if hit.table_id is not None))
        described = {item.table.table_id: item.table for item in DetailService(self.session).tables(
            connection_id, table_order,
        )}
        tables: list[FieldTable] = []
        for table_id in table_order:
            table = described.get(table_id)
            if table is None:
                continue
            fields = [
                FieldItem(
                    column_id=column.column_id, name=column.name, display_name=column.display_name,
                    data_type=column.data_type, semantic_role=column.semantic_role,
                    description=column.description or None, unit=column.unit,
                    contains_pii=True if column.contains_pii else None, score=scores[column.column_id],
                )
                for column in table.columns if column.column_id in scores
            ]
            fields.sort(key=lambda item: -(item.score or 0.0))
            tables.append(FieldTable(
                table_id=table.table_id, name=f"{table.schema_name}.{table.table_name}",
                display_name=table.display_name, description=table.description, grain=table.grain_description,
                fields=fields,
            ))
        tables.sort(key=lambda item: -(item.fields[0].score or 0.0) if item.fields else 0.0)
        reranked = outcome.reranked
        return FindFieldsOut(
            tables=tables, match="ok" if reranked else "unverified", note=None if reranked else UNVERIFIED_NOTE,
            reranked=reranked,
        )

