from sqlalchemy.orm import Session

from ..models import IndicatorAggregation
from .repo_child import ChildRepository


class IndicatorAggregationRepository(ChildRepository[IndicatorAggregation]):
    parent_key = "table_dictionary_id"

    def __init__(self, session: Session) -> None:
        super().__init__(session, IndicatorAggregation)
