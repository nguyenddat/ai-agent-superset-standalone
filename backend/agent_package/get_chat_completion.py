import json
import logging
import time
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic_core import to_jsonable_python

from .get_chat_models import get_chat_model
from .prompts.prompt_intent_classify import (
    intent_classify_parser,
    intent_classify_prompt,
)
from .prompts.prompt_rewrite import rewrite_parser, rewrite_prompt

logger = logging.getLogger(__name__)

PROMPTS_BY_TASK: dict[str, tuple[str, PydanticOutputParser]] = {
    "rewrite": (rewrite_prompt, rewrite_parser),
    "intent_classify": (intent_classify_prompt, intent_classify_parser),
}


def get_prompt_by_task(task: str) -> tuple[ChatPromptTemplate, PydanticOutputParser]:
    if task not in PROMPTS_BY_TASK:
        raise ValueError(f"Unknown task: {task}")
    system_prompt, parser = PROMPTS_BY_TASK[task]
    prompt_template = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_prompt + parser.get_format_instructions()),
            ("human", "{input}"),
        ]
    )
    return prompt_template, parser


def get_chat_completion(task: str, params: dict[str, Any]) -> dict[str, Any]:
    prompt, parser = get_prompt_by_task(task)
    chain = prompt | get_chat_model() | parser

    start = time.perf_counter()
    result = chain.invoke(
        {"input": json.dumps(params, ensure_ascii=False, indent=2, default=to_jsonable_python)}
    ).model_dump(mode="json")
    elapsed = time.perf_counter() - start
    logger.info("[Timing] LLM task='%s' took %.2fs", task, elapsed)
    return result
