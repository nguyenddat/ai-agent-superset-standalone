from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.modules.database_connection.models import DatabaseConnection

from ..repositories.qdrant_repository import QdrantRepository
from ..utils.exceptions import Text2SqlConnectionNotFound
from ..utils.topics import TOPICS
from .catalog_context import load_context
from .index_documents import TOPIC_BUILDERS, IndexDocument

EMBED_BATCH_SIZE = 32
DELETE_BATCH_SIZE = 256


@dataclass(frozen=True)
class SyncResult:
    connection_id: UUID
    topics: tuple[str, ...]
    total: int
    indexed: int
    unchanged: int
    deleted: int


class IngestionService:
    def __init__(self, session: Session, index: QdrantRepository, embedding: OpenRouterEmbedding) -> None:
        self.session = session
        self.index = index
        self.embedding = embedding

    def sync(self, connection_id: UUID, topics: Sequence[str] = TOPICS) -> SyncResult:
        topics = tuple(topics)
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        context = load_context(self.session, connection_id)
        documents: list[IndexDocument] = []
        for topic in topics:
            documents.extend(TOPIC_BUILDERS[topic](self.session, context))
        self.index.ensure_collection()
        existing = self.index.existing_points(str(connection_id), topics)
        changed = [
            document for document in documents
            if existing.get(document.point_id, {}).get("content_hash") != document.content_hash
        ]
        for start in range(0, len(changed), EMBED_BATCH_SIZE):
            batch = changed[start:start + EMBED_BATCH_SIZE]
            vectors = self.embedding.embed([document.text for document in batch])
            self.index.upsert([
                {"id": document.point_id, "vector": vector, "payload": document.payload}
                for document, vector in zip(batch, vectors, strict=True)
            ])
        stale = sorted(set(existing) - {document.point_id for document in documents})
        for start in range(0, len(stale), DELETE_BATCH_SIZE):
            self.index.delete(stale[start:start + DELETE_BATCH_SIZE])
        return SyncResult(
            connection_id=connection_id, topics=topics, total=len(documents), indexed=len(changed),
            unchanged=len(documents) - len(changed), deleted=len(stale),
        )
