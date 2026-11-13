import json
from collections.abc import Iterator
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.agent_package.get_chat_models import get_chat_model
from backend.agent_package.prompts.prompt_column_dictionary import column_dictionary_prompt
from backend.agent_package.prompts.prompt_table_dictionary import table_dictionary_prompt

MAX_CONCURRENCY = 4


class ColumnSuggestion(BaseModel):
    column_name: str = Field(description="Tên cột vật lý, giữ nguyên như đầu vào.")
    display_name: str = Field(description="Nhãn dễ hiểu bằng tiếng Việt, tối đa 255 ký tự.")
    description: str | None = Field(default=None, description="Mô tả cột, null nếu thiếu căn cứ.")
    business_term: str | None = Field(default=None, description="Thuật ngữ nghiệp vụ, null nếu không rõ.")
    unit: str | None = Field(default=None, description="Đơn vị đo nếu biết chắc, nếu không thì null.")


class ColumnSuggestions(BaseModel):
    suggestions: list[ColumnSuggestion] = Field(
        description="Đề xuất cho toàn bộ cột được gửi vào, mỗi tên cột xuất hiện đúng một lần."
    )


class TableSuggestion(BaseModel):
    display_name: str = Field(description="Tên hiển thị ngắn gọn, dễ hiểu bằng tiếng Việt.")
    description: str | None = Field(default=None, description="Mô tả bảng, null nếu thiếu căn cứ.")
    grain_description: str | None = Field(default=None, description="Một dòng đại diện cho điều gì, null nếu chưa rõ.")
    created_at_column: str | None = Field(
        default=None, description="Tên cột ghi thời điểm tạo bản ghi, phải khớp tên cột đầu vào hoặc null."
    )


class DictionarySuggester(Protocol):
    def ensure_ready(self) -> None: ...

    def suggest_column_batches(
        self, contexts: list[dict[str, Any]],
    ) -> Iterator[tuple[int, ColumnSuggestions | Exception | None]]: ...

    def suggest_table(self, context: dict[str, Any]) -> TableSuggestion | None: ...


def _messages(prompt: str, context: dict[str, Any]) -> list[SystemMessage | HumanMessage]:
    return [SystemMessage(content=prompt), HumanMessage(content=json.dumps(context, ensure_ascii=False, indent=2))]


class LlmDictionarySuggester:
    def ensure_ready(self) -> None:
        get_chat_model()

    def suggest_column_batches(
        self, contexts: list[dict[str, Any]],
    ) -> Iterator[tuple[int, ColumnSuggestions | Exception | None]]:
        model = get_chat_model().with_structured_output(ColumnSuggestions, method="function_calling")
        inputs = [_messages(column_dictionary_prompt, context) for context in contexts]
        results = model.batch_as_completed(inputs, config={"max_concurrency": MAX_CONCURRENCY}, return_exceptions=True)
        for index, result in results:
            if isinstance(result, Exception) or result is None:
                yield index, result
            else:
                yield index, ColumnSuggestions.model_validate(result)

    def suggest_table(self, context: dict[str, Any]) -> TableSuggestion | None:
        model = get_chat_model().with_structured_output(TableSuggestion, method="function_calling")
        result = model.invoke(_messages(table_dictionary_prompt, context))
        return None if result is None else TableSuggestion.model_validate(result)
