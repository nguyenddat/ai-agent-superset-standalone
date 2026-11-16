from collections.abc import Generator
from typing import Any

from pydantic import BaseModel, Field

from ..get_chat_models import ReasoningDelta, invoke_structured, stream_structured
from ..prompts.prompt_text2sql_rewrite import question_rewrite_prompt


class RewriteDraft(BaseModel):
    analysis: list[str] = Field(
        description="Suy luận từng bước, mỗi bước một dòng, viết TRƯỚC khi quyết định các trường bên dưới."
    )
    rewritten_question: str = Field(description="Câu hỏi đã viết lại theo thuật ngữ chuẩn, quy tắc và tri thức riêng.")
    glossary_term_ids: list[str] = Field(default_factory=list, description="id thuật ngữ thật sự liên quan.")
    rule_ids: list[str] = Field(default_factory=list, description="id quy tắc chuyên gia thật sự liên quan.")
    own_knowledge_ids: list[str] = Field(default_factory=list, description="id tri thức riêng thật sự liên quan.")
    changes: list[str] = Field(default_factory=list, description="Các thay đổi đã thực hiện, mỗi dòng một thay đổi.")


class QuestionRewriteAgent:
    def run(self, context: dict[str, Any]) -> RewriteDraft:
        return invoke_structured(RewriteDraft, question_rewrite_prompt, context)

    def stream(self, context: dict[str, Any]) -> Generator[ReasoningDelta, None, RewriteDraft]:
        return stream_structured(RewriteDraft, question_rewrite_prompt, context)
