from collections.abc import Generator
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..get_chat_models import ReasoningDelta, invoke_structured, stream_structured
from ..prompts.prompt_text2sql_dataset_plan import dataset_plan_prompt
from .query_plan_agent import CLARIFICATION_OPTIONS_DESCRIPTION, Granularity, Operator, clean_options

MAX_TABLES = 8
MAX_SELECT = 20
Aggregation = Literal["sum", "avg", "min", "max", "count", "count_distinct"]
Placement = Literal["where", "join"]


class DatasetSelectDraft(BaseModel):
    column: str | None = Field(default=None, description="Cột dạng bảng.cột (tên bảng không kèm schema).")
    expression: str | None = Field(
        default=None, description="Biểu thức SQL an toàn, cột viết dạng bảng.cột; dùng thay cho column."
    )
    aggregation: Aggregation | None = Field(default=None, description="Hàm tổng hợp áp dụng cho column.")
    alias: str | None = Field(default=None, description="Tên cột kết quả ngắn gọn, chữ không dấu và dấu gạch dưới.")


class DatasetFilterDraft(BaseModel):
    column: str = Field(description="Cột dạng bảng.cột.")
    operator: Operator
    value: str | list[str] | None = Field(default=None, description="Chuỗi; danh sách chuỗi cho in/not_in.")
    placement: Placement = Field(
        default="where",
        description='"where" (mặc định) loại dòng không khớp; "join" giữ dòng gốc không có dòng khớp ở bảng nối.',
    )


class DatasetTimeDraft(BaseModel):
    column: str = Field(description="Cột ngày hoặc ngày giờ dạng bảng.cột.")
    start: str | None = Field(default=None, description="YYYY-MM-DD, tính cả ngày này.")
    end: str | None = Field(default=None, description="YYYY-MM-DD, không tính ngày này.")
    granularity: Granularity | None = None


class DatasetOrderDraft(BaseModel):
    by: str = Field(description='Alias một cột kết quả, "time" (khi có granularity) hoặc bảng.cột trong group_by.')
    direction: Literal["asc", "desc"] = "desc"


class DatasetPlanDraft(BaseModel):
    analysis: list[str] = Field(
        description="Suy luận từng bước B1..Bn, mỗi bước một dòng, viết TRƯỚC khi quyết định các trường bên dưới."
    )
    status: Literal["ok", "cannot_answer", "needs_clarification"]
    root_table: str | None = Field(default=None, description="Bảng gốc dạng schema.bảng, theo grain của câu hỏi.")
    tables: list[str] = Field(
        default_factory=list, max_length=MAX_TABLES, description="Các bảng cần nối dạng schema.bảng, gồm cả gốc."
    )
    select: list[DatasetSelectDraft] = Field(
        default_factory=list, max_length=MAX_SELECT, description="1 đến 20 mục khi status là ok."
    )
    group_by: list[str] = Field(default_factory=list, description="Cột dạng bảng.cột.")
    time: DatasetTimeDraft | None = None
    filters: list[DatasetFilterDraft] = Field(default_factory=list)
    order_by: list[DatasetOrderDraft] = Field(default_factory=list)
    limit: int | None = None
    assumptions: list[str] = Field(default_factory=list)
    reason: str = ""
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list, description=CLARIFICATION_OPTIONS_DESCRIPTION)

    @field_validator("clarification_options", mode="before")
    @classmethod
    def _trim_options(cls, value: object) -> list[str]:
        return clean_options(value)


class DatasetPlanAgent:
    def run(self, context: dict[str, Any]) -> DatasetPlanDraft:
        return invoke_structured(DatasetPlanDraft, dataset_plan_prompt, context)

    def stream(self, context: dict[str, Any]) -> Generator[ReasoningDelta, None, DatasetPlanDraft]:
        return stream_structured(DatasetPlanDraft, dataset_plan_prompt, context)
