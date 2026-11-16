from sqlalchemy.orm import Session

from backend.modules.own_knowledge.services import OwnKnowledgeService

from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "own_knowledge"

KIND_LABELS = {"glossary": "thuật ngữ", "metric": "metric", "expert_rule": "quy tắc"}


def build_own_knowledge_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    for entry in OwnKnowledgeService(session).active_entries(context.connection_id):
        table_label = context.table_label(entry["table_id"])
        text = " | ".join(filter(None, [
            f"Tri thức riêng: {entry['name']}", f"Loại: {KIND_LABELS.get(entry['kind'], entry['kind'])}",
            f"Cách hiểu: {entry['definition']}",
            f"Bảng: {table_label}" if table_label else None,
        ]))
        documents.append(build_document(
            TOPIC, entry["id"], context.connection_id, entry["table_id"], text, name=entry["name"],
            display_name=entry["name"], user_id=entry["user_id"], kind=entry["kind"],
        ))
    return documents
