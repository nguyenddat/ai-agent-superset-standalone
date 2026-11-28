from collections.abc import Sequence

import httpx

from backend.agent_package.get_chat_models import OPENROUTER_PRIVACY
from backend.common.base_exceptions import ServiceUnavailableError
from backend.core.setting import config


class EmbeddingUnavailable(ServiceUnavailableError):
    abstract = False
    code = "embedding_unavailable"
    message = "Không thể tạo embedding."


class OpenRouterEmbedding:
    def __init__(
        self, client: httpx.Client | None = None, model: str | None = None, dimensions: int | None = None
    ) -> None:
        self.client = client or httpx.Client(timeout=60)
        self.model = model or config.text2sql_embedding_model
        self.dimensions = dimensions or config.text2sql_embedding_dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if config.openrouter_api_key is None:
            raise EmbeddingUnavailable("Cần cấu hình OPENROUTER_API_KEY để tạo embedding.")
        try:
            response = self.client.post(
                f"{config.openrouter_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {config.openrouter_api_key.get_secret_value()}"},
                json={
                    "model": self.model,
                    "input": list(texts),
                    "dimensions": self.dimensions,
                    "provider": OPENROUTER_PRIVACY,
                },
            )
            response.raise_for_status()
            data = response.json()["data"]
            if len(data) != len(texts):
                raise ValueError("embedding count mismatch")
            vectors: list[list[float] | None] = [None] * len(texts)
            for item in data:
                index = item["index"]
                vector = item["embedding"]
                if not isinstance(index, int) or not 0 <= index < len(texts) or len(vector) != self.dimensions:
                    raise ValueError("invalid embedding response")
                vectors[index] = vector
            if any(vector is None for vector in vectors):
                raise ValueError("missing embedding")
            return [vector for vector in vectors if vector is not None]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingUnavailable() from error

    def close(self) -> None:
        self.client.close()
