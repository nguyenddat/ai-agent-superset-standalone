import logging
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ...common.errors import Text2SqlConnectionNotFound, Text2SqlInvalidRequest, Text2SqlRerankUnavailable
from ..ingestion.registry import TOPICS
from ..qdrant_db_service import QdrantDbService
from ..rerank.base import Reranker

logger = logging.getLogger("text2sql.topic_search")

OWN_KNOWLEDGE = "own_knowledge"


@dataclass(frozen=True)
class TopicHit:
    entity_id: UUID
    table_id: UUID | None
    name: str
    display_name: str
    text: str
    score: float
    rerank_score: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopicSearchOutcome:
    hits: list[TopicHit]
    reranked: bool = False
    rerank_error: str | None = None


def _hit(point: dict[str, Any]) -> TopicHit:
    payload = point["payload"]
    table_id = payload.get("table_id")
    return TopicHit(
        entity_id=UUID(payload["entity_id"]), table_id=UUID(table_id) if table_id else None,
        name=payload.get("name", ""), display_name=payload.get("display_name", payload.get("name", "")),
        text=payload.get("text", ""), score=round(float(point.get("score", 0.0)), 6), payload=payload,
    )


class TopicSearchService:
    def __init__(self, session: Session, index: QdrantDbService, embedding: OpenRouterEmbedding) -> None:
        self.session = session
        self.index = index
        self.embedding = embedding

    def search(
        self, connection_id: UUID, topic: str, question: str, k: int = 5, reranker: Reranker | None = None,
        user_id: str | None = None, vector: list[float] | None = None,
    ) -> TopicSearchOutcome:
        if topic not in TOPICS:
            raise Text2SqlInvalidRequest(f"Topic không hợp lệ: {topic}.")
        filters: dict[str, str] | None = None
        if topic == OWN_KNOWLEDGE:
            if not user_id or not user_id.strip():
                raise Text2SqlInvalidRequest("Cần user_id để tìm tri thức riêng.")
            filters = {"user_id": user_id.strip()}
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        vector = vector or self.embedding.embed([question])[0]
        pool = max(k, config.text2sql_rerank_pool) if reranker is not None else k
        points = self.index.search(question, vector, str(connection_id), topic, pool, filters)
        hits = [_hit(point) for point in points]
        if reranker is None or not hits:
            return TopicSearchOutcome(hits=hits[:k])
        try:
            scores = reranker.rerank(question, [hit.text for hit in hits], topic)
        except Text2SqlRerankUnavailable as error:
            logger.warning("Rerank %s lỗi, dùng thứ tự gốc: %s", topic, error.code)
            return TopicSearchOutcome(hits=hits[:k], rerank_error=error.code)
        rescored = [replace(hit, rerank_score=round(score, 6)) for hit, score in zip(hits, scores, strict=True)]
        order = {hit.entity_id: position for position, hit in enumerate(hits)}
        rescored.sort(key=lambda hit: (-(hit.rerank_score or 0.0), order[hit.entity_id]))
        return TopicSearchOutcome(hits=rescored[:k], reranked=True)
