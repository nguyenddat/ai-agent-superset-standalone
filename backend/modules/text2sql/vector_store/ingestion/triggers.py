from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Select, event, select
from sqlalchemy.orm import Session

from backend.modules.data_dictionary.models import ColumnDictionary, ColumnSynonym, TableDictionary
from backend.modules.database_connection.models import DatabaseColumn, DatabaseSchema, DatabaseTable
from backend.modules.expert_rule_management.models import (
    ExpertRule,
    ExpertRuleGlossaryLink,
    ExpertRuleMetricLink,
    ExpertRuleRevision,
)
from backend.modules.glossary_management.models import GlossaryLink, GlossaryRevision, GlossaryTerm
from backend.modules.metric_management.models import Metric
from backend.modules.own_knowledge.models import OwnKnowledgeEntry

from ...models.ingestion_job import EVENT
from .jobs import enqueue_jobs
from .registry import TOPICS

ConnectionResolver = Callable[["ConnectionLookup", Any], UUID | None]

STRUCTURE_TOPICS = TOPICS
METRIC_TOPICS = ("metric", "glossary", "expert_rule", "own_knowledge")
GLOSSARY_TOPICS = ("glossary", "expert_rule", "own_knowledge")
EXPERT_RULE_TOPICS = ("expert_rule", "own_knowledge")
OWN_KNOWLEDGE_TOPICS = ("own_knowledge",)

_registered = False


class ConnectionLookup:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._cache: dict[tuple[str, UUID], UUID | None] = {}

    def _scalar(self, name: str, key: UUID | None, statement: Select) -> UUID | None:
        if key is None:
            return None
        if (name, key) not in self._cache:
            self._cache[(name, key)] = self.connection.execute(statement).scalar()
        return self._cache[(name, key)]

    def table(self, table_id: UUID | None) -> UUID | None:
        return self._scalar(
            "table", table_id,
            select(DatabaseSchema.connection_id).join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(DatabaseTable.id == table_id),
        )

    def column(self, column_id: UUID | None) -> UUID | None:
        table_id = self._scalar(
            "column_table", column_id, select(DatabaseColumn.table_id).where(DatabaseColumn.id == column_id)
        )
        return self.table(table_id)

    def column_dictionary(self, dictionary_id: UUID | None) -> UUID | None:
        column_id = self._scalar(
            "dictionary_column", dictionary_id,
            select(ColumnDictionary.column_id).where(ColumnDictionary.id == dictionary_id),
        )
        return self.column(column_id)

    def glossary_term(self, term_id: UUID | None) -> UUID | None:
        return self._scalar(
            "glossary_term", term_id, select(GlossaryTerm.connection_id).where(GlossaryTerm.id == term_id)
        )

    def glossary_revision(self, revision_id: UUID | None) -> UUID | None:
        return self._scalar(
            "glossary_revision", revision_id,
            select(GlossaryTerm.connection_id).join(GlossaryRevision, GlossaryRevision.term_id == GlossaryTerm.id)
            .where(GlossaryRevision.id == revision_id),
        )

    def rule(self, rule_id: UUID | None) -> UUID | None:
        return self._scalar("rule", rule_id, select(ExpertRule.connection_id).where(ExpertRule.id == rule_id))

    def rule_revision(self, revision_id: UUID | None) -> UUID | None:
        return self._scalar(
            "rule_revision", revision_id,
            select(ExpertRule.connection_id).join(ExpertRuleRevision, ExpertRuleRevision.rule_id == ExpertRule.id)
            .where(ExpertRuleRevision.id == revision_id),
        )


WATCHED: dict[type, tuple[tuple[str, ...], ConnectionResolver]] = {
    DatabaseSchema: (STRUCTURE_TOPICS, lambda lookup, item: item.connection_id),
    DatabaseTable: (STRUCTURE_TOPICS, lambda lookup, item: lookup.table(item.id)),
    DatabaseColumn: (STRUCTURE_TOPICS, lambda lookup, item: lookup.table(item.table_id)),
    TableDictionary: (STRUCTURE_TOPICS, lambda lookup, item: lookup.table(item.table_id)),
    ColumnDictionary: (STRUCTURE_TOPICS, lambda lookup, item: lookup.column(item.column_id)),
    ColumnSynonym: (STRUCTURE_TOPICS, lambda lookup, item: lookup.column_dictionary(item.column_dictionary_id)),
    Metric: (METRIC_TOPICS, lambda lookup, item: lookup.table(item.table_id)),
    GlossaryTerm: (GLOSSARY_TOPICS, lambda lookup, item: item.connection_id),
    GlossaryRevision: (GLOSSARY_TOPICS, lambda lookup, item: lookup.glossary_term(item.term_id)),
    GlossaryLink: (GLOSSARY_TOPICS, lambda lookup, item: lookup.glossary_revision(item.revision_id)),
    ExpertRule: (EXPERT_RULE_TOPICS, lambda lookup, item: item.connection_id),
    ExpertRuleRevision: (EXPERT_RULE_TOPICS, lambda lookup, item: lookup.rule(item.rule_id)),
    ExpertRuleGlossaryLink: (EXPERT_RULE_TOPICS, lambda lookup, item: lookup.rule_revision(item.revision_id)),
    ExpertRuleMetricLink: (EXPERT_RULE_TOPICS, lambda lookup, item: lookup.rule_revision(item.revision_id)),
    OwnKnowledgeEntry: (OWN_KNOWLEDGE_TOPICS, lambda lookup, item: item.connection_id),
}


def _changed_items(session: Session):
    yield from session.new
    yield from (item for item in session.dirty if session.is_modified(item))
    yield from session.deleted


def enqueue_for_changes(session: Session, flush_context: object) -> None:
    pending: dict[UUID, set[str]] = {}
    lookup: ConnectionLookup | None = None
    for item in _changed_items(session):
        watched = WATCHED.get(type(item))
        if watched is None:
            continue
        topics, resolve = watched
        lookup = lookup or ConnectionLookup(session.connection())
        connection_id = resolve(lookup, item)
        if connection_id is not None:
            pending.setdefault(connection_id, set()).update(topics)
    if lookup is None:
        return
    for connection_id, topics in pending.items():
        enqueue_jobs(lookup.connection, [connection_id], [topic for topic in TOPICS if topic in topics], EVENT)


def register_triggers() -> None:
    global _registered
    if not _registered:
        event.listen(Session, "after_flush", enqueue_for_changes)
        _registered = True
