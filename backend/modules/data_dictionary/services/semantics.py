import re

TABLE_KINDS = ("base", "aggregate")
LAYOUTS = ("wide", "indicator_values", "indicator_catalog")

COMMON_ROLES = ("time", "created_at", "row_kind")
CATALOG_ROLES = (
    "catalog_key", "catalog_code", "catalog_name", "catalog_unit", "catalog_value_kind", "catalog_aggregation",
)
LAYOUT_ROLES = {
    "wide": COMMON_ROLES,
    "indicator_values": (*COMMON_ROLES, "indicator_key", "value"),
    "indicator_catalog": (*COMMON_ROLES, *CATALOG_ROLES),
}
REQUIRED_ROLES = {
    "wide": (),
    "indicator_values": ("indicator_key", "value"),
    "indicator_catalog": ("catalog_key", "catalog_code", "catalog_name"),
}
VALUE_KINDS = ("number", "boolean", "text")

TIME_GRAINS = ("instant", "hour", "day", "week", "month", "quarter", "year")
INDICATOR_AGGREGATIONS = ("SUM", "AVG", "MIN", "MAX", "COUNT", "NONE")
MAX_INDICATOR_CODES = 20

SEMANTIC_ROLES = ("key", "measure", "dimension", "label", "time", "row_kind", "attribute")
TEMPORAL_KINDS = ("date", "timestamp")
COLUMN_AGGREGATIONS = ("SUM", "AVG", "MIN", "MAX", "COUNT", "COUNT_DISTINCT")
MAX_SYNONYMS = 20
MAX_SYNONYM_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 2000

NUMBER_TYPE = re.compile(r"\b((SMALL|BIG)?INT(EGER|2|4|8)?|NUMERIC|DECIMAL|REAL|FLOAT\d*|DOUBLE|MONEY)\b")
KEY_NAME = re.compile(r"(^|_)(id|key)$", re.IGNORECASE)


def looks_like_key(column_name: str) -> bool:
    return bool(KEY_NAME.search(column_name))


def default_temporal_kind(data_type: str) -> str | None:
    upper = data_type.upper()
    if "TIMESTAMP" in upper or "DATETIME" in upper:
        return "timestamp"
    if upper.strip() == "DATE":
        return "date"
    return None


def default_semantic_role(data_type: str, temporal_kind: str | None, is_key: bool, is_row_kind: bool) -> str:
    if is_key:
        return "key"
    if is_row_kind:
        return "row_kind"
    if temporal_kind:
        return "time"
    if NUMBER_TYPE.search(data_type.upper()):
        return "measure"
    return "dimension"
