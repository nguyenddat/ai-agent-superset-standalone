from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.core.setting import config


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
    )
