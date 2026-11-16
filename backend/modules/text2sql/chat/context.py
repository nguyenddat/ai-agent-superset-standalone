from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.own_knowledge.services import OwnKnowledgeService

from ..vector_store.ingestion.documents.context import CatalogContext, load_context
from ..vector_store.ingestion.documents.expert_rule import condition_text
from ..vector_store.qdrant_db_service import QdrantDbService
from ..vector_store.retrieve.topic_search import TopicSearchService

TERM_HITS = 5
RULE_HITS = 5
OWN_HITS = 3
MAX_TERMS = 8
MAX_RULES = 8


@dataclass(frozen=True)
class TermCandidate:
    id: UUID
    name: str
    synonyms: list[str]
    definition: str
    metric_ids: list[UUID]


@dataclass(frozen=True)
class RuleCandidate:
    id: UUID
    name: str
    description: str | None
    table_id: UUID | None
    conditions: list[dict]
    conditions_text: list[str]
    exceptions: list[dict]
    metric_ids: list[UUID]
    term_ids: list[UUID]


@dataclass(frozen=True)
class OwnCandidate:
    id: UUID
    name: str
    definition: str


@dataclass
class AskContext:
    catalog: CatalogContext
    terms: list[TermCandidate] = field(default_factory=list)
    rules: list[RuleCandidate] = field(default_factory=list)
    own: list[OwnCandidate] = field(default_factory=list)
    all_rules: list[RuleCandidate] = field(default_factory=list)

    def rules_for_metric(self, metric_id: UUID, table_id: UUID | None) -> list[RuleCandidate]:
        return [rule for rule in self.all_rules if metric_id in rule.metric_ids and rule.table_id == table_id]


def _rule(catalog: CatalogContext, item: dict) -> RuleCandidate:
    return RuleCandidate(
        id=item["id"], name=item["name"], description=item["description"], table_id=item["table_id"],
        conditions=list(item["conditions"]), exceptions=list(item["exceptions"]),
        conditions_text=[condition_text(catalog, condition) for condition in item["conditions"]],
        metric_ids=list(item["metric_ids"]), term_ids=list(item["glossary_term_ids"]),
    )


def _term(item: dict) -> TermCandidate:
    return TermCandidate(
        id=item["id"], name=item["name"], synonyms=list(item["synonyms"]), definition=item["definition"],
        metric_ids=[UUID(link["id"]) for link in item["links"] if link["kind"] == "metric"],
    )


class ContextGatherer:
    def __init__(self, session: Session, index: QdrantDbService, embedding: OpenRouterEmbedding) -> None:
        self.session = session
        self.search = TopicSearchService(session, index, embedding)
        self.embedding = embedding

    def gather(self, connection_id: UUID, question: str, user_id: str | None) -> AskContext:
        catalog = load_context(self.session, connection_id)
        vector = self.embedding.embed([question])[0]
        term_hits = [hit.entity_id for hit in self.search.search(
            connection_id, "glossary", question, TERM_HITS, vector=vector).hits]
        rule_hits = [hit.entity_id for hit in self.search.search(
            connection_id, "expert_rule", question, RULE_HITS, vector=vector).hits]
        all_terms = {item["id"]: _term(item) for item in GlossaryService(self.session).discovery(connection_id)}
        all_rules = [_rule(catalog, item) for item in ExpertRuleService(self.session).discovery(connection_id)]
        rules_by_id = {rule.id: rule for rule in all_rules}

        term_ids = [term_id for term_id in term_hits if term_id in all_terms]
        rule_ids = [rule_id for rule_id in rule_hits if rule_id in rules_by_id]
        for rule_id in list(rule_ids):
            term_ids += [term_id for term_id in rules_by_id[rule_id].term_ids if term_id in all_terms]
        for rule in all_rules:
            if rule.id not in rule_ids and any(term_id in term_hits for term_id in rule.term_ids):
                rule_ids.append(rule.id)
        context = AskContext(
            catalog=catalog,
            terms=[all_terms[term_id] for term_id in dict.fromkeys(term_ids)][:MAX_TERMS],
            rules=[rules_by_id[rule_id] for rule_id in dict.fromkeys(rule_ids)][:MAX_RULES],
            all_rules=all_rules,
        )
        if user_id and user_id.strip():
            own_ids = [hit.entity_id for hit in self.search.search(
                connection_id, "own_knowledge", question, OWN_HITS, user_id=user_id, vector=vector).hits]
            entries = {
                entry["id"]: entry
                for entry in OwnKnowledgeService(self.session).agent_entries(connection_id, user_id.strip())
            }
            context.own = [
                OwnCandidate(id=entries[own_id]["id"], name=entries[own_id]["name"],
                             definition=entries[own_id]["definition"])
                for own_id in own_ids if own_id in entries
            ]
        return context
