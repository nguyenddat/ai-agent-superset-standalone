from sqlalchemy.orm import Session

from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "table"


def build_table_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    for entry in context.tables.values():
        dictionary = entry.dictionary
        text = " | ".join(filter(None, [
            f"Bảng: {entry.label}", f"Tên kỹ thuật: {entry.qualified_name}",
            f"Mô tả: {dictionary.description}" if dictionary and dictionary.description else None,
            f"Grain: {dictionary.grain_description}" if dictionary and dictionary.grain_description else None,
        ]))
        documents.append(build_document(
            TOPIC, entry.table.id, context.connection_id, entry.table.id, text,
            name=entry.table.name, display_name=entry.label,
        ))
    return documents
