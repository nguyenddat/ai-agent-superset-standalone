from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.models import GlossaryTerm

from .base import IndexDocument, build_document
from .context import CatalogContext

TOPIC = "expert_rule"

OPERATOR_LABELS = {
    "equals": "bằng", "not_equals": "khác", "contains": "chứa", "not_contains": "không chứa",
    "greater_than": "lớn hơn", "greater_than_or_equal": "từ ... trở lên", "less_than": "nhỏ hơn",
    "less_than_or_equal": "từ ... trở xuống", "in": "là một trong", "not_in": "không thuộc",
    "is_null": "để trống", "is_not_null": "có giá trị",
}


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
            f"Nhóm: {rule['group_name']}" if rule["group_name"] else None,
            f"Bảng: {table_label}" if table_label else None,
            f"Mô tả: {rule['description']}" if rule["description"] else None,
            f"Điều kiện: {'; '.join(conditions)}" if conditions else None,
            f"Ngoại lệ: {'; '.join(exceptions)}" if exceptions else None,
            f"Ví dụ: {'; '.join(examples)}" if examples else None,
            f"Thuật ngữ: {', '.join(terms)}" if terms else None,
            f"Metric: {', '.join(metrics)}" if metrics else None,
        ]))
        documents.append(build_document(
            TOPIC, rule["id"], context.connection_id, rule["table_id"], text, name=rule["name"],
            display_name=rule["name"], glossary_term_ids=sorted(str(item) for item in rule["glossary_term_ids"]),
            metric_ids=sorted(str(item) for item in rule["metric_ids"]),
        ))
    return documents
