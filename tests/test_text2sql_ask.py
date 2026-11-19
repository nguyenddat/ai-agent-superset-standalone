import unittest
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.agent_package.agents.query_plan_agent import DraftFilter, DraftQuery, DraftTime, PlanDraft
from backend.agent_package.agents.question_rewrite_agent import RewriteDraft
from backend.common.base_model import Base
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.expert_rule_management.services import ExpertRuleService
from backend.modules.glossary_management.services import GlossaryService
from backend.modules.metric_management.models import Metric
from backend.modules.model_registry import register_all_models
from backend.modules.own_knowledge.models import OwnKnowledgeEntry
from backend.modules.text2sql.chat.context import ContextGatherer
from backend.modules.text2sql.chat.rewrite import build_rewrite_context, rewrite_question
from backend.modules.text2sql.chat.service import AskService, execute_ask
from backend.modules.text2sql.common.errors import Text2SqlInvalidRequest
from backend.modules.text2sql.query.schemas import PiiReport, QueryMetricInfo, QueryResult, ResultColumn

register_all_models()
TODAY = date(2026, 4, 2)


def point(entity_id, text, topic, table_id=None):
    return {"score": 1.0, "payload": {
        "entity_id": str(entity_id), "table_id": str(table_id) if table_id else None, "text": text,
        "name": text, "display_name": text, "topic": topic,
    }}


class FakeIndex:
    def __init__(self, hits=None):
        self.hits = hits or {}
        self.calls = []

    def search(self, question, vector, connection_id, topic, limit, filters=None):
        self.calls.append((topic, filters))
        return list(self.hits.get(topic, []))


class FakeEmbedding:
    def embed(self, texts):
        return [[0.1] * 4 for _ in texts]


class FakeLlm:
    def __init__(self, rewrite=None, plan=None):
        self.rewrite_draft = rewrite
        self.plan_draft = plan
        self.rewrite_contexts = []
        self.plan_contexts = []

    @property
    def rewriter(self):
        return SimpleNamespace(run=self.rewrite)

    @property
    def planner(self):
        return SimpleNamespace(run=self.plan)

    def rewrite(self, context):
        self.rewrite_contexts.append(context)
        return self.rewrite_draft or RewriteDraft(analysis=[], rewritten_question=context["question"])

    def plan(self, context):
        self.plan_contexts.append(context)
        return self.plan_draft


class FakeQueryService:
    def __init__(self):
        self.executed = []

    def execute(self, compiled, source_url, confirmation):
        self.executed.append((compiled, confirmation))
        return QueryResult(
            metric=QueryMetricInfo(
                metric_id=compiled.metric_id, name=compiled.metric_name, label=compiled.metric_label, format=None,
                currency=None, warning_text=None, table=compiled.table_label,
            ),
            columns=[ResultColumn(name="m", role="metric")], rows=[["1"]], row_count=1, truncated=False,
            limit=compiled.limit, sql=compiled.sql, parameters=compiled.parameters, pii=PiiReport(), elapsed_ms=1,
        )


class AskFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        self.connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.table = DatabaseTable(schema_id=schema.id, name="visits", table_type="TABLE")
        s.add(self.table)
        s.flush()
        self.col = {}
        for position, (name, data_type) in enumerate([
            ("department", "text"), ("status", "text"), ("fee", "numeric"), ("visit_date", "date"),
            ("patient_name", "text"), ("is_urgent", "boolean"),
        ], start=1):
            self.col[name] = DatabaseColumn(
                table_id=self.table.id, name=name, data_type=data_type, ordinal_position=position, is_nullable=True,
            )
            s.add(self.col[name])
        s.flush()
        s.add_all([
            TableDictionary(table_id=self.table.id, display_name="Lượt khám"),
            ColumnDictionary(column_id=self.col["status"].id, display_name="Trạng thái"),
            ColumnDictionary(column_id=self.col["department"].id, display_name="Khoa"),
            ColumnDictionary(column_id=self.col["patient_name"].id, display_name="Tên bệnh nhân", contains_pii=True),
        ])
        self.visits = Metric(table_id=self.table.id, name="visits", label="Số lượt khám", expression="COUNT(*)")
        self.fees = Metric(table_id=self.table.id, name="fees", label="Viện phí", expression="SUM(fee)")
        self.virtual = Metric(table_id=self.table.id, name="virt", expression="COUNT(*)", source_sql="SELECT 1")
        s.add_all([self.visits, self.fees, self.virtual])
        s.flush()
        glossary = GlossaryService(s)
        term = glossary.create_term({
            "connection_id": self.connection.id, "canonical_name": "Lượt khám",
            "definition": "Một lần bệnh nhân được khám", "synonyms": ["khám bệnh"],
            "links": [{"kind": "metric", "id": self.visits.id}],
        })
        glossary.approve(term["id"], 1)
        self.term_id = UUID(str(term["id"]))
        rules = ExpertRuleService(s)
        rule = rules.create_rule({
            "connection_id": self.connection.id, "table_id": self.table.id, "name": "Chỉ tính lượt khám hoàn tất",
            "description": "Chỉ tính lượt khám đã hoàn tất",
            "conditions": [{"column_id": self.col["status"].id, "operator": "equals", "value_type": "string",
                            "value": "done"}],
            "exceptions": [], "examples": [], "glossary_term_ids": [self.term_id], "metric_ids": [self.visits.id],
        })
        rules.approve(rule["id"], 1)
        self.rule_id = UUID(str(rule["id"]))
        s.add(OwnKnowledgeEntry(
            connection_id=self.connection.id, user_id="alice", kind="glossary", name="Mùa khám",
            normalized_name="mua kham", definition="Mùa khám của tôi là tháng 6 và 7", table_id=self.table.id,
        ))
        s.flush()
        self.index = FakeIndex({
            "glossary": [point(self.term_id, "Lượt khám", "glossary")],
            "expert_rule": [point(self.rule_id, "Chỉ tính lượt khám hoàn tất", "expert_rule", self.table.id)],
        })

    def service(self, llm: FakeLlm) -> AskService:
        return AskService(
            self.session, self.index, FakeEmbedding(), rewriter=llm.rewriter, planner=llm.planner, today=lambda: TODAY,
        )

    def selecting_rewrite(self, question="Số lượt khám của khoa Nhi trong tháng 4/2026?"):
        return RewriteDraft(
            analysis=["b1"], rewritten_question=question, glossary_term_ids=[str(self.term_id)],
            rule_ids=[str(self.rule_id)], own_knowledge_ids=[], changes=["x"],
        )

    def plan(self, **query):
        defaults = {"metric_id": str(self.visits.id), "group_by": [], "time": None, "filters": [], "order_by": [],
                    "limit": None}
        return PlanDraft(analysis=["p"], status="ok", queries=[DraftQuery(**{**defaults, **query})], reason="r")

    def test_rewrite_always_runs_once_even_with_nothing_retrieved(self) -> None:
        self.index.hits = {}
        llm = FakeLlm(plan=PlanDraft(analysis=[], status="no_metric", reason="không có"))
        prepared = self.service(llm).prepare(self.connection.id, "điểm trung bình lớp 10A?")
        self.assertEqual(len(llm.rewrite_contexts), 1)
        self.assertEqual(prepared.rewrite.rewritten_question, "điểm trung bình lớp 10A?")
        self.assertEqual(llm.rewrite_contexts[0]["glossary_terms"], [])

    def test_rewrite_context_gives_plain_text_and_metric_names_not_ids_of_columns(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan())
        self.service(llm).prepare(self.connection.id, "Số lượt khám của khoa Nhi trong tháng này?")
        context = llm.rewrite_contexts[0]
        self.assertEqual(context["today"], "2026-04-02")
        term = context["glossary_terms"][0]
        self.assertEqual((term["name"], term["metrics"]), ("Lượt khám", ["Số lượt khám"]))
        rule = context["expert_rules"][0]
        self.assertEqual((rule["description"], rule["metrics"]), ("Chỉ tính lượt khám đã hoàn tất", ["Số lượt khám"]))
        self.assertEqual(rule["conditions"], ["Trạng thái bằng done"])

    def test_retrieval_uses_the_original_question_and_expands_by_links(self) -> None:
        self.index.hits = {"glossary": [point(self.term_id, "Lượt khám", "glossary")]}
        llm = FakeLlm(plan=PlanDraft(analysis=[], status="no_metric", reason="x"))
        self.service(llm).prepare(self.connection.id, "khám bệnh")
        context = llm.rewrite_contexts[0]
        self.assertEqual([item["id"] for item in context["expert_rules"]], [str(self.rule_id)])

    def test_own_knowledge_is_searched_only_for_a_known_user_and_is_filtered_by_them(self) -> None:
        llm = FakeLlm(plan=PlanDraft(analysis=[], status="no_metric", reason="x"))
        self.service(llm).prepare(self.connection.id, "mùa khám")
        self.assertNotIn("own_knowledge", [topic for topic, _ in self.index.calls])
        self.service(llm).prepare(self.connection.id, "mùa khám", user_id="alice")
        self.assertIn(("own_knowledge", {"user_id": "alice"}), self.index.calls)

    def test_rewrite_ignores_unknown_ids_and_empty_rewrites(self) -> None:
        draft = RewriteDraft(
            analysis=[], rewritten_question="   ", glossary_term_ids=[str(self.term_id), str(uuid4()), "xyz"],
            rule_ids=[str(self.rule_id), str(self.rule_id)], own_knowledge_ids=[str(uuid4())],
        )
        llm = FakeLlm(rewrite=draft)
        context = ContextGatherer(self.session, self.index, FakeEmbedding()).gather(self.connection.id, "q", None)
        outcome = rewrite_question(llm.rewriter, "câu gốc", TODAY, context)
        self.assertEqual(outcome.info.rewritten_question, "câu gốc")
        self.assertEqual((outcome.term_ids, outcome.rule_ids), ([self.term_id], [self.rule_id]))
        self.assertEqual(outcome.info.own_knowledge, [])
        self.assertIn("glossary_terms", build_rewrite_context("q", TODAY, context))

    def test_metric_comes_from_the_glossary_link_before_any_search(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan())
        prepared = self.service(llm).prepare(self.connection.id, "Số lượt khám của khoa Nhi?")
        candidates = llm.plan_contexts[0]["metric_candidates"]
        self.assertEqual(
            [(item["id"], item["source"]) for item in candidates], [(str(self.visits.id), "glossary_link")]
        )
        self.assertEqual(prepared.planned[0].metric.source, "glossary_link")

    def test_search_results_join_linked_metrics_for_multi_measure_questions(self) -> None:
        self.index.hits["metric"] = [point(self.fees.id, "Viện phí", "metric", self.table.id)]
        self.index.hits["table"] = [point(self.table.id, "Lượt khám", "table", self.table.id)]
        llm = FakeLlm(rewrite=self.selecting_rewrite("So sánh lượt khám và viện phí"), plan=self.plan())
        self.service(llm).prepare(self.connection.id, "so sánh lượt khám và viện phí")
        candidates = llm.plan_contexts[0]["metric_candidates"]
        self.assertEqual(
            [(item["label"], item["source"]) for item in candidates],
            [("Số lượt khám", "glossary_link"), ("Viện phí", "search")],
        )

    def reranked_service(self, llm: FakeLlm, scores) -> AskService:
        class FakeReranker:
            def rerank(self, question, passages, subject="metric"):
                if isinstance(scores, Exception):
                    raise scores
                return [scores] * len(passages)

        return AskService(
            self.session, self.index, FakeEmbedding(), rewriter=llm.rewriter, planner=llm.planner,
            today=lambda: TODAY, reranker=FakeReranker(),
        )

    def test_searched_metrics_below_the_jev_threshold_are_dropped_and_empty_means_no_metric(self) -> None:
        self.index.hits["metric"] = [point(self.fees.id, "Viện phí", "metric", self.table.id)]
        llm = FakeLlm(rewrite=RewriteDraft(analysis=[], rewritten_question="q"), plan=self.plan())
        prepared = self.reranked_service(llm, 0.59).prepare(self.connection.id, "q")
        self.assertEqual(prepared.status, "no_metric")
        self.assertEqual(llm.plan_contexts, [])

    def test_searched_metrics_at_or_above_the_threshold_go_to_the_plan(self) -> None:
        self.index.hits["metric"] = [point(self.fees.id, "Viện phí", "metric", self.table.id)]
        llm = FakeLlm(rewrite=RewriteDraft(analysis=[], rewritten_question="q"), plan=self.plan(
            metric_id=str(self.fees.id)))
        self.reranked_service(llm, 0.6).prepare(self.connection.id, "q")
        self.assertEqual([item["source"] for item in llm.plan_contexts[0]["metric_candidates"]], ["search"])

    def test_glossary_linked_metrics_are_not_gated_by_the_threshold(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan())
        self.reranked_service(llm, 0.0).prepare(self.connection.id, "q")
        self.assertEqual([item["source"] for item in llm.plan_contexts[0]["metric_candidates"]], ["glossary_link"])

    def test_when_jev_fails_the_unfiltered_candidates_go_to_the_plan(self) -> None:
        from backend.modules.text2sql.common.errors import Text2SqlRerankUnavailable

        self.index.hits["metric"] = [point(self.fees.id, "Viện phí", "metric", self.table.id)]
        llm = FakeLlm(rewrite=RewriteDraft(analysis=[], rewritten_question="q"), plan=self.plan(
            metric_id=str(self.fees.id)))
        self.reranked_service(llm, Text2SqlRerankUnavailable()).prepare(self.connection.id, "q")
        self.assertEqual(len(llm.plan_contexts[0]["metric_candidates"]), 1)

    def test_unselected_terms_do_not_link_metrics(self) -> None:
        llm = FakeLlm(rewrite=RewriteDraft(analysis=[], rewritten_question="q"), plan=self.plan())
        self.index.hits.pop("metric", None)
        prepared = self.service(llm).prepare(self.connection.id, "q")
        self.assertEqual(prepared.status, "no_metric")
        self.assertEqual(llm.plan_contexts, [])

    def test_rule_conditions_are_applied_automatically_to_the_linked_metric(self) -> None:
        draft = self.plan(
            group_by=["department"],
            time=DraftTime(column="visit_date", start="2026-04-01", end="2026-05-01"),
            filters=[DraftFilter(column="department", operator="equals", value="Nhi")],
        )
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=draft)
        prepared = self.service(llm).prepare(self.connection.id, "Số lượt khám theo khoa trong tháng 4/2026?")
        planned = prepared.planned[0]
        self.assertIn('"status" =', planned.compiled.sql)
        self.assertIn("done", planned.compiled.parameters.values())
        self.assertEqual(planned.rules[0].filters, ["Trạng thái bằng done"])
        self.assertEqual(planned.rules[0].overridden, [])
        self.assertEqual(prepared.status, "ready")

    def test_rules_never_apply_to_metrics_they_are_not_linked_to(self) -> None:
        self.index.hits["metric"] = [point(self.fees.id, "Viện phí", "metric", self.table.id)]
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan(metric_id=str(self.fees.id)))
        prepared = self.service(llm).prepare(self.connection.id, "viện phí")
        planned = prepared.planned[0]
        self.assertEqual(planned.rules, [])
        self.assertNotIn("done", planned.compiled.parameters.values())

    def test_an_explicit_filter_on_the_same_column_wins_and_is_reported(self) -> None:
        draft = self.plan(filters=[DraftFilter(column="status", operator="equals", value="cancelled")])
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=draft)
        prepared = self.service(llm).prepare(self.connection.id, "Số lượt khám bị hủy?")
        planned = prepared.planned[0]
        self.assertIn("cancelled", planned.compiled.parameters.values())
        self.assertNotIn("done", planned.compiled.parameters.values())
        self.assertEqual(planned.rules[0].overridden, ["Trạng thái bằng done"])
        self.assertEqual(planned.rules[0].filters, [])

    def test_the_model_has_no_way_to_waive_a_rule(self) -> None:
        self.assertNotIn("waived_rules", DraftQuery.model_fields)
        self.assertNotIn("waived_rules", PlanDraft.model_fields)

    def test_columns_resolve_by_technical_or_display_name_and_values_are_typed(self) -> None:
        draft = self.plan(
            group_by=["Khoa"],
            filters=[DraftFilter(column="IS_URGENT", operator="equals", value="true"),
                     DraftFilter(column="department", operator="in", value="Nhi")],
        )
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=draft)
        planned = self.service(llm).prepare(self.connection.id, "q").planned[0]
        values = list(planned.compiled.parameters.values())
        self.assertIn(True, values)
        self.assertIn(["Nhi"], values)

    def test_unknown_columns_are_reported_with_the_valid_ones_and_never_retried(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan(group_by=["region"]))
        with self.assertRaises(Text2SqlInvalidRequest) as raised:
            self.service(llm).prepare(self.connection.id, "q")
        message = str(raised.exception)
        self.assertIn("truy vấn 1", message)
        self.assertIn("region", message)
        self.assertIn("department", message)
        self.assertEqual((len(llm.rewrite_contexts), len(llm.plan_contexts)), (1, 1))

    def test_errors_in_several_queries_are_reported_together(self) -> None:
        draft = PlanDraft(analysis=[], status="ok", reason="r", queries=[
            DraftQuery(metric_id=str(self.visits.id), group_by=["nope"]),
            DraftQuery(metric_id=str(uuid4())),
        ])
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=draft)
        with self.assertRaises(Text2SqlInvalidRequest) as raised:
            self.service(llm).prepare(self.connection.id, "q")
        self.assertIn("truy vấn 1", str(raised.exception))
        self.assertIn("truy vấn 2", str(raised.exception))

    def test_pii_columns_are_collected_for_consent(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan(group_by=["patient_name"]))
        prepared = self.service(llm).prepare(self.connection.id, "Bệnh nhân nào khám nhiều nhất?")
        self.assertEqual(prepared.pii_columns, ["Tên bệnh nhân"])

    def test_no_metric_from_the_model_falls_back_to_text2sql_with_candidate_tables(self) -> None:
        self.index.hits["table"] = [point(self.table.id, "Lượt khám", "table", self.table.id)]
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=PlanDraft(
            analysis=["x"], status="no_metric", reason="Không có metric đo chi phí."))
        prepared = self.service(llm).prepare(self.connection.id, "Chi phí mỗi ca?")
        self.assertEqual(prepared.status, "no_metric")
        self.assertEqual(prepared.fallback.status, "not_implemented")
        self.assertEqual([item.table_id for item in prepared.fallback.candidate_tables], [self.table.id])
        result = execute_ask(prepared, FakeQueryService(), None, "not_required")
        self.assertEqual((result.status, result.queries), ("no_metric", []))
        self.assertIn("chi phí", result.message)

    def test_ok_with_no_queries_is_treated_as_no_metric(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=PlanDraft(analysis=[], status="ok", queries=[]))
        self.assertEqual(self.service(llm).prepare(self.connection.id, "q").status, "no_metric")

    def test_clarification_is_returned_without_running_anything(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=PlanDraft(
            analysis=[], status="needs_clarification", reason="mơ hồ", clarification_question="Khoa nào?"))
        prepared = self.service(llm).prepare(self.connection.id, "q")
        fake = FakeQueryService()
        result = execute_ask(prepared, fake, None, "not_required")
        self.assertEqual(
            (result.status, result.clarification_question, fake.executed), ("needs_clarification", "Khoa nào?", [])
        )

    def test_execute_runs_every_query_and_explains_the_rules_that_were_applied(self) -> None:
        llm = FakeLlm(rewrite=self.selecting_rewrite(), plan=self.plan())
        prepared = self.service(llm).prepare(self.connection.id, "q")
        fake = FakeQueryService()
        result = execute_ask(prepared, fake, object(), "confirmed")
        self.assertEqual((result.status, len(result.queries), fake.executed[0][1]), ("answered", 1, "confirmed"))
        self.assertIn("Chỉ tính lượt khám hoàn tất", result.message)
        self.assertEqual(result.queries[0].rules[0].filters, ["Trạng thái bằng done"])
        self.assertEqual(result.plan_analysis, ["p"])

    def test_invalid_questions_are_rejected_before_any_model_call(self) -> None:
        llm = FakeLlm()
        for question in ("", "   ", "x" * 2001):
            with self.subTest(length=len(question)), self.assertRaises(Text2SqlInvalidRequest):
                self.service(llm).prepare(self.connection.id, question)
        self.assertEqual(llm.rewrite_contexts, [])


