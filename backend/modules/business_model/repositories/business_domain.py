from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository
from backend.modules.data_dictionary.models import TableDictionary
from backend.modules.database_connection.models import DatabaseSchema, DatabaseTable

from ..models import BusinessDomain, business_domain_tables


class BusinessDomainRepository(BaseRepository[BusinessDomain]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessDomain)

    def read_ordered(self) -> list[BusinessDomain]:
        return list(self.session.scalars(select(self.model).order_by(self.model.name)).all())

    def read_by_name(self, name: str) -> BusinessDomain | None:
        return self.session.scalar(select(self.model).where(func.lower(self.model.name) == name.lower()))

    def memberships(self, connection_id: UUID | None = None) -> dict[UUID, list[UUID]]:
        statement = select(business_domain_tables.c.domain_id, TableDictionary.table_id).join(
            TableDictionary, business_domain_tables.c.table_dictionary_id == TableDictionary.id
        )
        if connection_id is not None:
            statement = statement.join(DatabaseTable, DatabaseTable.id == TableDictionary.table_id).join(
                DatabaseSchema, DatabaseSchema.id == DatabaseTable.schema_id
            ).where(DatabaseSchema.connection_id == connection_id)
        result: dict[UUID, list[UUID]] = {}
        for domain_id, table_id in self.session.execute(statement):
            result.setdefault(domain_id, []).append(table_id)
        return result

    def replace_memberships(self, domain_id: UUID, dictionary_ids: Collection[UUID]) -> None:
        self.session.execute(delete(business_domain_tables).where(business_domain_tables.c.domain_id == domain_id))
        if dictionary_ids:
            self.session.execute(insert(business_domain_tables), [
                {"domain_id": domain_id, "table_dictionary_id": dictionary_id} for dictionary_id in dictionary_ids
            ])
