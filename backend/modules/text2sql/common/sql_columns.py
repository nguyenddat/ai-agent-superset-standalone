from uuid import UUID

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError


def referenced_columns(expression: str, columns_by_name: dict[str, UUID]) -> list[str]:
    try:
        parsed = parse_one(expression, read="postgres")
    except SqlglotError:
        return []
    if parsed is None:
        return []
    identifiers = {column.name.lower() for column in parsed.find_all(exp.Column)}
    return sorted(str(columns_by_name[name]) for name in identifiers if name in columns_by_name)
