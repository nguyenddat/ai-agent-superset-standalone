from .documents.base import DocumentBuilder
from .documents.column import TOPIC as COLUMN
from .documents.column import build_column_documents
from .documents.expert_rule import TOPIC as EXPERT_RULE
from .documents.expert_rule import build_expert_rule_documents
from .documents.glossary import TOPIC as GLOSSARY
from .documents.glossary import build_glossary_documents
from .documents.metric import TOPIC as METRIC
from .documents.metric import build_metric_documents
from .documents.own_knowledge import TOPIC as OWN_KNOWLEDGE
from .documents.own_knowledge import build_own_knowledge_documents
from .documents.table import TOPIC as TABLE
from .documents.table import build_table_documents

TOPIC_BUILDERS: dict[str, DocumentBuilder] = {
    TABLE: build_table_documents,
    COLUMN: build_column_documents,
    METRIC: build_metric_documents,
    GLOSSARY: build_glossary_documents,
    EXPERT_RULE: build_expert_rule_documents,
    OWN_KNOWLEDGE: build_own_knowledge_documents,
}

TOPICS: tuple[str, ...] = tuple(TOPIC_BUILDERS)

DEFAULT_INTERVAL_SECONDS: dict[str, int] = {
    TABLE: 900,
    COLUMN: 900,
    METRIC: 300,
    GLOSSARY: 300,
    EXPERT_RULE: 300,
    OWN_KNOWLEDGE: 120,
}


def validate_topics(topics: list[str] | None) -> tuple[str, ...]:
    if topics is None:
        return TOPICS
    unknown = sorted(set(topics) - set(TOPICS))
    if unknown:
        raise ValueError(f"Topic không hợp lệ: {', '.join(unknown)}.")
    return tuple(topic for topic in TOPICS if topic in set(topics))
