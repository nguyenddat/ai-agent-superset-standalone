import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from backend.core.setting import config
from backend.modules.business_model.services import DomainAssignment
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.models import GlossaryTerm
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import metric_domains
from backend.modules.own_knowledge.services import OwnKnowledgeService

from ..utils.topics import COLUMN, EXPERT_RULE, GLOSSARY, METRIC, OWN_KNOWLEDGE, TABLE
from .catalog_context import CatalogContext

OPERATOR_LABELS = {
    "equals": "bằng", "not_equals": "khác", "contains": "chứa", "not_contains": "không chứa",
    "greater_than": "lớn hơn", "greater_than_or_equal": "từ ... trở lên", "less_than": "nhỏ hơn",
    "less_than_or_equal": "từ ... trở xuống", "in": "là một trong", "not_in": "không thuộc",
    "is_null": "để trống", "is_not_null": "có giá trị",
}

KIND_LABELS = {"glossary": "thuật ngữ", "metric": "metric", "expert_rule": "quy tắc"}


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
            TABLE, entry.table.id, context.connection_id, entry.table.id, text,
            name=entry.table.name, display_name=entry.label,
        ))
    return documents


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
            COLUMN, column.id, context.connection_id, column.table_id, text,
            name=column.name, display_name=entry.label,
        ))
    return documents


def referenced_columns(expression: str, columns_by_name: dict[str, UUID]) -> list[str]:
    try:
        parsed = parse_one(expression, read="postgres")
    except SqlglotError:
        return []
    if parsed is None:
        return []
    identifiers = {column.name.lower() for column in parsed.find_all(exp.Column)}
    return sorted(str(columns_by_name[name]) for name in identifiers if name in columns_by_name)


def build_metric_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    documents: list[IndexDocument] = []
    domains = DomainAssignment(session, metric_domains, "metric_id").read([metric.id for metric in context.metrics])
    for metric in context.metrics:
        if metric.table_id is None or metric.source_sql:
            continue
        table = context.tables[metric.table_id]
        referenced = referenced_columns(metric.expression, context.columns_by_table.get(table.table.id, {}))
        column_labels = [context.column_label(UUID(value)) for value in referenced]
        text = " | ".join(filter(None, [
            f"Metric: {metric.label or metric.name}", f"Tên kỹ thuật: {metric.name}",
            f"Mô tả: {metric.description}" if metric.description else None,
            f"Miền nghiệp vụ: {', '.join(domain['name'] for domain in domains[metric.id])}"
            if metric.id in domains else None,
            f"Bảng: {table.label} ({table.qualified_name})",
            f"Cột liên quan: {', '.join(filter(None, column_labels))}" if referenced else None,
        ]))
        documents.append(build_document(
            METRIC, metric.id, context.connection_id, table.table.id, text, name=metric.name,
            display_name=metric.label or metric.name, origin=metric.origin, is_active=True,
            column_ids=referenced,
        ))
    return documents


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
            GLOSSARY, term["id"], context.connection_id, None, text, name=term["name"], display_name=term["name"],
            synonyms=list(synonyms), table_ids=sorted(links["table"]), column_ids=sorted(links["column"]),
            metric_ids=sorted(links["metric"]),
        ))
    return documents


def condition_text(context: CatalogContext, condition: dict[str, Any]) -> str:
    column = context.column_label(UUID(condition["column_id"])) or "cột không xác định"
    operator = OPERATOR_LABELS.get(condition["operator"], condition["operator"])
    value = condition.get("value")
    if condition["operator"] in ("is_null", "is_not_null") or value is None:
        return f"{column} {operator}"
    rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
    return f"{column} {operator} {rendered}"


def build_expert_rule_documents(session: Session, context: CatalogContext) -> list[IndexDocument]:
    rules = ExpertRuleService(session).discovery(context.connection_id)
    term_ids = {term_id for rule in rules for term_id in rule["glossary_term_ids"]}
    term_names = {
        term.id: term.canonical_name
        for term in session.scalars(select(GlossaryTerm).where(GlossaryTerm.id.in_(term_ids)))
    } if term_ids else {}
    documents: list[IndexDocument] = []
    for rule in rules:
        table_label = context.table_label(rule["table_id"])
        conditions = [condition_text(context, condition) for condition in rule["conditions"]]
        exceptions = [f"khi {item['when']} thì {item['outcome']}" for item in rule["exceptions"]]
        examples = [f"\"{item['question']}\" → {item['intent']}" for item in rule["examples"]]
        terms = [term_names[term_id] for term_id in rule["glossary_term_ids"] if term_id in term_names]
        metrics = [label for label in map(context.metric_label, rule["metric_ids"]) if label]
        text = " | ".join(filter(None, [
            f"Quy tắc: {rule['name']}",
            f"Miền nghiệp vụ: {', '.join(domain['name'] for domain in rule['business_domains'])}"
            if rule["business_domains"] else None,
            f"Bảng: {table_label}" if table_label else None,
            f"Mô tả: {rule['description']}" if rule["description"] else None,
            f"Điều kiện: {'; '.join(conditions)}" if conditions else None,
            f"Ngoại lệ: {'; '.join(exceptions)}" if exceptions else None,
            f"Ví dụ: {'; '.join(examples)}" if examples else None,
            f"Thuật ngữ: {', '.join(terms)}" if terms else None,
            f"Metric: {', '.join(metrics)}" if metrics else None,
        ]))
        documents.append(build_document(
            EXPERT_RULE, rule["id"], context.connection_id, rule["table_id"], text, name=rule["name"],
            display_name=rule["name"], glossary_term_ids=sorted(str(item) for item in rule["glossary_term_ids"]),
            metric_ids=sorted(str(item) for item in rule["metric_ids"]),
        ))
    return documents


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
            OWN_KNOWLEDGE, entry["id"], context.connection_id, entry["table_id"], text, name=entry["name"],
            display_name=entry["name"], user_id=entry["user_id"], kind=entry["kind"],
        ))
    return documents


TOPIC_BUILDERS: dict[str, DocumentBuilder] = {
    TABLE: build_table_documents,
    COLUMN: build_column_documents,
    METRIC: build_metric_documents,
    GLOSSARY: build_glossary_documents,
    EXPERT_RULE: build_expert_rule_documents,
    OWN_KNOWLEDGE: build_own_knowledge_documents,
}

