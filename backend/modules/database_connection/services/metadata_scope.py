from fnmatch import fnmatchcase
from typing import Any

from ..utils.exceptions import InvalidConnectionError

SCOPE_FIELDS = ("schema_includes", "schema_excludes", "table_includes", "table_excludes")
MAX_PATTERNS = 100
MAX_PATTERN_LENGTH = 255


def checked_patterns(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_PATTERNS:
        raise InvalidConnectionError()
    patterns = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > MAX_PATTERN_LENGTH:
            raise InvalidConnectionError()
        pattern = item.strip()
        if pattern not in patterns:
            patterns.append(pattern)
    return patterns


def _selected(name: str, includes: list[str], excludes: list[str]) -> bool:
    return (not includes or any(fnmatchcase(name, pattern) for pattern in includes)) and not any(
        fnmatchcase(name, pattern) for pattern in excludes
    )


class MetadataScope:
    def __init__(self, connection: Any) -> None:
        self.schema_includes = connection.schema_includes or []
        self.schema_excludes = connection.schema_excludes or []
        self.table_includes = connection.table_includes or []
        self.table_excludes = connection.table_excludes or []

    def schema(self, name: str) -> bool:
        return _selected(name, self.schema_includes, self.schema_excludes)

    def table(self, schema_name: str, table_name: str) -> bool:
        qualified = f"{schema_name}.{table_name}"
        included = not self.table_includes or any(
            fnmatchcase(candidate, pattern)
            for pattern in self.table_includes
            for candidate in (table_name, qualified)
        )
        excluded = any(
            fnmatchcase(candidate, pattern)
            for pattern in self.table_excludes
            for candidate in (table_name, qualified)
        )
        return included and not excluded
