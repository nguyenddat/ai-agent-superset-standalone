import json
import unittest
from typing import get_args
from unittest.mock import patch

from backend.agent_package import get_chat_models
from backend.agent_package.agents.analysis_agent import AnalysisAgent
from backend.agent_package.agents.dataset_plan_agent import (
    DatasetFilterDraft,
    DatasetPlanAgent,
    DatasetPlanDraft,
    DatasetTimeDraft,
)
from backend.agent_package.agents.query_plan_agent import Granularity, Operator
from backend.agent_package.errors import AgentUnavailableError
from backend.agent_package.prompts.prompt_text2sql_analysis import analysis_prompt
from backend.agent_package.prompts.prompt_text2sql_dataset_plan import dataset_plan_prompt

FORBIDDEN = ("doanh thu", "paid", "miền", "cước", "carrier", "region", "ngành hàng")
PLAN = {
    "analysis": ["B1. x"], "status": "ok", "root_table": "hr.staff", "tables": ["hr.staff"],
    "select": [{"column": "staff.staff_id", "aggregation": "count", "alias": "so_nhan_su"}],
    "filters": [{"column": "staff.level", "operator": "in", "value": ["a", "b"], "placement": "join"}],
    "time": {"column": "staff.joined_on", "start": "2025-01-01", "end": "2026-01-01", "granularity": "month"},
    "unknown_field": 1,
}


class Chunk:
    def __init__(self, content):
        self.content = content


class FakeModel:
    def __init__(self, result=None, error=None, chunks=(), stream_error=None):
        self.result = result
        self.error = error
        self.chunks = chunks
        self.stream_error = stream_error
        self.seen = None

    def with_structured_output(self, schema, method):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.seen = messages
        if self.error:
            raise self.error
        return self.result

    def stream(self, messages):
        self.seen = messages
        for chunk in self.chunks:
            yield Chunk(chunk)
        if self.stream_error:
            raise self.stream_error


def failing_model():
    raise RuntimeError("missing key")


class DatasetPlanAgentTests(unittest.TestCase):
    def test_schema_puts_analysis_first_and_reuses_the_plan_enums(self) -> None:
        self.assertEqual(next(iter(DatasetPlanDraft.model_fields)), "analysis")
        self.assertEqual(get_args(DatasetFilterDraft.model_fields["operator"].annotation), get_args(Operator))
        self.assertEqual(get_args(DatasetTimeDraft.model_fields["granularity"].annotation), (Granularity, type(None)))

    def test_extra_fields_are_ignored_and_defaults_apply(self) -> None:
        draft = DatasetPlanDraft.model_validate(PLAN)
        self.assertFalse(hasattr(draft, "unknown_field"))
        self.assertEqual(draft.filters[0].placement, "join")
        self.assertEqual(DatasetFilterDraft(column="a.b", operator="is_null").placement, "where")
        self.assertEqual(draft.group_by, [])

    def test_agent_sends_the_fixed_prompt_and_context_as_json(self) -> None:
        model = FakeModel(PLAN)
        context = {"question": "Số nhân sự?", "today": "2026-04-02", "tables": []}
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            draft = DatasetPlanAgent().run(context)
        self.assertIsInstance(draft, DatasetPlanDraft)
        self.assertIs(model.schema, DatasetPlanDraft)
        self.assertEqual(draft.select[0].aggregation, "count")
        self.assertEqual(model.seen[0].content, dataset_plan_prompt)
        self.assertEqual(json.loads(model.seen[1].content), context)

    def test_failure_or_invalid_output_becomes_agent_unavailable(self) -> None:
        models = (FakeModel(error=RuntimeError("boom")), FakeModel(None), FakeModel({"analysis": [], "status": "x"}))
        for model in models:
            with patch.object(get_chat_models, "get_chat_model", lambda model=model: model):
                with self.assertRaises(AgentUnavailableError):
                    DatasetPlanAgent().run({})

    def test_prompt_states_the_core_rules(self) -> None:
        for phrase in ("GRAIN", "LEFT JOIN", 'placement="join"', "contains_pii=true", "group_by", "cannot_answer",
                       "needs_clarification", "today", "CHAR", "subquery", "B1."):
            self.assertIn(phrase, dataset_plan_prompt)


class AnalysisAgentTests(unittest.TestCase):
    def test_stream_yields_text_and_skips_empty_chunks(self) -> None:
        chunks = ["Kết ", "", [{"type": "text", "text": "luận"}, {"type": "tool_use", "id": "x"}, " ok"], [], None]
        model = FakeModel(chunks=chunks)
        context = {"question": "Ai?", "status": "answered"}
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            parts = list(AnalysisAgent().stream(context))
        self.assertEqual(parts, ["Kết ", "luận ok"])
        self.assertEqual(model.seen[0].content, analysis_prompt)
        self.assertEqual(json.loads(model.seen[1].content), context)

    def test_run_joins_the_stream(self) -> None:
        model = FakeModel(chunks=["a", "b"])
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            self.assertEqual(AnalysisAgent().run({}), "ab")

    def test_mid_stream_and_startup_errors_become_agent_unavailable(self) -> None:
        model = FakeModel(chunks=["a"], stream_error=RuntimeError("cut"))
        with patch.object(get_chat_models, "get_chat_model", lambda: model):
            stream = AnalysisAgent().stream({})
            self.assertEqual(next(stream), "a")
            with self.assertRaises(AgentUnavailableError):
                next(stream)
        with patch.object(get_chat_models, "get_chat_model", failing_model):
            with self.assertRaises(AgentUnavailableError):
                list(AnalysisAgent().stream({}))

    def test_prompt_covers_every_status_and_pii(self) -> None:
        for phrase in ("no_metric", "cannot_answer", "needs_clarification", "join_ambiguous", "join_not_declared",
                       "error", "<PII_1>", "data dictionary", "truncated", "format", "currency"):
            self.assertIn(phrase, analysis_prompt)


class PromptLeakTests(unittest.TestCase):
    def test_prompts_do_not_mention_real_data(self) -> None:
        for prompt in (dataset_plan_prompt, analysis_prompt):
            lowered = prompt.lower()
            for forbidden in FORBIDDEN:
                self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
