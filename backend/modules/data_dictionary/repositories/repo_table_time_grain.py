from sqlalchemy.orm import Session

from ..models import TableTimeGrain
from .repo_child import ChildRepository


class TableTimeGrainRepository(ChildRepository[TableTimeGrain]):
    parent_key = "table_dictionary_id"

    def __init__(self, session: Session) -> None:
        super().__init__(session, TableTimeGrain)
