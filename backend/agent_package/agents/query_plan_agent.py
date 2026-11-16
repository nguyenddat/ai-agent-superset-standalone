from collections.abc import Generator
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..get_chat_models import ReasoningDelta, invoke_structured, stream_structured
from ..prompts.prompt_text2sql_plan import query_plan_prompt

MAX_QUERIES = 3
MAX_CLARIFICATION_OPTIONS = 4
CLARIFICATION_OPTIONS_DESCRIPTION = (
    "Khi status là needs_clarification: tối đa 4 lựa chọn trả lời ngắn (mỗi lựa chọn vài từ, người dùng bấm chọn được) "
    "cho clarification_question; để rỗng nếu không có lựa chọn rõ ràng."
)
Operator = Literal[
    "equals", "not_equals", "contains", "not_contains", "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal", "in", "not_in", "is_null", "is_not_null",
]
Granularity = Literal["day", "week", "month", "quarter", "year"]


class DraftFilter(BaseModel):
    column: str = Field(description="Tên cột (trường name).")
    operator: Operator
    value: str | list[str] | None = Field(default=None, description="Chuỗi; danh sách chuỗi cho in/not_in.")


class DraftTime(BaseModel):
    column: str = Field(description="Tên cột ngày hoặc ngày giờ.")
    start: str | None = Field(default=None, description="YYYY-MM-DD, tính cả ngày này.")
    end: str | None = Field(default=None, description="YYYY-MM-DD, không tính ngày này.")
    granularity: Granularity | None = None


class DraftOrder(BaseModel):
    by: str = Field(description='"metric", "time" hoặc tên cột trong group_by.')
    direction: Literal["asc", "desc"] = "desc"


class DraftQuery(BaseModel):
    metric_id: str
    group_by: list[str] = Field(default_factory=list)
    time: DraftTime | None = None
    filters: list[DraftFilter] = Field(default_factory=list)
    order_by: list[DraftOrder] = Field(default_factory=list)
    limit: int | None = None


class PlanDraft(BaseModel):
    analysis: list[str] = Field(
        description="Suy luận từng bước, mỗi bước một dòng, viết TRƯỚC khi quyết định các trường bên dưới."
    )
    status: Literal["ok", "no_metric", "needs_clarification"]
    queries: list[DraftQuery] = Field(default_factory=list, max_length=MAX_QUERIES)
    assumptions: list[str] = Field(default_factory=list)
    reason: str = ""
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list, description=CLARIFICATION_OPTIONS_DESCRIPTION)

    @field_validator("clarification_options", mode="before")
    @classmethod
    def _trim_options(cls, value: object) -> list[str]:
        return clean_options(value)


def clean_options(value: object) -> list[str]:
    items = value if isinstance(value, list) else []
    options = [" ".join(item.split()) for item in items if isinstance(item, str) and item.strip()]
    return list(dict.fromkeys(options))[:MAX_CLARIFICATION_OPTIONS]


class QueryPlanAgent:
    def run(self, context: dict[str, Any]) -> PlanDraft:
        return invoke_structured(PlanDraft, query_plan_prompt, context)

    def stream(self, context: dict[str, Any]) -> Generator[ReasoningDelta, None, PlanDraft]:
        return stream_structured(PlanDraft, query_plan_prompt, context)
