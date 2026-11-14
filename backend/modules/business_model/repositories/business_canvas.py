from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.common.base_repository import BaseRepository

from ..models import BusinessCanvas


class BusinessCanvasRepository(BaseRepository[BusinessCanvas]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessCanvas)

    def read_by_connection_id(self, connection_id: UUID) -> BusinessCanvas | None:
        return self.session.scalar(select(self.model).where(self.model.connection_id == connection_id))
