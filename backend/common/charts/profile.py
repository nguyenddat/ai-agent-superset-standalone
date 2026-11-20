import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .spec import ChartField

EMPTY_LABEL = "(Trống)"
NON_FINITE = frozenset({"nan", "-nan", "infinity", "-infinity", "+infinity", "inf", "-inf", "+inf"})
PLAIN_WORDS = frozenset({"nam", "year", "id", "ma", "code", "key"})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
CATEGORY_TYPES = frozenset({"text", "boolean", "other"})
TEMPORAL_TYPES = frozenset({"date", "datetime"})


def folded(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value).casefold().replace("đ", "d"))
    return " ".join("".join(char for char in text if unicodedata.category(char) != "Mn").split())


def humanize(alias: str) -> str:
    words = " ".join(str(alias).replace("_", " ").split())
    return words[:1].upper() + words[1:] if words else str(alias)


def is_plain_name(*names: str | None) -> bool:
    for name in names:
        if not name:
            continue
        tokens = [token for token in re.split(r"[_\s]+", folded(name)) if token]
        if any(token in PLAIN_WORDS for token in tokens) or "so_hieu" in "_".join(tokens):
            return True
    return False


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def number(value: Any) -> float | None:
    return float(value) if is_number(value) else None


def is_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    return isinstance(value, str) and value.strip().lower() in NON_FINITE


def category_key(value: Any) -> str:
    if value is None:
        return EMPTY_LABEL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    return str(value)


def temporal_key(value: Any) -> str | None:
    return value if isinstance(value, str) and ISO_DATE.match(value[:10]) else None


def field_kinds(field: ChartField) -> frozenset[str]:
    if field.type in TEMPORAL_TYPES:
        return frozenset({"T"})
    if field.type == "number":
        return frozenset({"N", "C"}) if field.role == "dimension" else frozenset({"N"})
    return frozenset({"C"})


def _json_type(values: list[Any]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return "other"
    if all(isinstance(value, bool) for value in present):
        return "boolean"
    if all(is_number(value) or is_non_finite(value) for value in present) and any(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in present
    ):
        return "number"
    if all(isinstance(value, str) and ISO_DATE.match(value) for value in present):
        return "date"
    if all(isinstance(value, str) and (ISO_DATE.match(value) or ISO_DATETIME.match(value)) for value in present):
        if all(_midnight(value) for value in present):
            return "date"
        return "datetime"
    return "text"


def _midnight(value: str) -> bool:
    if ISO_DATE.match(value):
        return True
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (parsed.hour, parsed.minute, parsed.second, parsed.microsecond) == (0, 0, 0, 0)


def infer_fields(columns: list[str], rows: list[list[Any]]) -> list[ChartField]:
    fields = []
    for index, name in enumerate(columns):
        values = [row[index] if isinstance(row, (list, tuple)) and index < len(row) else None for row in rows]
        kind = _json_type(values)
        plain = kind == "number" and is_plain_name(name)
        fields.append(ChartField(
            name=name, label=humanize(name), type=kind, format_hint="plain" if plain else None,
            role="measure" if kind == "number" and not plain else "dimension",
        ))
    return fields


@dataclass(frozen=True)
class ColumnProfile:
    field: ChartField
    distinct: int
    has_negative: bool
    has_positive: bool
    non_null: int


@dataclass(frozen=True)
class ResultProfile:
    columns: tuple[ColumnProfile, ...]
    row_count: int

    def by_kind(self, kind: str) -> list[ColumnProfile]:
        if kind == "N":
            return [item for item in self.columns if item.field.type == "number" and item.field.role == "measure"]
        if kind == "T":
            return [item for item in self.columns if item.field.type in TEMPORAL_TYPES]
        return [
            item for item in self.columns
            if item.field.type in CATEGORY_TYPES or (item.field.type == "number" and item.field.role == "dimension")
        ]


def profile(fields: list[ChartField], rows: list[list[Any]]) -> ResultProfile:
    columns = []
    for index, field in enumerate(fields):
        values = [row[index] for row in rows if isinstance(row, (list, tuple)) and index < len(row)]
        numbers = [value for value in values if is_number(value)]
        columns.append(ColumnProfile(
            field=field, distinct=len({category_key(value) for value in values}),
            has_negative=any(value < 0 for value in numbers), has_positive=any(value > 0 for value in numbers),
            non_null=sum(value is not None and not is_non_finite(value) for value in values),
        ))
    return ResultProfile(tuple(columns), len(rows))
