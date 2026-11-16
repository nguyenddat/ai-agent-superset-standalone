import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from backend.core.setting import config

from .context import CatalogContext


@dataclass(frozen=True)
class IndexDocument:
    point_id: str
    topic: str
    entity_id: str
    connection_id: str
    table_id: str | None
    text: str
    content_hash: str
    payload: dict[str, object]


DocumentBuilder = Callable[[Session, CatalogContext], list[IndexDocument]]


def build_document(
    topic: str, entity_id: UUID, connection_id: UUID, table_id: UUID | None, text: str, **fields: object
) -> IndexDocument:
    clean_text = " ".join(text.split())
    payload: dict[str, object] = {
        "topic": topic,
        "entity_id": str(entity_id),
        "connection_id": str(connection_id),
        "table_id": str(table_id) if table_id is not None else None,
        "text": clean_text,
        "model_version": config.text2sql_embedding_model,
        "embedding_dimensions": config.text2sql_embedding_dimensions,
        **fields,
    }
    content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    payload["content_hash"] = content_hash
    return IndexDocument(
        point_id=str(uuid5(NAMESPACE_URL, f"text2sql:{topic}:{entity_id}")),
        topic=topic,
        entity_id=str(entity_id),
        connection_id=str(connection_id),
        table_id=str(table_id) if table_id is not None else None,
        text=clean_text,
        content_hash=content_hash,
        payload=payload,
    )
