from uuid import UUID

from sqlalchemy.orm import Session

from backend.modules.database_connection.models import DatabaseConnection

from ..common.errors import Text2SqlConnectionNotFound
from ..vector_store.ingestion.documents.context import load_context
from .join_graph import JoinGraph
from .join_schemas import JoinPlan


class JoinService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def plan(
        self, connection_id: UUID, table_ids: list[UUID], via: list[UUID] | None = None, root: UUID | None = None,
    ) -> JoinPlan:
        if self.session.get(DatabaseConnection, connection_id) is None:
            raise Text2SqlConnectionNotFound()
        context = load_context(self.session, connection_id)
        return JoinGraph(context).plan(table_ids, via, root)
