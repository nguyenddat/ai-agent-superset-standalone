import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.core.setting import config
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.services.topic_search_service import (
    TopicSearchService,
)
from backend.modules.text2sql.utils.exceptions import (
    Text2SqlConnectionNotFound,
    Text2SqlInvalidRequest,
    Text2SqlRerankUnavailable,
)

register_all_models()


def point(entity_id, text, table_id=None, score=1.0, **payload):
    return {"score": score, "payload": {
        "entity_id": str(entity_id), "table_id": str(table_id) if table_id else None, "text": text,
        "name": payload.pop("name", text), "display_name": payload.pop("display_name", text), **payload,
    }}


class RecordingIndex:
    def __init__(self, points=None):
        self.points = points or []
        self.calls = []

    def search(self, question, vector, connection_id, topic, limit, filters=None):
        self.calls.append({"topic": topic, "limit": limit, "filters": filters, "connection_id": connection_id})
        return list(self.points)


class FakeEmbedding:
    def embed(self, texts):
        return [[0.1] * 4 for _ in texts]


class StaticReranker:
    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.subjects = scores, error, []

    def rerank(self, question, passages, subject="metric"):
        self.subjects.append(subject)
        if self.error is not None:
            raise self.error
        return list(self.scores)


class ConnectionSession:
    def get(self, model, entity_id):
        return SimpleNamespace(id=entity_id)


class MissingConnectionSession:
    def get(self, model, entity_id):
        return None


class TopicSearchTests(unittest.TestCase):
    def service(self, index, session=None):
        return TopicSearchService(session or ConnectionSession(), index, FakeEmbedding())

    def test_searches_the_requested_topic_inside_the_connection(self) -> None:
        connection_id, first, second = uuid4(), uuid4(), uuid4()
        index = RecordingIndex([point(first, "Bảng A", score=0.9), point(second, "Bảng B", score=0.5)])
        outcome = self.service(index).search(connection_id, "table", "câu hỏi", 5)
        self.assertEqual([hit.entity_id for hit in outcome.hits], [first, second])
        self.assertEqual((index.calls[0]["topic"], index.calls[0]["connection_id"]), ("table", str(connection_id)))
        self.assertIsNone(index.calls[0]["filters"])
        self.assertFalse(outcome.reranked)

    def test_k_limits_results_and_the_query_when_not_reranking(self) -> None:
        index = RecordingIndex([point(uuid4(), f"t{n}") for n in range(5)])
        outcome = self.service(index).search(uuid4(), "glossary", "q", 2)
        self.assertEqual(len(outcome.hits), 2)
        self.assertEqual(index.calls[0]["limit"], 2)

    def test_own_knowledge_is_filtered_by_user_and_requires_one(self) -> None:
        index = RecordingIndex([point(uuid4(), "Ngày mưa")])
        self.service(index).search(uuid4(), "own_knowledge", "q", 3, user_id=" alice ")
        self.assertEqual(index.calls[0]["filters"], {"user_id": "alice"})
        for missing in (None, "", "   "):
            with self.subTest(user_id=missing), self.assertRaises(Text2SqlInvalidRequest):
                self.service(index).search(uuid4(), "own_knowledge", "q", 3, user_id=missing)

    def test_unknown_topic_and_missing_connection_are_rejected(self) -> None:
        with self.assertRaises(Text2SqlInvalidRequest):
            self.service(RecordingIndex()).search(uuid4(), "bogus", "q", 3)
        with self.assertRaises(Text2SqlConnectionNotFound):
            self.service(RecordingIndex(), MissingConnectionSession()).search(uuid4(), "table", "q", 3)

    def test_reranker_reorders_by_its_score_and_names_the_topic(self) -> None:
        ids = [uuid4(), uuid4(), uuid4()]
        index = RecordingIndex([point(ids[0], "a"), point(ids[1], "b"), point(ids[2], "c")])
        reranker = StaticReranker(scores=[0.2, 0.9, 0.5])
        outcome = self.service(index).search(uuid4(), "expert_rule", "q", 2, reranker)
        self.assertTrue(outcome.reranked)
        self.assertEqual([hit.entity_id for hit in outcome.hits], [ids[1], ids[2]])
        self.assertEqual(outcome.hits[0].rerank_score, 0.9)
        self.assertEqual(reranker.subjects, ["expert_rule"])

    def test_rerank_pool_is_wider_than_k_but_ties_keep_search_order(self) -> None:
        ids = [uuid4() for _ in range(3)]
        index = RecordingIndex([point(entity, "x") for entity in ids])
        with patch.object(config, "text2sql_rerank_pool", 12):
            outcome = self.service(index).search(uuid4(), "column", "q", 2, StaticReranker(scores=[0.5] * 3))
        self.assertEqual(index.calls[0]["limit"], 12)
        self.assertEqual([hit.entity_id for hit in outcome.hits], ids[:2])

    def test_rerank_failure_falls_back_to_search_order(self) -> None:
        ids = [uuid4(), uuid4()]
        index = RecordingIndex([point(ids[0], "a"), point(ids[1], "b")])
        outcome = self.service(index).search(
            uuid4(), "table", "q", 2, StaticReranker(error=Text2SqlRerankUnavailable())
        )
        self.assertFalse(outcome.reranked)
        self.assertEqual(outcome.rerank_error, "text2sql_rerank_unavailable")
        self.assertEqual([hit.entity_id for hit in outcome.hits], ids)
        self.assertEqual({hit.rerank_score for hit in outcome.hits}, {None})



if __name__ == "__main__":
    unittest.main()
