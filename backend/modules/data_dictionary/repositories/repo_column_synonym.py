from sqlalchemy.orm import Session

from ..models import ColumnSynonym
from .repo_child import ChildRepository


class ColumnSynonymRepository(ChildRepository[ColumnSynonym]):
    parent_key = "column_dictionary_id"

    def __init__(self, session: Session) -> None:
        super().__init__(session, ColumnSynonym)
