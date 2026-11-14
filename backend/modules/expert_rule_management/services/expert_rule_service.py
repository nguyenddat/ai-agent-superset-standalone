import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_model import utc_now
from backend.modules.database_connection.models import DatabaseColumn, DatabaseConnection, DatabaseSchema, DatabaseTable
from backend.modules.glossary_management.models import GlossaryTerm
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric

from ..models import ExpertRule, ExpertRuleGlossaryLink, ExpertRuleMetricLink, ExpertRuleRevision
from ..repositories import ExpertRuleRepository
from ..utils.exceptions import ExpertRuleConflictError, ExpertRuleNotFoundError, ExpertRuleValidationError


class ExpertRuleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ExpertRuleRepository(session)
        self.glossary = GlossaryService(session)

    def list_rules(self, connection_id: UUID) -> list[dict[str, Any]]:
        self._connection(connection_id)
        return [self._serialize(rule) for rule in self.repository.list(connection_id)]

    def get_rule(self, rule_id: UUID) -> dict[str, Any]:
        return self._serialize(self._rule(rule_id))

    def list_revisions(self, rule_id: UUID) -> list[dict[str, Any]]:
        rule = self._rule(rule_id)
        return [self._revision(revision) for revision in self.repository.revisions(rule.id)]

    def create_rule(self, values: dict[str, Any]) -> dict[str, Any]:
        connection_id = values["connection_id"]
        table_id = values["table_id"]
        self._connection(connection_id)
        self._table(connection_id, table_id)
        name = " ".join(values["name"].split())
        if not name or self.repository.find_name(connection_id, name.casefold()):
            raise ExpertRuleConflictError("Tên expert rule đã tồn tại trong kết nối này.")
        content = self._content(values, connection_id, table_id)
        rule = ExpertRule(
            connection_id=connection_id, table_id=table_id, name=name,
            normalized_name=name.casefold(), group_name=self._group(values.get("group_name")),
        )
        self.session.add(rule)
        self.session.flush()
        self._add_revision(rule.id, 1, content)
        return self._serialize(rule)

    def update_rule(self, rule_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        rule = self._rule(rule_id, lock=True)
        current = self.repository.revisions(rule.id)[0]
        self._expected(current, values["expected_revision"])
        content = self._content(values, rule.connection_id, rule.table_id)
        group = self._group(values.get("group_name"))
        same = (
            current.description == content["description"]
            and current.conditions == content["conditions"]
            and current.exceptions == content["exceptions"]
            and current.examples == content["examples"]
            and self._glossary_targets(current.id) == content["glossary"]
            and self._metric_targets(current.id) == content["metrics"]
        )
        if same and current.status != "revoked":
            if rule.group_name != group:
                rule.group_name = group
                rule.updated_at = utc_now()
                self.session.flush()
            return self._serialize(rule)
        rule.group_name = group
        rule.updated_at = utc_now()
        self._add_revision(rule.id, current.number + 1, content)
        return self._serialize(rule)

    def approve(self, rule_id: UUID, expected_revision: int) -> dict[str, Any]:
        rule = self._rule(rule_id, lock=True)
        current = self.repository.revisions(rule.id)[0]
        self._expected(current, expected_revision)
        if current.status != "draft":
            raise ExpertRuleConflictError("Chỉ có thể duyệt bản nháp hiện tại.")
        if not self._revision_is_live(rule, current):
            raise ExpertRuleConflictError("Liên kết hoặc điều kiện đã thay đổi; hãy sửa bản nháp trước khi duyệt.")
        current.status = "approved"
        rule.updated_at = utc_now()
        self.session.flush()
        return self._serialize(rule)

    def revoke(self, rule_id: UUID, expected_revision: int) -> dict[str, Any]:
        rule = self._rule(rule_id, lock=True)
        revisions = self.repository.revisions(rule.id)
        self._expected(revisions[0], expected_revision)
        serving = self._serving(revisions)
        if serving is None:
            raise ExpertRuleConflictError("Expert rule chưa có bản được duyệt để thu hồi.")
        content = {
            "description": serving.description, "conditions": serving.conditions,
            "exceptions": serving.exceptions, "examples": serving.examples,
            "glossary": [
                (link.term_id, link.glossary_revision_id) for link in self.repository.glossary_links(serving.id)
            ],
            "metrics": [(link.metric_id, link.fingerprint) for link in self.repository.metric_links(serving.id)],
        }
        rule.updated_at = utc_now()
        self._add_revision(rule.id, revisions[0].number + 1, content, status="revoked")
        return self._serialize(rule)

    def delete_rule(self, rule_id: UUID) -> None:
        self.session.delete(self._rule(rule_id, lock=True))
        self.session.flush()

    def discovery(self, connection_id: UUID) -> list[dict[str, Any]]:
        self._connection(connection_id)
        result = []
        for rule in self.repository.list(connection_id):
            serving = self._serving(self.repository.revisions(rule.id))
            if serving is None or not self._revision_is_live(rule, serving):
                continue
            result.append({
                "id": rule.id, "table_id": rule.table_id, "name": rule.name, "group_name": rule.group_name,
                "description": serving.description, "conditions": serving.conditions,
                "exceptions": serving.exceptions, "examples": serving.examples,
                "glossary_term_ids": self._glossary_ids(serving.id), "metric_ids": self._metric_ids(serving.id),
            })
        return result

    def options(self, connection_id: UUID) -> list[dict[str, Any]]:
        self._connection(connection_id)
        tables = list(self.session.scalars(
            select(DatabaseTable).join(DatabaseSchema).where(DatabaseSchema.connection_id == connection_id)
            .order_by(DatabaseTable.name)
        ))
        result = []
        for table in tables:
            columns = list(self.session.scalars(
                select(DatabaseColumn).where(DatabaseColumn.table_id == table.id)
                .order_by(DatabaseColumn.ordinal_position)
            ))
            metrics = list(self.session.scalars(
                select(Metric).where(Metric.table_id == table.id, Metric.is_active.is_(True)).order_by(Metric.name)
            ))
            terms = []
            for term in self.glossary.repository.list(connection_id):
                serving = self.glossary.serving_revision(term.id)
                if serving and self._term_matches_table(connection_id, table.id, serving.id):
                    terms.append({"id": term.id, "name": term.canonical_name})
            result.append({
                "table_id": table.id, "name": table.name,
                "columns": [
                    {"id": column.id, "name": column.name, "data_type": column.data_type} for column in columns
                ],
                "glossary_terms": terms, "metrics": [{"id": metric.id, "name": metric.name} for metric in metrics],
            })
        return result

    def _content(self, values: dict[str, Any], connection_id: UUID, table_id: UUID) -> dict[str, Any]:
        conditions = [item if isinstance(item, dict) else item.model_dump() for item in values["conditions"]]
        for condition in conditions:
            column = self.session.get(DatabaseColumn, condition["column_id"])
            if column is None or column.table_id != table_id:
                raise ExpertRuleValidationError("Cột điều kiện không thuộc bảng của expert rule.")
            condition["column_id"] = str(condition["column_id"])
        glossary_ids = values["glossary_term_ids"]
        metric_ids = values["metric_ids"]
        if len(set(glossary_ids)) != len(glossary_ids) or len(set(metric_ids)) != len(metric_ids):
            raise ExpertRuleValidationError("Liên kết glossary hoặc metric bị trùng.")
        glossary = []
        for term_id in sorted(glossary_ids):
            term = self.session.get(GlossaryTerm, term_id)
            if term is None or term.connection_id != connection_id:
                raise ExpertRuleValidationError("Thuật ngữ không thuộc kết nối đang chọn.")
            serving = self.glossary.serving_revision(term_id)
            if serving is None or not self._term_matches_table(connection_id, table_id, serving.id):
                raise ExpertRuleValidationError("Thuật ngữ cần bản đã duyệt liên kết tới bảng của rule.")
            glossary.append((term_id, serving.id))
        metrics = []
        for metric_id in sorted(metric_ids):
            metric = self.session.get(Metric, metric_id)
            if metric is None or not metric.is_active or metric.table_id != table_id:
                raise ExpertRuleValidationError("Metric không thuộc bảng hoặc không còn hoạt động.")
            metrics.append((metric_id, self._metric_fingerprint(metric)))
        return {
            "description": values["description"].strip() or None if values["description"] else None,
            "conditions": conditions,
            "exceptions": [item if isinstance(item, dict) else item.model_dump() for item in values["exceptions"]],
            "examples": [item if isinstance(item, dict) else item.model_dump() for item in values["examples"]],
            "glossary": glossary, "metrics": metrics,
        }

    def _add_revision(self, rule_id: UUID, number: int, content: dict[str, Any], status: str = "draft") -> None:
        revision = ExpertRuleRevision(
            rule_id=rule_id, number=number, description=content["description"],
            conditions=content["conditions"], exceptions=content["exceptions"],
            examples=content["examples"], status=status,
        )
        self.session.add(revision)
        self.session.flush()
        for term_id, glossary_revision_id in content["glossary"]:
            self.session.add(ExpertRuleGlossaryLink(
                revision_id=revision.id, term_id=term_id, glossary_revision_id=glossary_revision_id,
            ))
        for metric_id, fingerprint in content["metrics"]:
            self.session.add(ExpertRuleMetricLink(
                revision_id=revision.id, metric_id=metric_id, fingerprint=fingerprint,
            ))
        self.session.flush()

    def _revision_is_live(self, rule: ExpertRule, revision: ExpertRuleRevision) -> bool:
        try:
            self._table(rule.connection_id, rule.table_id)
            for condition in revision.conditions:
                column = self.session.get(DatabaseColumn, UUID(condition["column_id"]))
                if column is None or column.table_id != rule.table_id:
                    return False
            glossary_links = self.repository.glossary_links(revision.id)
            if not glossary_links:
                return False
            for link in glossary_links:
                term = self.session.get(GlossaryTerm, link.term_id)
                if term is None or term.connection_id != rule.connection_id:
                    return False
                serving = self.glossary.serving_revision(link.term_id)
                if serving is None or serving.id != link.glossary_revision_id:
                    return False
                if not self._term_matches_table(rule.connection_id, rule.table_id, serving.id):
                    return False
            for link in self.repository.metric_links(revision.id):
                metric = self.session.get(Metric, link.metric_id)
                if metric is None or not metric.is_active or metric.table_id != rule.table_id:
                    return False
                if self._metric_fingerprint(metric) != link.fingerprint:
                    return False
            return True
        except (ExpertRuleValidationError, ValueError):
            return False

    def _term_matches_table(self, connection_id: UUID, table_id: UUID, revision_id: UUID) -> bool:
        for link in self.glossary.live_links(connection_id, revision_id):
            object_id = UUID(link["id"])
            if link["kind"] == "table" and object_id == table_id:
                return True
            if link["kind"] == "column":
                column = self.session.get(DatabaseColumn, object_id)
                if column is not None and column.table_id == table_id:
                    return True
            if link["kind"] == "metric":
                metric = self.session.get(Metric, object_id)
                if metric is not None and metric.table_id == table_id:
                    return True
        return False

    @staticmethod
    def _metric_fingerprint(metric: Metric) -> str:
        value = [str(metric.table_id), metric.name, metric.expression, metric.description, metric.is_active]
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _glossary_ids(self, revision_id: UUID) -> list[UUID]:
        return [link.term_id for link in self.repository.glossary_links(revision_id)]

    def _metric_ids(self, revision_id: UUID) -> list[UUID]:
        return [link.metric_id for link in self.repository.metric_links(revision_id)]

    def _glossary_targets(self, revision_id: UUID) -> list[tuple[UUID, UUID]]:
        return [
            (link.term_id, link.glossary_revision_id) for link in self.repository.glossary_links(revision_id)
        ]

    def _metric_targets(self, revision_id: UUID) -> list[tuple[UUID, str]]:
        return [(link.metric_id, link.fingerprint) for link in self.repository.metric_links(revision_id)]

    def _connection(self, connection_id: UUID) -> None:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise ExpertRuleValidationError("Kết nối không tồn tại.")

    def _table(self, connection_id: UUID, table_id: UUID) -> None:
        owner = self.session.scalar(
            select(DatabaseSchema.connection_id).join(DatabaseTable, DatabaseTable.schema_id == DatabaseSchema.id)
            .where(DatabaseTable.id == table_id)
        )
        if owner != connection_id:
            raise ExpertRuleValidationError("Bảng không thuộc kết nối đang chọn.")

    def _rule(self, rule_id: UUID, lock: bool = False) -> ExpertRule:
        rule = self.repository.get(rule_id, lock)
        if rule is None:
            raise ExpertRuleNotFoundError()
        return rule

    @staticmethod
    def _group(value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None

    @staticmethod
    def _expected(current: ExpertRuleRevision, expected: int) -> None:
        if current.number != expected:
            raise ExpertRuleConflictError()

    @staticmethod
    def _serving(revisions: list[ExpertRuleRevision]) -> ExpertRuleRevision | None:
        for revision in revisions:
            if revision.status == "revoked":
                return None
            if revision.status == "approved":
                return revision
        return None

    def _revision(self, revision: ExpertRuleRevision) -> dict[str, Any]:
        return {
            "number": revision.number, "status": revision.status,
            "description": revision.description, "conditions": revision.conditions,
            "exceptions": revision.exceptions, "examples": revision.examples,
            "glossary_term_ids": self._glossary_ids(revision.id),
            "metric_ids": self._metric_ids(revision.id), "created_at": revision.created_at,
        }

    def _serialize(self, rule: ExpertRule) -> dict[str, Any]:
        revisions = self.repository.revisions(rule.id)
        serving = self._serving(revisions)
        return {
            "id": rule.id, "connection_id": rule.connection_id, "table_id": rule.table_id,
            "name": rule.name, "group_name": rule.group_name,
            "current": self._revision(revisions[0]), "serving": self._revision(serving) if serving else None,
            "is_discoverable": serving is not None and self._revision_is_live(rule, serving),
            "created_at": rule.created_at, "updated_at": rule.updated_at,
        }
