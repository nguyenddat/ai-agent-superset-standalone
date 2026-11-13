from sqlalchemy.orm import Session

from ..models import TableColumnRole
from .repo_child import ChildRepository


class TableColumnRoleRepository(ChildRepository[TableColumnRole]):
    parent_key = "table_dictionary_id"

    def __init__(self, session: Session) -> None:
        super().__init__(session, TableColumnRole)
