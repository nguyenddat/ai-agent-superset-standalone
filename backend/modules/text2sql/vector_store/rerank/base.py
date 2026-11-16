from collections.abc import Sequence
from typing import Protocol


class Reranker(Protocol):
    def rerank(self, question: str, passages: Sequence[str], subject: str = "metric") -> list[float]: ...
