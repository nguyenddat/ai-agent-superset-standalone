import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from backend.core.setting import config
from backend.modules.text2sql.services.reranker import (
    SUBJECTS,
    JevReranker,
)
from backend.modules.text2sql.utils.exceptions import Text2SqlRerankUnavailable
from backend.modules.text2sql.utils.topics import TOPICS

SCORES = {"a": 2.0, "b": 1.0, "c": 0.0}


def reranker_with(responder, concurrency: int = 3) -> tuple[JevReranker, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responder(request)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return JevReranker(client, model="typesafe/jev-1.14", concurrency=concurrency), requests


def score_by_passage(request: httpx.Request) -> httpx.Response:
    passage = json.loads(request.content)["state"]["noi_dung"]
    return httpx.Response(200, json={"answers": {"relevance": {
        "type": "score", "score": SCORES.get(passage, 0.0), "confidence": 0.9,
    }}})


class JevRerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(config, "openrouter_api_key", SimpleNamespace(get_secret_value=lambda: "test-key"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sends_one_score_question_per_passage_to_systemone(self) -> None:
        reranker, requests = reranker_with(score_by_passage)
        reranker.rerank("doanh thu?", ["a", "b"])
        self.assertEqual(len(requests), 2)
        request = requests[0]
        self.assertEqual(request.url.path, "/api/v1/systemone")
        self.assertEqual(request.headers["authorization"], "Bearer test-key")
        body = json.loads(request.content)
        self.assertEqual(body["model"], "typesafe/jev-1.14")
        self.assertEqual(body["state"]["cau_hoi"], "doanh thu?")
        self.assertEqual(body["state"]["loai"], SUBJECTS["metric"][0])
        question = body["questions"]["relevance"]
        self.assertEqual(question["type"], "score")
        self.assertEqual(question["criteria"], SUBJECTS["metric"][1])

    def test_every_indexed_topic_has_its_own_wording(self) -> None:
        self.assertEqual(set(SUBJECTS), set(TOPICS))
        self.assertEqual(len({noun for noun, _ in SUBJECTS.values()}), len(TOPICS))
        for noun, criteria in SUBJECTS.values():
            self.assertEqual(len(criteria), 3)

    def test_subject_selects_the_question_wording(self) -> None:
        reranker, requests = reranker_with(score_by_passage)
        reranker.rerank("q", ["a"], "glossary")
        body = json.loads(requests[0].content)
        self.assertEqual(body["state"]["loai"], SUBJECTS["glossary"][0])
        self.assertEqual(body["questions"]["relevance"]["criteria"], SUBJECTS["glossary"][1])
        self.assertIn(SUBJECTS["glossary"][0], body["questions"]["relevance"]["instructions"])

    def test_unknown_subject_is_a_programming_error_not_a_service_failure(self) -> None:
        reranker, requests = reranker_with(score_by_passage)
        with self.assertRaises(ValueError):
            reranker.rerank("q", ["a"], "bogus")
        self.assertEqual(requests, [])

    def test_scores_are_normalized_and_keep_passage_order(self) -> None:
        reranker, _ = reranker_with(score_by_passage)
        self.assertEqual(reranker.rerank("q", ["c", "a", "b"]), [0.0, 1.0, 0.5])

    def test_scores_are_clamped_to_unit_interval(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            value = 3.5 if json.loads(request.content)["state"]["noi_dung"] == "hi" else -1.0
            return httpx.Response(200, json={"answers": {"relevance": {"type": "score", "score": value}}})

        reranker, _ = reranker_with(respond)
        self.assertEqual(reranker.rerank("q", ["hi", "lo"]), [1.0, 0.0])

    def test_empty_passages_make_no_request(self) -> None:
        reranker, requests = reranker_with(score_by_passage)
        self.assertEqual(reranker.rerank("q", []), [])
        self.assertEqual(requests, [])

    def test_any_failure_raises_rerank_unavailable(self) -> None:
        failures = {
            "http error": lambda request: httpx.Response(500, json={"error": {"message": "boom"}}),
            "refusal": lambda request: httpx.Response(200, json={"answers": {"relevance": {"type": "refusal"}}}),
            "missing answer": lambda request: httpx.Response(200, json={"answers": {}}),
            "not json": lambda request: httpx.Response(200, text="oops"),
            "non numeric score": lambda request: httpx.Response(
                200, json={"answers": {"relevance": {"type": "score", "score": "high"}}}
            ),
        }
        for name, responder in failures.items():
            with self.subTest(name):
                reranker, _ = reranker_with(responder)
                with self.assertRaises(Text2SqlRerankUnavailable):
                    reranker.rerank("q", ["a", "b"])

    def test_missing_api_key_raises_without_calling_openrouter(self) -> None:
        reranker, requests = reranker_with(score_by_passage)
        with patch.object(config, "openrouter_api_key", None):
            with self.assertRaises(Text2SqlRerankUnavailable):
                reranker.rerank("q", ["a"])
        self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
