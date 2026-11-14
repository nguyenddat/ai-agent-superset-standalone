from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExpertRule, ExpertRuleGlossaryLink, ExpertRuleMetricLink, ExpertRuleRevision


class ExpertRuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, rule_id: UUID, lock: bool = False) -> ExpertRule | None:
        statement = select(ExpertRule).where(ExpertRule.id == rule_id)
        return self.session.scalar(statement.with_for_update() if lock else statement)

    def list(self, connection_id: UUID) -> list[ExpertRule]:
        return list(self.session.scalars(
            select(ExpertRule).where(ExpertRule.connection_id == connection_id)
            .order_by(ExpertRule.name, ExpertRule.id)
        ))

    def find_name(self, connection_id: UUID, normalized_name: str) -> ExpertRule | None:
        return self.session.scalar(select(ExpertRule).where(
            ExpertRule.connection_id == connection_id, ExpertRule.normalized_name == normalized_name
        ))

    def revisions(self, rule_id: UUID) -> list[ExpertRuleRevision]:
        return list(self.session.scalars(
            select(ExpertRuleRevision).where(ExpertRuleRevision.rule_id == rule_id)
            .order_by(ExpertRuleRevision.number.desc())
        ))

    def glossary_links(self, revision_id: UUID) -> list[ExpertRuleGlossaryLink]:
        return list(self.session.scalars(
            select(ExpertRuleGlossaryLink).where(ExpertRuleGlossaryLink.revision_id == revision_id)
            .order_by(ExpertRuleGlossaryLink.term_id)
        ))

    def metric_links(self, revision_id: UUID) -> list[ExpertRuleMetricLink]:
        return list(self.session.scalars(
            select(ExpertRuleMetricLink).where(ExpertRuleMetricLink.revision_id == revision_id)
            .order_by(ExpertRuleMetricLink.metric_id)
        ))
