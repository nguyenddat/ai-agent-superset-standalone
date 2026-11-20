from typing import Any

from backend.common.charts import ChartField, compatible_types, infer_fields
from backend.core.setting import config

COLUMN_VALUES = "column_values"


def result_fields(item: dict[str, Any]) -> list[ChartField]:
    stored = item.get("fields")
    if isinstance(stored, list) and stored:
        try:
            return [
                ChartField.model_validate({
                    key: value for key, value in field.items() if key in ChartField.model_fields
                })
                for field in stored if isinstance(field, dict)
            ]
        except ValueError:
            pass
    columns = item.get("columns") if isinstance(item.get("columns"), list) else []
    rows = item.get("rows") if isinstance(item.get("rows"), list) else []
    return infer_fields([str(name) for name in columns], rows)


def rows_complete(item: dict[str, Any]) -> bool:
    return not (item.get("stored_truncated") or item.get("truncated"))


def normalize_results(results: list[Any] | None) -> list[Any] | None:
    if not isinstance(results, list):
        return results
    counters: dict[Any, int] = {}
    normalized: list[Any] = []
    for item in results:
        if not isinstance(item, dict) or item.get("kind") == COLUMN_VALUES:
            normalized.append(item)
            continue
        position = item.get("position", 1)
        counters[position] = counters.get(position, 0) + 1
        if item.get("result_id"):
            normalized.append(item)
            continue
        fields = result_fields(item)
        rows = item.get("rows") if isinstance(item.get("rows"), list) else []
        normalized.append({
            **item, "result_id": f"{position}-{counters[position]}",
            "fields": [field.model_dump() for field in fields],
            "chart_types": compatible_types(
                fields, rows, enabled=config.text2sql_chart_types, rows_complete=rows_complete(item),
            ),
            "chart": None, "chart_source": None, "display": "none",
        })
    return normalized
