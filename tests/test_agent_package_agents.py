import unittest
from typing import get_args
from unittest.mock import patch

from backend.agent_package import get_chat_models
from backend.agent_package.agents.query_plan_agent import Granularity, Operator, PlanDraft, QueryPlanAgent
from backend.agent_package.agents.question_rewrite_agent import QuestionRewriteAgent, RewriteDraft
from backend.agent_package.errors import AgentUnavailableError
from backend.modules.text2sql.query import schemas as query_schemas


class FakeModel:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.seen = None

    def with_structured_output(self, schema, method):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.seen = messages
        if self.error:
            raise self.error
        return self.result


class AgentTests(unittest.TestCase):
    def test_the_agent_enums_stay_in_sync_with_the_query_schema(self) -> None:
        self.assertEqual(get_args(Operator), get_args(query_schemas.Operator))
        self.assertEqual(get_args(Granularity), get_args(query_schemas.Granularity))

    def test_agents_send_the_fixed_prompt_and_the_context_as_json(self) -> None:
        model = FakeModel(RewriteDraft(analysis=["b1"], rewritten_question="q"))
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            draft = QuestionRewriteAgent().run({"question": "Số đơn?"})
        self.assertEqual(draft.rewritten_question, "q")
        self.assertIn("QuestionRewriteAgent", model.seen[0].content)
        self.assertIn("Số đơn?", model.seen[1].content)

    def test_plan_agent_returns_validated_output(self) -> None:
        model = FakeModel({"analysis": [], "status": "no_metric", "reason": "x"})
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            draft = QueryPlanAgent().run({})
        self.assertIsInstance(draft, PlanDraft)

    def test_model_failure_or_empty_output_becomes_agent_unavailable(self) -> None:
        for model in (FakeModel(error=RuntimeError("boom")), FakeModel(result=None)):
            with patch.object(get_chat_models, "get_chat_model", lambda model=model: model):
                with self.assertRaises(AgentUnavailableError):
                    QuestionRewriteAgent().run({})



if __name__ == "__main__":
    unittest.main()
