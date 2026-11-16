from collections.abc import Iterator
from typing import Any

from ..get_chat_models import stream_text
from ..prompts.prompt_text2sql_analysis import analysis_prompt


class AnalysisAgent:
    def stream(self, context: dict[str, Any]) -> Iterator[str]:
        return stream_text(analysis_prompt, context)

    def run(self, context: dict[str, Any]) -> str:
        return "".join(self.stream(context))
