from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modules.data_dictionary.schemas.schema_data_dictionary import TableDictionaryOut
from backend.modules.data_dictionary.services import DataDictionaryService
from backend.modules.data_dictionary.utils.exceptions import DictionaryTableNotFoundError
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.models import GlossaryTerm
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.own_knowledge.services import OwnKnowledgeService

from ..common.errors import Text2SqlConnectionNotFound, Text2SqlEntityNotFound, Text2SqlInvalidRequest
from ..common.sql_columns import referenced_columns
from ..vector_store.ingestion.documents.context import CatalogContext, load_context
from ..vector_store.ingestion.documents.expert_rule import condition_text
from .schemas import (
    ColumnDescription,
    ColumnRef,
    ExpertRuleDetail,
    GlossaryTermDetail,
    LinkRef,
    MetricDetail,
    NamedRef,
    OwnKnowledgeDetail,
    RuleConditionDetail,
    RuleExampleDetail,
    RuleExceptionDetail,
    TableDescription,
    TableRef,
)


class DetailService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def tables(self, connection_id: UUID, table_ids: Sequence[UUID]) -> list[TableDescription]:
        descriptions = self._table_dictionaries(connection_id, table_ids)
        return [TableDescription(table=descriptions[table_id]) for table_id in table_ids if table_id in descriptions]

    def columns(self, connection_id: UUID, column_refs: Sequence[tuple[UUID, UUID]]) -> list[ColumnDescription]:
        descriptions = self._table_dictionaries(connection_id, [table_id for table_id, _ in column_refs])
        result: list[ColumnDescription] = []
        for table_id, column_id in column_refs:
            table = descriptions.get(table_id)
            column = next((item for item in table.columns if item.column_id == column_id), None) if table else None
            if table is not None and column is not None:
                result.append(ColumnDescription(
                    table=TableRef(
                        table_id=table.table_id, schema_name=table.schema_name, table_name=table.table_name,
                        display_name=table.display_name,
                    ),
                    column=column,
                ))
        return result

    def metric(self, connection_id: UUID, metric_id: UUID) -> MetricDetail:
        context = self._context(connection_id)
        metric = context.metrics_by_id.get(metric_id)
        if metric is None or metric.table_id is None or metric.source_sql:
            raise Text2SqlEntityNotFound()
        column_ids = referenced_columns(metric.expression, context.columns_by_table.get(metric.table_id, {}))
        return MetricDetail(
            metric_id=metric.id, name=metric.name, label=metric.label, description=metric.description,
            expression=metric.expression, format=metric.format, currency=metric.currency,
            metric_type=metric.metric_type, warning_text=metric.warning_text, origin=metric.origin,
            table=self._table_ref(context, metric.table_id),
            referenced_columns=[
                ColumnRef(
                    column_id=UUID(value), name=context.columns_by_id[UUID(value)].column.name,
                    display_name=context.columns_by_id[UUID(value)].label,
                )
                for value in column_ids
            ],
        )

    def glossary_term(self, connection_id: UUID, term_id: UUID) -> GlossaryTermDetail:
        context = self._context(connection_id)
        term = self.session.get(GlossaryTerm, term_id)
        if term is None or term.connection_id != connection_id:
            raise Text2SqlEntityNotFound()
        service = GlossaryService(self.session)
        serving = service.serving_revision(term_id)
        if serving is None:
            raise Text2SqlEntityNotFound()
        links = [
            link for link in (
                self._link_ref(context, item["kind"], UUID(item["id"]))
                for item in service.live_links(connection_id, serving.id)
            ) if link is not None
        ]
        return GlossaryTermDetail(
            term_id=term.id, name=term.canonical_name, group_name=term.group_name, revision_number=serving.number,
            definition=serving.definition, synonyms=list(serving.synonyms), links=links,
        )

    def expert_rule(self, connection_id: UUID, rule_id: UUID) -> ExpertRuleDetail:
        context = self._context(connection_id)
        rule = next(
            (item for item in ExpertRuleService(self.session).discovery(connection_id) if item["id"] == rule_id), None
        )
        if rule is None:
            raise Text2SqlEntityNotFound()
        term_ids = list(rule["glossary_term_ids"])
        term_names = {
            term.id: term.canonical_name
            for term in self.session.scalars(select(GlossaryTerm).where(GlossaryTerm.id.in_(term_ids)))
        } if term_ids else {}
        return ExpertRuleDetail(
            rule_id=rule["id"], name=rule["name"], group_name=rule["group_name"],
            table=self._table_ref(context, rule["table_id"]) if rule["table_id"] in context.tables else None,
            description=rule["description"],
            conditions=[
                RuleConditionDetail(
                    column_id=UUID(condition["column_id"]),
                    column_name=context.column_label(UUID(condition["column_id"])),
                    operator=condition["operator"], value_type=condition["value_type"],
                    value=condition.get("value"), text=condition_text(context, condition),
                )
                for condition in rule["conditions"]
            ],
            exceptions=[RuleExceptionDetail(**item) for item in rule["exceptions"]],
            examples=[RuleExampleDetail(**item) for item in rule["examples"]],
            glossary_terms=[
                NamedRef(id=term_id, name=term_names[term_id]) for term_id in term_ids if term_id in term_names
            ],
            metrics=[
                NamedRef(id=metric_id, name=label)
                for metric_id in rule["metric_ids"] if (label := context.metric_label(metric_id))
            ],
        )

    def own_entry(self, connection_id: UUID, user_id: str, entry_id: UUID) -> OwnKnowledgeDetail:
        if not user_id or not user_id.strip():
            raise Text2SqlInvalidRequest("Cần user_id để xem tri thức riêng.")
        context = self._context(connection_id)
        entry = next(
            (item for item in OwnKnowledgeService(self.session).agent_entries(connection_id, user_id.strip())
             if item["id"] == entry_id),
            None,
        )
        if entry is None:
            raise Text2SqlEntityNotFound()
        return OwnKnowledgeDetail(
            entry_id=entry["id"], name=entry["name"], kind=entry["kind"], concept=entry["concept"],
            definition=entry["definition"],
            table=self._table_ref(context, entry["table_id"]) if entry["table_id"] in context.tables else None,
            review_status=entry["review_status"], version=entry["version"], updated_at=entry["updated_at"],
        )

    def _context(self, connection_id: UUID) -> CatalogContext:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        return load_context(self.session, connection_id)

    def _table_dictionaries(
        self, connection_id: UUID, table_ids: Sequence[UUID]
    ) -> dict[UUID, TableDictionaryOut]:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        service = DataDictionaryService(self.session)
        result: dict[UUID, TableDictionaryOut] = {}
        for table_id in dict.fromkeys(table_ids):
            try:
                description = service.get_table_dictionary(table_id)
            except DictionaryTableNotFoundError:
                continue
            if description["connection_id"] == connection_id:
                result[table_id] = TableDictionaryOut.model_validate(description)
        return result

    @staticmethod
    def _table_ref(context: CatalogContext, table_id: UUID) -> TableRef:
        entry = context.tables[table_id]
        return TableRef(
            table_id=table_id, schema_name=entry.schema.name, table_name=entry.table.name, display_name=entry.label,
        )

    def _link_ref(self, context: CatalogContext, kind: str, target_id: UUID) -> LinkRef | None:
        if kind == "table" and target_id in context.tables:
            ref = self._table_ref(context, target_id)
            return LinkRef(kind=kind, id=target_id, name=ref.display_name, table=ref)
        if kind == "column" and target_id in context.columns_by_id:
            column = context.columns_by_id[target_id]
            return LinkRef(
                kind=kind, id=target_id, name=column.label, table=self._table_ref(context, column.column.table_id)
            )
        if kind == "metric" and (label := context.metric_label(target_id)):
            metric = context.metrics_by_id[target_id]
            return LinkRef(
                kind=kind, id=target_id, name=label,
                table=self._table_ref(context, metric.table_id) if metric.table_id in context.tables else None,
            )
        return None

