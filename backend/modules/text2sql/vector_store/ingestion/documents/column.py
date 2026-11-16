from sqlalchemy.orm import Session

from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "column"


def build_column_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    for entry in context.columns:
        column, dictionary = entry.column, entry.dictionary
        table = context.tables[column.table_id]
        text = " | ".join(filter(None, [
            f"Cột: {entry.label}", f"Tên kỹ thuật: {column.name}",
            f"Bảng: {table.label} ({table.qualified_name})",
            f"Mô tả: {dictionary.description}" if dictionary and dictionary.description else column.description,
            f"Thuật ngữ: {dictionary.business_term}" if dictionary and dictionary.business_term else None,
            f"Đồng nghĩa: {', '.join(entry.synonyms)}" if entry.synonyms else None,
            f"Đơn vị: {dictionary.unit}" if dictionary and dictionary.unit else None,
        ]))
        documents.append(build_document(
            TOPIC, column.id, context.connection_id, column.table_id, text,
            name=column.name, display_name=entry.label,
        ))
    return documents
