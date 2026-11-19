from uuid import UUID

from sqlalchemy.orm import Session

from backend.modules.glossary_management.services import GlossaryService

from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "glossary"


def _link_text(context: CatalogContext, kind: str, target_id: UUID) -> str | None:
    if kind == "table":
        label = context.table_label(target_id)
        return f"Bảng {label}" if label else None
    if kind == "column":
        column = context.columns_by_id.get(target_id)
        if column is None:
            return None
        table_label = context.table_label(column.column.table_id)
        return f"Cột {column.label} (bảng {table_label})" if table_label else f"Cột {column.label}"
    label = context.metric_label(target_id)
    return f"Metric {label}" if label else None


def build_glossary_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    for term in GlossaryService(session).discovery(context.connection_id):
        links: dict[str, list[str]] = {"table": [], "column": [], "metric": []}
        link_texts: list[str] = []
        for link in term["links"]:
            target_id = UUID(link["id"])
            text = _link_text(context, link["kind"], target_id)
            if text is not None:
                links[link["kind"]].append(str(target_id))
                link_texts.append(text)
        synonyms = term["synonyms"]
        text = " | ".join(filter(None, [
            f"Thuật ngữ: {term['name']}", f"Định nghĩa: {term['definition']}",
            f"Miền nghiệp vụ: {', '.join(domain['name'] for domain in term['business_domains'])}"
            if term["business_domains"] else None,
            f"Đồng nghĩa: {', '.join(synonyms)}" if synonyms else None,
            f"Liên quan: {'; '.join(link_texts)}" if link_texts else None,
        ]))
        documents.append(build_document(
            TOPIC, term["id"], context.connection_id, None, text, name=term["name"], display_name=term["name"],
            synonyms=list(synonyms), table_ids=sorted(links["table"]), column_ids=sorted(links["column"]),
            metric_ids=sorted(links["metric"]),
        ))
    return documents
