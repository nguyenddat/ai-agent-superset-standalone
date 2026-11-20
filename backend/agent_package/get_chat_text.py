import json
import logging
import time
from collections.abc import Callable
from contextlib import closing
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic_core import to_jsonable_python

from .get_chat_models import get_chat_model

logger = logging.getLogger(__name__)

TextCallback = Callable[[str], None]


def get_chat_text(
    system_prompt: str, params: dict[str, Any], on_text: TextCallback | None = None,
    model: BaseChatModel | None = None,
) -> str:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(params, ensure_ascii=False, indent=2, default=to_jsonable_python)),
    ]
    chat_model = model or get_chat_model()
    start = time.perf_counter()
    if on_text is None:
        text = chat_model.invoke(messages).text
    else:
        parts: list[str] = []
        with closing(chat_model.stream(messages)) as chunks:
            for chunk in chunks:
                piece = chunk.text
                if piece:
                    parts.append(piece)
                    on_text(piece)
        text = "".join(parts)
    logger.info("[Timing] LLM text streaming=%s took %.2fs", on_text is not None, time.perf_counter() - start)
    return text.strip()
