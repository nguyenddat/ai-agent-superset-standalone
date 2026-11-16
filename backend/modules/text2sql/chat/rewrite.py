from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from backend.agent_package.agents.question_rewrite_agent import QuestionRewriteAgent, RewriteDraft

from .context import AskContext
from .schemas import NamedItem, RewriteInfo


@dataclass
class RewriteOutcome:
    info: RewriteInfo
    term_ids: list[UUID] = field(default_factory=list)
    rule_ids: list[UUID] = field(default_factory=list)


def _metric_labels(context: AskContext, metric_ids: list[UUID]) -> list[str]:
    labels = (context.catalog.metric_label(metric_id) for metric_id in metric_ids)
    return [label for label in labels if label]


def build_rewrite_context(
    question: str, today: date, context: AskContext, history: list[dict] | None = None,
) -> dict:
    payload = {
        "question": question,
        "today": today.isoformat(),
        "glossary_terms": [
            {
                "id": str(term.id), "name": term.name, "synonyms": term.synonyms, "definition": term.definition,
                "metrics": _metric_labels(context, term.metric_ids),
            }
            for term in context.terms
        ],
        "expert_rules": [
            {
                "id": str(rule.id), "name": rule.name, "description": rule.description,
                "metrics": _metric_labels(context, rule.metric_ids),
                "conditions": rule.conditions_text,
                "exceptions": [{"when": item["when"], "outcome": item["outcome"]} for item in rule.exceptions],
            }
            for rule in context.rules
        ],
        "own_knowledge": [
            {"id": str(entry.id), "name": entry.name, "definition": entry.definition} for entry in context.own
        ],
    }
    if history:
        payload["history"] = history
    return payload


def _valid(ids: list[str], allowed: dict[UUID, str]) -> list[UUID]:
    chosen: list[UUID] = []
    for raw in ids:
        try:
            value = UUID(str(raw).strip())
        except ValueError:
            continue
        if value in allowed and value not in chosen:
            chosen.append(value)
    return chosen


def rewrite_question(rewriter: QuestionRewriteAgent, question: str, today: date, context: AskContext) -> RewriteOutcome:
    return rewrite_outcome(rewriter.run(build_rewrite_context(question, today, context)), question, context)


def rewrite_outcome(draft: RewriteDraft, question: str, context: AskContext) -> RewriteOutcome:
    terms = {term.id: term.name for term in context.terms}
    rules = {rule.id: rule.name for rule in context.rules}
    own = {entry.id: entry.name for entry in context.own}
    term_ids, rule_ids = _valid(draft.glossary_term_ids, terms), _valid(draft.rule_ids, rules)
    own_ids = _valid(draft.own_knowledge_ids, own)
    return RewriteOutcome(
        info=RewriteInfo(
            original_question=question, rewritten_question=draft.rewritten_question.strip() or question,
            glossary_terms=[NamedItem(id=item, name=terms[item]) for item in term_ids],
            rules=[NamedItem(id=item, name=rules[item]) for item in rule_ids],
            own_knowledge=[NamedItem(id=item, name=own[item]) for item in own_ids],
            changes=[change.strip() for change in draft.changes if change.strip()],
            analysis=[step.strip() for step in draft.analysis if step.strip()],
        ),
        term_ids=term_ids, rule_ids=rule_ids,
    )
