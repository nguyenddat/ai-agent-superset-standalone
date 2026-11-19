from collections.abc import Collection, Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import Table, delete, insert, select
from sqlalchemy.orm import Session

from ..models import BusinessDomain


# Domains of glossary terms, expert rules and metrics; each module owns a `(owner, domain_id)` join table.
class DomainAssignment:
    def __init__(self, session: Session, table: Table, owner_column: str) -> None:
        self.session = session
        self.table = table
        self.owner = table.c[owner_column]

    def unknown(self, domain_ids: Iterable[UUID]) -> list[UUID]:
        wanted = list(dict.fromkeys(domain_ids))
        if not wanted:
            return []
        found = set(self.session.scalars(select(BusinessDomain.id).where(BusinessDomain.id.in_(wanted))))
        return [domain_id for domain_id in wanted if domain_id not in found]

    def read(self, owner_ids: Collection[UUID]) -> dict[UUID, list[dict[str, Any]]]:
        if not owner_ids:
            return {}
        rows = self.session.execute(
            select(self.owner, BusinessDomain.id, BusinessDomain.name, BusinessDomain.color)
            .join(BusinessDomain, BusinessDomain.id == self.table.c.domain_id)
            .where(self.owner.in_(owner_ids))
            .order_by(BusinessDomain.name)
        )
        result: dict[UUID, list[dict[str, Any]]] = {}
        for owner_id, domain_id, name, color in rows:
            result.setdefault(owner_id, []).append({"id": domain_id, "name": name, "color": color})
        return result

    def read_one(self, owner_id: UUID) -> list[dict[str, Any]]:
        return self.read([owner_id]).get(owner_id, [])

    def ids(self, owner_id: UUID) -> set[UUID]:
        return set(self.session.scalars(select(self.table.c.domain_id).where(self.owner == owner_id)))

    def replace(self, owner_id: UUID, domain_ids: Iterable[UUID]) -> None:
        self.session.execute(delete(self.table).where(self.owner == owner_id))
        wanted = list(dict.fromkeys(domain_ids))
        if wanted:
            self.session.execute(insert(self.table), [
                {self.owner.name: owner_id, "domain_id": domain_id} for domain_id in wanted
            ])
