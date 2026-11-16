from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlglot import exp

from backend.modules.database_connection.models import DatabaseColumn, DatabaseTable

from .expression import parse_dataset_expression
from .join_schemas import JoinOption
from .schemas import DatasetQueryPlan

type ColumnKey = tuple[str, str]


def _expression_columns(text: str) -> list[ColumnKey]:
    found: list[ColumnKey] = []

    def record(table: str, column: str) -> exp.Column:
        found.append((table.lower(), column.lower()))
        return exp.column(column, table)

    parse_dataset_expression(text, record)
    return found


def _columns_by_name(session: Session, join: JoinOption) -> dict[ColumnKey, UUID]:
    rows = session.execute(
        select(DatabaseColumn.id, DatabaseTable.name, DatabaseColumn.name)
        .join(DatabaseTable, DatabaseTable.id == DatabaseColumn.table_id)
        .where(DatabaseColumn.table_id.in_(join.table_ids))
    ).all()
    return {(table.lower(), column.lower()): column_id for column_id, table, column in rows}


def dataset_column_ids(session: Session, join: JoinOption, plan: DatasetQueryPlan) -> list[UUID]:
    wanted: list[UUID | ColumnKey] = []
    for item in plan.select:
        if item.column_id is not None:
            wanted.append(item.column_id)
        elif item.expression is not None:
            wanted.extend(_expression_columns(item.expression))
    wanted.extend(plan.group_by)
    if plan.time is not None and plan.time.granularity is not None:
        wanted.append(plan.time.column_id)
    by_name = _columns_by_name(session, join) if any(isinstance(item, tuple) for item in wanted) else {}
    resolved = [by_name.get(item) if isinstance(item, tuple) else item for item in wanted]
    return list(dict.fromkeys(item for item in resolved if item is not None))
