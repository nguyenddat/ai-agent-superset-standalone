import json
from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backend.core.setting import config

Output = TypeVar("Output", bound=BaseModel)
# Sent on every OpenRouter call: only providers that keep nothing and train on nothing.
OPENROUTER_PRIVACY = {"zdr": True, "data_collection": "deny"}


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.openrouter_model,
        temperature=0.0,
        max_tokens=4096,
        timeout=60,
        max_retries=2,
        api_key=config.require_openrouter_api_key(),
        base_url=config.openrouter_base_url,
        extra_body={"provider": OPENROUTER_PRIVACY},
    )


def structured_model(schema: type[Output]) -> Any:
    return get_chat_model().with_structured_output(schema, method="function_calling")


def build_messages(prompt: str, context: dict[str, Any]) -> list[SystemMessage | HumanMessage]:
    return [SystemMessage(content=prompt), HumanMessage(content=json.dumps(context, ensure_ascii=False, indent=2))]
