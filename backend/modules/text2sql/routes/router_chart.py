from typing import Any

from fastapi import APIRouter

from backend.common.charts import ChartField, ChartSpecError, chart_catalog, compatible_types, validate_chart
from backend.core.setting import config

from ..schemas import ChartValidateIn, ChartValidateOut
from ..utils.exceptions import Text2SqlChartInvalid

router = APIRouter()


@router.get("/chart-types")
def chart_types() -> dict[str, Any]:
    return chart_catalog(config.text2sql_chart_types)


@router.post("/charts/validate", response_model=ChartValidateOut)
def validate(body: ChartValidateIn) -> dict[str, Any]:
    fields = [ChartField.model_validate(item.model_dump()) for item in body.fields]
    enabled = config.text2sql_chart_types
    try:
        checked = validate_chart(body.chart, fields, body.rows, rows_complete=body.rows_complete, enabled=enabled)
    except ChartSpecError as error:
        raise Text2SqlChartInvalid("\n".join(error.errors)) from None
    return {
        "chart": checked.json(), "warnings": checked.warnings,
        "chart_types": compatible_types(fields, body.rows, enabled=enabled, rows_complete=body.rows_complete),
    }
