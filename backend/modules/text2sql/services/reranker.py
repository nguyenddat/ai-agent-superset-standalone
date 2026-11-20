from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import httpx

from backend.core.setting import config

from ..utils.exceptions import Text2SqlRerankUnavailable


class Reranker(Protocol):
    def rerank(self, question: str, passages: Sequence[str], subject: str = "metric") -> list[float]: ...


QUESTION_NAME = "relevance"
INSTRUCTIONS = (
    "Đánh giá {noun} dưới đây có giúp trả lời câu hỏi của người dùng hay không. "
    "Chỉ xét ý nghĩa nghiệp vụ, không xét cách cài đặt kỹ thuật."
)
SUBJECTS: dict[str, tuple[str, list[str]]] = {
    "metric": ("metric (chỉ số)", [
        "Không liên quan: metric đo một đại lượng khác với điều câu hỏi cần biết.",
        "Liên quan một phần: cùng chủ đề nhưng không đo đúng đại lượng được hỏi.",
        "Trả lời trực tiếp: metric đo đúng đại lượng mà câu hỏi cần biết.",
    ]),
    "table": ("bảng dữ liệu", [
        "Không liên quan: bảng không chứa dữ liệu mà câu hỏi cần.",
        "Liên quan một phần: bảng cùng chủ đề nhưng thiếu dữ liệu chính cần để trả lời.",
        "Trả lời trực tiếp: bảng chứa dữ liệu cần để trả lời câu hỏi.",
    ]),
    "column": ("cột dữ liệu", [
        "Không liên quan: cột không mang thông tin câu hỏi cần.",
        "Liên quan một phần: cột có liên quan nhưng không phải thông tin chính được hỏi.",
        "Trả lời trực tiếp: cột chính là thông tin hoặc điều kiện lọc mà câu hỏi nhắc tới.",
    ]),
    "glossary": ("thuật ngữ nghiệp vụ", [
        "Không liên quan: thuật ngữ không xuất hiện hoặc không cần để hiểu câu hỏi.",
        "Liên quan một phần: thuật ngữ gần nghĩa nhưng không phải khái niệm câu hỏi dùng.",
        "Trả lời trực tiếp: câu hỏi dùng đúng khái niệm này hoặc từ đồng nghĩa của nó.",
    ]),
    "expert_rule": ("quy tắc chuyên gia", [
        "Không liên quan: quy tắc không áp dụng cho câu hỏi.",
        "Liên quan một phần: quy tắc cùng chủ đề nhưng điều kiện áp dụng chưa khớp rõ với câu hỏi.",
        "Trả lời trực tiếp: quy tắc áp dụng trực tiếp cho câu hỏi này.",
    ]),
    "own_knowledge": ("cách hiểu riêng của người dùng", [
        "Không liên quan: cách hiểu này không liên quan đến câu hỏi.",
        "Liên quan một phần: cùng chủ đề nhưng không định nghĩa khái niệm câu hỏi dùng.",
        "Trả lời trực tiếp: câu hỏi dùng đúng khái niệm mà cách hiểu này định nghĩa.",
    ]),
}


class JevReranker:
    def __init__(
        self, client: httpx.Client | None = None, model: str | None = None, concurrency: int | None = None
    ) -> None:
        self.client = client or httpx.Client(timeout=config.text2sql_rerank_timeout_seconds)
        self.model = model or config.text2sql_rerank_model
        self.concurrency = concurrency or config.text2sql_rerank_concurrency

    def rerank(self, question: str, passages: Sequence[str], subject: str = "metric") -> list[float]:
        if subject not in SUBJECTS:
            raise ValueError(f"Loại đối tượng không hợp lệ: {subject}")
        if not passages:
            return []
        if config.openrouter_api_key is None:
            raise Text2SqlRerankUnavailable("Cần cấu hình OPENROUTER_API_KEY để xếp hạng lại.")
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(passages))) as executor:
            return list(executor.map(lambda passage: self._score(question, passage, subject), passages))

    def _score(self, question: str, passage: str, subject: str) -> float:
        noun, criteria = SUBJECTS[subject]
        body = {
            "model": self.model,
            "state": {"cau_hoi": question, "loai": noun, "noi_dung": passage},
            "questions": {QUESTION_NAME: {
                "type": "score", "instructions": INSTRUCTIONS.format(noun=noun), "criteria": criteria,
            }},
        }
        try:
            response = self.client.post(
                f"{config.openrouter_base_url.rstrip('/')}/systemone",
                headers={"Authorization": f"Bearer {config.openrouter_api_key.get_secret_value()}"},
                json=body,
            )
            response.raise_for_status()
            answer = response.json()["answers"][QUESTION_NAME]
            if answer["type"] != "score":
                raise ValueError("answer is not a score")
            score = float(answer["score"])
            if score != score:
                raise ValueError("score is not a number")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise Text2SqlRerankUnavailable() from error
        return min(max(score / (len(criteria) - 1), 0.0), 1.0)

    def close(self) -> None:
        self.client.close()
