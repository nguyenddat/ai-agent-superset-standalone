from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Operator = Literal[
    "equals", "not_equals", "contains", "not_contains", "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal", "in", "not_in", "is_null", "is_not_null",
]
Granularity = Literal["day", "week", "month", "quarter", "year"]
Scalar = str | int | float | bool

MAX_GROUP_BY = 5
MAX_FILTERS = 10
MAX_ORDER_BY = 3
MAX_IN_VALUES = 50


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID = Field(description="ID cột (lấy từ search_tables hoặc search_columns).")
    operator: Operator
    value: Scalar | list[Scalar] | None = Field(
        default=None, description="Giá trị so sánh; danh sách cho in/not_in; bỏ trống cho is_null/is_not_null."
    )


class QueryTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID = Field(description="ID cột ngày hoặc ngày giờ.")
    start: date | datetime | None = Field(default=None, description="Từ thời điểm này (bao gồm).")
    end: date | datetime | None = Field(default=None, description="Đến thời điểm này (không bao gồm).")
    granularity: Granularity | None = Field(
        default=None, description="Nhóm kết quả theo ngày, tuần, tháng, quý hoặc năm."
    )


class QueryOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: str = Field(description='"metric", "time" hoặc ID một cột trong group_by.')
    direction: Literal["asc", "desc"] = "desc"


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: UUID
    group_by: list[UUID] = Field(default_factory=list, max_length=MAX_GROUP_BY)
    time: QueryTime | None = None
    filters: list[QueryFilter] = Field(default_factory=list, max_length=MAX_FILTERS)
    order_by: list[QueryOrder] = Field(default_factory=list, max_length=MAX_ORDER_BY)
    limit: int = Field(default=100, ge=1)


class ResultColumn(BaseModel):
    name: str
    role: Literal["dimension", "time", "metric"]
    column_id: UUID | None = None
    contains_pii: bool = False
    aggregation: str | None = Field(default=None, exclude=True)


class PiiReport(BaseModel):
    confirmation: Literal["not_required", "confirmed", "not_supported"] = "not_required"
    masked_columns: list[str] = Field(default_factory=list)
    detected: dict[str, int] = Field(default_factory=dict)
    warning: str | None = None


class QueryMetricInfo(BaseModel):
    metric_id: UUID
    name: str
    label: str | None
    format: str | None
    currency: str | None
    warning_text: str | None
    table: str


class QueryResult(BaseModel):
    metric: QueryMetricInfo
    columns: list[ResultColumn]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    limit: int
    sql: str
    parameters: dict[str, Any]
    pii: PiiReport
    elapsed_ms: int
    value_types: list[str | None] = Field(default_factory=list, exclude=True)