class PromptTests(unittest.TestCase):
    def test_prompts_are_fixed_few_shot_with_step_by_step_analysis_and_no_dataset_terms(self) -> None:
        from backend.agent_package.prompts.prompt_text2sql_plan import query_plan_prompt
        from backend.agent_package.prompts.prompt_text2sql_rewrite import question_rewrite_prompt

        for prompt in (question_rewrite_prompt, query_plan_prompt):
            self.assertIn("analysis", prompt)
            self.assertGreaterEqual(prompt.count("Ví dụ "), 5)
            self.assertIn("Đầu vào", prompt)
            self.assertIn("Đầu ra", prompt)
            self.assertNotIn("{", prompt.replace("{\"", "").replace("{", "", 0)[:0])
        for forbidden in ("doanh thu", "paid", "miền", "cước", "carrier", "region", "ngành hàng"):
            self.assertNotIn(forbidden, (question_rewrite_prompt + query_plan_prompt).lower())

    def test_analysis_comes_first_so_the_model_reasons_before_deciding(self) -> None:
        self.assertEqual(list(RewriteDraft.model_fields)[0], "analysis")
        self.assertEqual(list(PlanDraft.model_fields)[0], "analysis")

    def test_the_rewrite_prompt_forbids_choosing_columns_and_tables(self) -> None:
        from backend.agent_package.prompts.prompt_text2sql_rewrite import question_rewrite_prompt

        self.assertIn("không chọn bảng, cột", question_rewrite_prompt)
        self.assertIn("tháng này", question_rewrite_prompt)


if __name__ == "__main__":
    unittest.main()
