import math
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

type Scalar = str | int | float | bool | Decimal | UUID | date | datetime | None
type JsonScalar = str | int | float | bool | None


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


def iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return utc_datetime(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("timestamp must be ISO 8601") from error
    return utc_datetime(parsed)


def iso_date(value: date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise TypeError("iso_date expects a date, not a datetime")
    return value.isoformat()


def format_scalar(value: Scalar) -> JsonScalar:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not valid JSON values")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimals are not valid JSON values")
        return format(value, "f")
    if isinstance(value, datetime):
        return iso_datetime(value)
    if isinstance(value, date):
        return iso_date(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported scalar type: {type(value).__name__}")
