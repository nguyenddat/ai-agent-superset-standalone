from uuid import UUID

from sqlalchemy.orm import Session

from ....common.sql_columns import referenced_columns
from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "metric"


def build_metric_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    for metric in context.metrics:
        if metric.table_id is None or metric.source_sql:
            continue
        table = context.tables[metric.table_id]
        referenced = referenced_columns(metric.expression, context.columns_by_table.get(table.table.id, {}))
        column_labels = [context.column_label(UUID(value)) for value in referenced]
        text = " | ".join(filter(None, [
            f"Metric: {metric.label or metric.name}", f"Tên kỹ thuật: {metric.name}",
            f"Mô tả: {metric.description}" if metric.description else None,
            f"Bảng: {table.label} ({table.qualified_name})",
            f"Cột liên quan: {', '.join(filter(None, column_labels))}" if referenced else None,
        ]))
        documents.append(build_document(
            TOPIC, metric.id, context.connection_id, table.table.id, text, name=metric.name,
            display_name=metric.label or metric.name, origin=metric.origin, is_active=True,
            column_ids=referenced,
        ))
    return documents
