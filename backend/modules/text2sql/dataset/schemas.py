from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..query.schemas import (
    MAX_FILTERS,
    MAX_GROUP_BY,
    MAX_ORDER_BY,
    PiiReport,
    QueryFilter,
    QueryOrder,
    QueryTime,
    ResultColumn,
)

Aggregation = Literal["sum", "avg", "min", "max", "count", "count_distinct"]
Placement = Literal["where", "join"]

MAX_SELECT = 20
MAX_ALIAS_LENGTH = 48


class SelectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID | None = Field(default=None, description="ID cột thuộc một trong các bảng của phương án nối.")
    expression: str | None = Field(
        default=None,
        description="Biểu thức SQL an toàn, cột viết dạng bang.cot (tên bảng không kèm schema), ví dụ "
        "SUM(orders.total) / NULLIF(COUNT(DISTINCT orders.customer_id), 0).",
    )
    aggregation: Aggregation | None = Field(default=None, description="Hàm tổng hợp áp dụng cho column_id.")
    alias: str | None = Field(default=None, description="Tên cột kết quả; chỉ giữ chữ, số và dấu gạch dưới.")

    @model_validator(mode="after")
    def _one_source(self) -> "SelectItem":
        if (self.column_id is None) == (self.expression is None):
            raise ValueError("Mỗi mục select cần đúng một trong column_id hoặc expression.")
        if self.expression is not None and self.aggregation is not None:
            raise ValueError("aggregation chỉ dùng với column_id; hãy viết hàm tổng hợp trong expression.")
        return self


class DatasetFilter(QueryFilter):
    placement: Placement = Field(
        default="where",
        description='"where" (mặc định) loại dòng không khớp; "join" đặt điều kiện vào ON của bước LEFT JOIN tới '
        "bảng chứa cột để giữ dòng của bảng gốc không khớp (chỉ cho cột của bảng không phải gốc).",
    )


class DatasetOrder(QueryOrder):
    by: str = Field(description='Alias một cột kết quả, "time" (khi có granularity) hoặc column_id một mục select.')


class DatasetQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    select: list[SelectItem] = Field(min_length=1, max_length=MAX_SELECT)
    group_by: list[UUID] = Field(default_factory=list, max_length=MAX_GROUP_BY)
    time: QueryTime | None = None
    filters: list[DatasetFilter] = Field(default_factory=list, max_length=MAX_FILTERS)
    order_by: list[DatasetOrder] = Field(default_factory=list, max_length=MAX_ORDER_BY)
    limit: int = Field(default=100, ge=1)


class DatasetResult(BaseModel):
    columns: list[ResultColumn]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    limit: int
    sql: str
    parameters: dict[str, Any]
    pii: PiiReport
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)
    value_types: list[str | None] = Field(default_factory=list, exclude=True)
