from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.modules.database_connection.models import DatabaseColumn

from ..common.errors import Text2SqlEntityNotFound, Text2SqlInvalidRequest
from ..models.query_dataset import MAX_SELECTED_COLUMNS, QueryDataset
from .join_schemas import JoinOption

MAX_LIST_LIMIT = 200

type ColumnIdList = list[UUID]
type DatasetList = list[QueryDataset]


@dataclass
class ColumnAddition:
    added: ColumnIdList = field(default_factory=list)
    warning: str | None = None


class DatasetStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self, connection_id: UUID, option: JoinOption) -> tuple[QueryDataset, bool]:
        existing = self._find(connection_id, option.signature, option.root_table_id)
        if existing is not None:
            return existing, False
        dataset = QueryDataset(
            connection_id=connection_id,
            signature=option.signature,
            root_table_id=option.root_table_id,
            table_ids=[str(table_id) for table_id in option.table_ids],
            edge_ids=[str(edge_id) for edge_id in option.edge_ids],
            from_sql=option.from_sql,
            selected_column_ids=[],
        )
        try:
            with self.session.begin_nested():
                self.session.add(dataset)
                self.session.flush()
        except IntegrityError:
            existing = self._find(connection_id, option.signature, option.root_table_id)
            if existing is None:
                raise
            return existing, False
        return dataset, True

    def add_columns(self, dataset: QueryDataset, column_ids: Sequence[UUID]) -> ColumnAddition:
        locked = self.session.scalar(
            select(QueryDataset)
            .where(QueryDataset.id == dataset.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise Text2SqlEntityNotFound()
        current = list(locked.selected_column_ids or [])
        known = set(current)
        requested: ColumnIdList = []
        for column_id in column_ids:
            if str(column_id) not in known:
                known.add(str(column_id))
                requested.append(column_id)
        if not requested:
            return ColumnAddition()
        self._check_columns_belong(locked, requested)
        if len(current) + len(requested) > MAX_SELECTED_COLUMNS:
            return ColumnAddition(warning=(
                f"Dataset đã đạt trần {MAX_SELECTED_COLUMNS} cột (hiện có {len(current)} cột) nên {len(requested)} "
                "cột mới của lần truy vấn này không được ghi thêm vào dataset; truy vấn vẫn chạy bình thường."
            ))
        locked.selected_column_ids = current + [str(column_id) for column_id in requested]
        self.session.flush()
        return ColumnAddition(requested)

    def get(self, connection_id: UUID, dataset_id: UUID) -> QueryDataset:
        dataset = self.session.scalar(
            select(QueryDataset).where(QueryDataset.connection_id == connection_id, QueryDataset.id == dataset_id)
        )
        if dataset is None:
            raise Text2SqlEntityNotFound()
        return dataset

    def list(self, connection_id: UUID, limit: int = 50) -> DatasetList:
        bounded = max(1, min(limit, MAX_LIST_LIMIT))
        statement = (
            select(QueryDataset)
            .where(QueryDataset.connection_id == connection_id)
            .order_by(QueryDataset.updated_at.desc(), QueryDataset.id.desc())
            .limit(bounded)
        )
        return [*self.session.scalars(statement)]

    def saved_signatures(self, connection_id: UUID, options: Sequence[JoinOption]) -> set[str]:
        if not options:
            return set()
        saved = self.session.scalars(select(QueryDataset).where(
            QueryDataset.connection_id == connection_id,
            QueryDataset.signature.in_([option.signature for option in options]),
        ))
        keys = {(item.signature, str(item.root_table_id), frozenset(item.table_ids or [])) for item in saved}
        return {
            option.signature for option in options
            if (option.signature, str(option.root_table_id), frozenset(str(item) for item in option.table_ids)) in keys
        }

    def _find(self, connection_id: UUID, signature: str, root_table_id: UUID) -> QueryDataset | None:
        return self.session.scalar(
            select(QueryDataset).where(
                QueryDataset.connection_id == connection_id,
                QueryDataset.signature == signature,
                QueryDataset.root_table_id == root_table_id,
            )
        )

    def _check_columns_belong(self, dataset: QueryDataset, column_ids: ColumnIdList) -> None:
        rows = self.session.execute(
            select(DatabaseColumn.id, DatabaseColumn.table_id).where(DatabaseColumn.id.in_(column_ids))
        ).all()
        table_by_column = {column_id: table_id for column_id, table_id in rows}
        allowed_tables = set(dataset.table_ids)
        invalid = [
            str(column_id) for column_id in column_ids
            if str(table_by_column.get(column_id, "")) not in allowed_tables
        ]
        if invalid:
            raise Text2SqlInvalidRequest(
                "Các cột sau không thuộc bảng nào của dataset hoặc không tồn tại: " + ", ".join(invalid) + "."
            )
