import logging
import unicodedata
from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.core.setting import config
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.metric_management.models import Metric

from ...common.errors import Text2SqlConnectionNotFound, Text2SqlRerankUnavailable
from ...common.sql_columns import referenced_columns
from ..ingestion.documents.context import load_context
from ..ingestion.documents.metric import build_metric_documents
from ..qdrant_db_service import QdrantDbService
from ..rerank.base import Reranker

logger = logging.getLogger("text2sql.retrieve")


@dataclass(frozen=True)
class MetricCandidate:
    metric_id: UUID
    table_id: UUID
    name: str
    label: str | None
    description: str | None
    score: float
    matched_topics: list[str]
    rerank_score: float | None = None


@dataclass(frozen=True)
class RetrievalOutcome:
    candidates: list[MetricCandidate]
    reranked: bool = False
    rerank_error: str | None = None


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return " ".join("".join(character for character in normalized if unicodedata.category(character) != "Mn").split())


class RetrievalService:
    def __init__(self, session: Session, index: QdrantDbService, embedding: OpenRouterEmbedding) -> None:
        self.session = session
        self.index = index
        self.embedding = embedding

    def top_metrics(
        self, connection_id: UUID, question: str, k: int = 5, reranker: Reranker | None = None
    ) -> list[MetricCandidate]:
        return self.search(connection_id, question, k, reranker).candidates

    def search(
        self, connection_id: UUID, question: str, k: int = 5, reranker: Reranker | None = None
    ) -> RetrievalOutcome:
        ranked = self._ranked_candidates(connection_id, question, k)
        pool = ranked[:max(k, config.text2sql_rerank_pool)]
        if reranker is None or not pool:
            return RetrievalOutcome(candidates=ranked[:k])
        try:
            passages = self._passages(connection_id, pool)
            scores = reranker.rerank(question, passages, "metric")
        except Text2SqlRerankUnavailable as error:
            logger.warning("Rerank lỗi, dùng thứ tự gốc: %s", error.code)
            return RetrievalOutcome(candidates=ranked[:k], rerank_error=error.code)
        rescored = [
            replace(candidate, rerank_score=round(score, 6)) for candidate, score in zip(pool, scores, strict=True)
        ]
        rescored.sort(key=lambda candidate: (
            -(candidate.rerank_score or 0.0), -candidate.score, candidate.name, str(candidate.metric_id)
        ))
        return RetrievalOutcome(candidates=rescored[:k], reranked=True)

    def _passages(self, connection_id: UUID, candidates: list[MetricCandidate]) -> list[str]:
        documents = {
            document.entity_id: document.text
            for document in build_metric_documents(self.session, load_context(self.session, connection_id))
        }
        return [
            documents.get(str(candidate.metric_id), f"Metric: {candidate.label or candidate.name}")
            for candidate in candidates
        ]

    def _ranked_candidates(self, connection_id: UUID, question: str, k: int) -> list[MetricCandidate]:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        vector = self.embedding.embed([question])[0]
        hits = {
            topic: self.index.search(question, vector, str(connection_id), topic, limit)
            for topic, limit in (("metric", max(30, k * 6)), ("table", 15), ("column", 30))
        }
        metric_ranks = {point["payload"]["entity_id"]: rank for rank, point in enumerate(hits["metric"])}
        table_ranks = {point["payload"]["table_id"]: rank for rank, point in enumerate(hits["table"])}
        column_ranks = {point["payload"]["entity_id"]: rank for rank, point in enumerate(hits["column"])}
        metrics = self.session.scalars(
            select(Metric)
            .join(DatabaseTable, Metric.table_id == DatabaseTable.id)
            .join(DatabaseSchema, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(
                DatabaseSchema.connection_id == connection_id,
                Metric.is_active.is_(True),
                or_(Metric.source_sql.is_(None), Metric.source_sql == ""),
            )
        ).all()
        table_ids = {metric.table_id for metric in metrics if metric.table_id is not None}
        columns_by_table: dict[UUID, dict[str, UUID]] = {}
        if table_ids and column_ranks:
            for column in self.session.scalars(select(DatabaseColumn).where(DatabaseColumn.table_id.in_(table_ids))):
                columns_by_table.setdefault(column.table_id, {})[column.name.lower()] = column.id
        candidates: list[MetricCandidate] = []
        for metric in metrics:
            if metric.table_id is None:
                continue
            metric_id = str(metric.id)
            table_id = str(metric.table_id)
            direct_rank = metric_ranks.get(metric_id)
            table_rank = table_ranks.get(table_id)
            metric_column_ids = (
                referenced_columns(metric.expression, columns_by_table.get(metric.table_id, {}))
                if column_ranks else []
            )
            matching_columns = [
                column_ranks[column_id] for column_id in metric_column_ids
                if column_id in column_ranks
            ]
            if direct_rank is None and table_rank is None and not matching_columns:
                continue
            score = 1 / (direct_rank + 1) if direct_rank is not None else 0.0
            if table_rank is not None:
                score += 0.12 / (table_rank + 1)
            if matching_columns:
                score += 0.18 / (min(matching_columns) + 1)
            query = _normalized(question)
            if any(_normalized(name) in query for name in (metric.name, metric.label) if name):
                score += 0.2
            topics = [topic for topic, matched in (
                ("metric", direct_rank is not None), ("table", table_rank is not None),
                ("column", bool(matching_columns)),
            ) if matched]
            candidates.append(MetricCandidate(
                metric_id=metric.id, table_id=metric.table_id, name=metric.name,
                label=metric.label, description=metric.description, score=round(score, 6), matched_topics=topics,
            ))
        return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.name, str(candidate.metric_id)))
