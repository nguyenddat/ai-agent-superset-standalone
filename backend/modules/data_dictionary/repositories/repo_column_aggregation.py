from sqlalchemy.orm import Session

from ..models import ColumnAggregation
from .repo_child import ChildRepository


class ColumnAggregationRepository(ChildRepository[ColumnAggregation]):
    parent_key = "column_dictionary_id"

    def __init__(self, session: Session) -> None:
        super().__init__(session, ColumnAggregation)
