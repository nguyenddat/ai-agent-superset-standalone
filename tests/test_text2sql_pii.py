import threading
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from backend.agent_package.tool_agent import ToolError
from backend.modules.text2sql.repositories.source_query_repository import QueryRows
from langchain_core.messages import HumanMessage

from backend.agent_package.tool_agent import ToolAgentPause
from backend.modules.text2sql.schemas import AgentStepOut, QuestionAnswerOut
from backend.modules.text2sql.services.agent_tools import PII_HINT, QueryCache, Text2SqlToolkit
from backend.modules.text2sql.services.chat_events import UnmaskingEmit
from backend.modules.text2sql.services.chat_graph import PendingQuestion
from backend.modules.text2sql.services.pii_masker import (
    MaskColumn,
    PiiMasker,
    anonymous_placeholders,
    hinted_entities,
    split_placeholder_tail,
)
from tests.test_text2sql_agent import ValueRunner, make_catalog
from tests.test_text2sql_chat import (
    CONNECTION_ID,
    SINGLE_REWRITE,
    FakeAgent,
    FakeCompletion,
    clarifying_service,
    persisted_service,
)


def column(label: str, name: str = "c", flagged: bool = False) -> MaskColumn:
    return MaskColumn(label=label, name=name, flagged=flagged)


def mask_one(value: object, label: str = "Ghi chú", **kwargs) -> object:
    rows, _ = PiiMasker().mask([column(label, **kwargs)], [[value]])
    return rows[0][0]


class ValueDetectionTests(unittest.TestCase):
    def test_vietnamese_mobile_numbers_in_common_formats(self) -> None:
        for number in ("0912345678", "0912 345 678", "091.234.5678", "+84 912 345 678", "+84912345678", "84912345678"):
            with self.subTest(number):
                masked = mask_one(f"gọi {number} nhé")
                self.assertNotIn("912", masked.replace("<", ""))
                self.assertIn("<VN_PHONE_NUMBER_1>", masked)

    def test_email_card_and_ip_inside_free_text(self) -> None:
        masked = mask_one("mail a.nguyen@example.com, thẻ 4111 1111 1111 1111, ip 192.168.1.10")
        self.assertEqual(masked, "mail <EMAIL_ADDRESS_1>, thẻ <CREDIT_CARD_1>, ip <IP_ADDRESS_1>")

    def test_ordinary_business_values_are_left_alone(self) -> None:
        for value in ("Hà Nội", "2026-01", "Q1/2026", "ORD-12345", "1234567890", "100.50", "Bắc", "12345", "x"):
            with self.subTest(value):
                self.assertEqual(mask_one(value), value)

    def test_bare_digit_strings_need_a_hint_from_the_column_name(self) -> None:
        self.assertEqual(mask_one("079201012345", label="Mã đơn"), "079201012345")
        self.assertEqual(mask_one("079201012345", label="Số CCCD"), "<VN_CITIZEN_ID_1>")
        self.assertEqual(mask_one("123456789", label="Số CMND"), "<VN_IDENTITY_CARD_1>")
        self.assertEqual(mask_one("0101234567", label="Mã số thuế"), "<VN_TAX_CODE_1>")
        self.assertEqual(mask_one("0101234567-001", label="MST"), "<VN_TAX_CODE_1>")
        self.assertEqual(mask_one("190012345678", label="Số tài khoản"), "<VN_BANK_ACCOUNT_1>")

    def test_column_hints_ignore_accents_and_case(self) -> None:
        self.assertEqual(hinted_entities("Căn cước công dân", "x"), ["VN_CITIZEN_ID", "VN_IDENTITY_CARD"])
        self.assertEqual(hinted_entities("MÃ SỐ THUẾ", "x"), ["VN_TAX_CODE"])
        self.assertEqual(hinted_entities("Điện thoại", "x"), ["VN_PHONE_NUMBER", "PHONE_NUMBER"])
        self.assertEqual(hinted_entities("Khu vực", "region"), [])
        self.assertEqual(hinted_entities("Liên hệ", "customer_email"), ["EMAIL_ADDRESS"])


class ColumnPolicyTests(unittest.TestCase):
    def test_flagged_column_is_pseudonymized_consistently(self) -> None:
        rows, report = PiiMasker().mask(
            [column("Khách hàng", flagged=True)],
            [["Nguyễn Văn A"], ["Trần Thị B"], ["Nguyễn Văn A"], [None], [""]],
        )
        self.assertEqual([row[0] for row in rows], ["<PII_1>", "<PII_2>", "<PII_1>", None, ""])
        self.assertEqual(report.masked_columns, ["Khách hàng"])
        self.assertEqual(report.detected, {"PII": 2})

    def test_flagged_column_uses_the_specific_entity_when_one_is_recognized(self) -> None:
        rows, _ = PiiMasker().mask([column("Khách hàng", flagged=True)], [["0912345678"], ["Lê Văn C"]])
        self.assertEqual([row[0] for row in rows], ["<VN_PHONE_NUMBER_1>", "<PII_1>"])

    def test_same_value_gets_the_same_placeholder_across_columns_and_rows(self) -> None:
        rows, report = PiiMasker().mask(
            [column("Liên hệ"), column("Ghi chú")],
            [["0912345678", "gọi 0912345678"], ["0987654321", "x"]],
        )
        self.assertEqual(rows[0], ["<VN_PHONE_NUMBER_1>", "gọi <VN_PHONE_NUMBER_1>"])
        self.assertEqual(rows[1], ["<VN_PHONE_NUMBER_2>", "x"])
        self.assertEqual(report.detected, {"VN_PHONE_NUMBER": 2})

    def test_placeholders_are_shared_across_calls_and_reports_count_each_call(self) -> None:
        masker = PiiMasker()
        first, _ = masker.mask([column("Liên hệ")], [["a@example.com"]])
        second, report = masker.mask([column("Liên hệ")], [["b@example.com"], ["a@example.com"]])
        self.assertEqual(first, [["<EMAIL_ADDRESS_1>"]])
        self.assertEqual(second, [["<EMAIL_ADDRESS_2>"], ["<EMAIL_ADDRESS_1>"]])
        self.assertEqual(report.detected, {"EMAIL_ADDRESS": 2})
        _, empty = masker.mask([column("Thành phố")], [["Huế"]])
        self.assertFalse(empty)

    def test_report_never_contains_raw_values(self) -> None:
        _, report = PiiMasker().mask(
            [column("Khách hàng", flagged=True), column("Liên hệ")],
            [["Nguyễn Văn A", "a@example.com"]],
        )
        text = repr(report)
        self.assertNotIn("Nguyễn", text)
        self.assertNotIn("example.com", text)

    def test_flagged_values_of_any_type_are_masked_except_none(self) -> None:
        for value in (912345678, 84912345678, 3.5, True):
            with self.subTest(value=value):
                masked = mask_one(value, label="Số điện thoại", flagged=True)
                self.assertIsInstance(masked, str)
                self.assertNotIn(str(value), masked)
                self.assertTrue(masked.startswith("<") and masked.endswith(">"))
        self.assertIsNone(mask_one(None, flagged=True))

    def test_unflagged_non_string_cells_are_left_as_they_are(self) -> None:
        for value in (912345678, 3.5, True, None):
            with self.subTest(value=value):
                self.assertEqual(mask_one(value, label="Số điện thoại"), value)

    def test_parallel_calls_keep_placeholders_unique(self) -> None:
        masker = PiiMasker()
        results: list[list[list[object]]] = []
        emails = [[f"user{index}@example.com"] for index in range(20)]

        def run() -> None:
            rows, _ = masker.mask([column("Liên hệ")], emails)
            results.append(rows)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(all(rows == results[0] for rows in results))
        self.assertEqual(len({row[0] for row in results[0]}), 20)


class PiiRunner:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.calls: list[str] = []

    def __call__(self, sql: str, max_rows: int) -> QueryRows:
        self.calls.append(sql)
        columns = ["quan_trac_vien", "thanh_pho", "luong_mua"]
        return QueryRows(columns=columns, rows=self.rows, truncated=False, elapsed_ms=1)


class ToolkitMaskingTests(unittest.TestCase):
    def make(self, runner, masker: PiiMasker | None = None) -> Text2SqlToolkit:
        cache = QueryCache(runner=runner, max_rows=200)
        return Text2SqlToolkit(make_catalog(), cache, 50, today=date(2026, 11, 20), masker=masker)

    def test_run_sql_masks_rows_for_the_llm_the_step_and_the_fields(self) -> None:
        runner = PiiRunner([
            ("Nguyễn Văn A", "gọi 0912345678", Decimal(5)),
            ("Trần Thị B", "Huế", Decimal(3)),
        ])
        toolkit = self.make(runner)
        output = toolkit.run_sql("SELECT quan_trac_vien, thanh_pho, luong_mua FROM daily", "xem")
        step = toolkit.steps[0]
        self.assertEqual(step.rows, [["<PII_1>", "gọi <VN_PHONE_NUMBER_1>", 5], ["<PII_2>", "Huế", 3]])
        self.assertEqual([row[:2] for row in output["rows"]], [row[:2] for row in step.rows])
        text = repr(output) + step.model_dump_json()
        self.assertNotIn("Nguyễn", text)
        self.assertNotIn("0912345678", text)
        self.assertTrue(any("Đã che dữ liệu cá nhân" in note for note in output["notes"]))
        self.assertIn("Quan trắc viên", step.notes[-1])
        self.assertIn(PII_HINT, output["notes"])
        self.assertNotIn(PII_HINT, step.notes)
        field = next(item for item in step.fields if item.name == "quan_trac_vien")
        self.assertEqual((field.type, field.role, field.pii), ("text", "dimension", True))

    def test_flagged_numeric_column_becomes_a_text_field(self) -> None:
        runner = PiiRunner([(123, "Huế", Decimal(5))])
        toolkit = self.make(runner)
        toolkit.run_sql("SELECT quan_trac_vien, thanh_pho, luong_mua FROM daily", "xem")
        step = toolkit.steps[0]
        self.assertEqual(step.rows[0][0], "<PII_1>")
        field = next(item for item in step.fields if item.name == "quan_trac_vien")
        self.assertEqual(field.type, "text")

    def test_results_without_personal_data_are_unchanged_and_carry_no_note(self) -> None:
        runner = PiiRunner([(None, "Huế", Decimal(5))])
        toolkit = self.make(runner)
        output = toolkit.run_sql("SELECT quan_trac_vien, thanh_pho, luong_mua FROM daily", "xem")
        self.assertEqual(toolkit.steps[0].rows, [[None, "Huế", 5]])
        self.assertFalse(any("Đã che" in note for note in output.get("notes", [])))

    def test_one_masker_keeps_labels_consistent_across_questions(self) -> None:
        masker = PiiMasker()
        rows = [("Nguyễn Văn A", "Huế", Decimal(5))]
        first = self.make(PiiRunner(rows), masker)
        second = self.make(PiiRunner([("Trần Thị B", "Huế", Decimal(1)), *rows]), masker)
        first.run_sql("SELECT quan_trac_vien, thanh_pho, luong_mua FROM daily", "a")
        second.run_sql("SELECT quan_trac_vien, thanh_pho, luong_mua FROM daily", "b")
        self.assertEqual(first.steps[0].rows[0][0], "<PII_1>")
        self.assertEqual([row[0] for row in second.steps[0].rows], ["<PII_2>", "<PII_1>"])

    def test_column_values_are_masked(self) -> None:
        toolkit = self.make(ValueRunner(["a@example.com", "Huế"]))
        output = toolkit.get_column_values("daily", "thanh_pho")
        self.assertEqual(output["rows"], [["<EMAIL_ADDRESS_1>"], ["Huế"]])
        self.assertTrue(any("Đã che" in note for note in output["notes"]))

    def test_value_hints_in_errors_are_masked(self) -> None:
        toolkit = self.make(ValueRunner(["a@example.com", "Huế"]))
        with self.assertRaises(ToolError) as caught:
            toolkit.query_metric(
                metric="tong_luong_mua", filters=[{"column": "thanh_pho", "operator": "equals", "value": "Vinh"}],
            )
        self.assertNotIn("example.com", str(caught.exception))
        self.assertIn("<EMAIL_ADDRESS_1>", str(caught.exception))



class UnmaskTests(unittest.TestCase):
    masker = PiiMasker(values={"<PII_1>": "Nguyễn Văn An", "<VN_PHONE_NUMBER_1>": "0912345678"})

    def test_placeholders_become_real_values_in_any_markdown_form(self) -> None:
        cases = {
            "**<PII_1>** gọi <VN_PHONE_NUMBER_1>": "**Nguyễn Văn An** gọi 0912345678",
            r"\<PII\_1\> và \<VN\_PHONE\_NUMBER\_1\>": "Nguyễn Văn An và 0912345678",
            "`<PII_1>`": "Nguyễn Văn An",
        }
        for masked, shown in cases.items():
            with self.subTest(masked):
                self.assertEqual(self.masker.unmask(masked), shown)

    def test_unknown_labels_and_ordinary_text_are_kept(self) -> None:
        for text in ("<PII_9> mua nhiều", "nhiệt độ < 20 °C", "<kết quả câu 1>", "a <b> c"):
            with self.subTest(text):
                self.assertEqual(self.masker.unmask(text), text)

    def test_restored_masker_continues_numbering_and_reuses_labels(self) -> None:
        restored = PiiMasker(values=self.masker.values)
        rows, _ = restored.mask([column("Khách", flagged=True)], [["Trần Thị B"], ["Nguyễn Văn An"]])
        self.assertEqual(rows, [["<PII_2>"], ["<PII_1>"]])

    def test_history_drops_label_numbers(self) -> None:
        self.assertEqual(
            anonymous_placeholders(r"**<PII_1>** gọi \<VN\_PHONE\_NUMBER\_2\>"), "**<PII>** gọi <VN_PHONE_NUMBER>",
        )

    def test_stream_tail_holds_only_a_possible_label_start(self) -> None:
        self.assertEqual(split_placeholder_tail("xin chào <PI"), ("xin chào ", "<PI"))
        self.assertEqual(split_placeholder_tail("gọi \\"), ("gọi ", "\\"))
        self.assertEqual(split_placeholder_tail("giá < 20 nhé"), ("giá < 20 nhé", ""))
        self.assertEqual(split_placeholder_tail("xong <PII_1>"), ("xong <PII_1>", ""))


class UnmaskingEmitTests(unittest.TestCase):
    def make(self) -> tuple[UnmaskingEmit, list]:
        sent: list = []
        masker = PiiMasker(values={"<PII_1>": "Nguyễn Văn An", "<PII_2>": "Trần Thị B"})
        return UnmaskingEmit(lambda event, data: sent.append((event, data)), masker), sent

    def delta(self, text: str, position: int | None = 1, round_: int = 0) -> dict:
        return {"position": position, "round": round_, "final": False, "text": text}

    def test_label_split_across_deltas_is_unmasked_once_complete(self) -> None:
        emit, sent = self.make()
        for piece in ("Người mưa nhiều nhất là <PI", "I_1", "> rồi đến <PII_2>."):
            emit("answer_delta", self.delta(piece))
        self.assertEqual(
            "".join(data["text"] for _, data in sent), "Người mưa nhiều nhất là Nguyễn Văn An rồi đến Trần Thị B.",
        )
        self.assertFalse(any("<" in data["text"] for _, data in sent))

    def test_streams_of_different_questions_do_not_mix(self) -> None:
        emit, sent = self.make()
        emit("answer_delta", self.delta("A <PII", position=1))
        emit("answer_delta", self.delta("B <PII_2>", position=2))
        emit("answer_delta", self.delta("_1>", position=1))
        self.assertEqual(
            [(data["position"], data["text"]) for _, data in sent],
            [(1, "A "), (2, "B Trần Thị B"), (1, "Nguyễn Văn An")],
        )

    def test_reset_drops_the_held_tail(self) -> None:
        emit, sent = self.make()
        emit("answer_delta", self.delta("bỏ <PII"))
        emit("answer_reset", {"position": 1, "round": 0})
        emit("answer_delta", self.delta("_1> mới", round_=1))
        self.assertEqual([data["text"] for event, data in sent if event == "answer_delta"], ["bỏ ", "_1> mới"])

    def test_text_events_are_unmasked_and_others_untouched(self) -> None:
        emit, sent = self.make()
        emit("answer", {"answer": "<PII_1> nhiều nhất"})
        emit("question_answered", {"position": 1, "question": "q", "answer": "<PII_2>", "exhausted": False})
        emit("question_waiting", {"position": 2, "question": "Ý bạn là <PII_1>?", "options": ["<PII_1>", "Khác"]})
        emit("preprocess", {"rewritten_question": "<PII_1>"})
        self.assertEqual(sent[0][1]["answer"], "Nguyễn Văn An nhiều nhất")
        self.assertEqual(sent[1][1]["answer"], "Trần Thị B")
        self.assertEqual(sent[2][1]["question"], "Ý bạn là Nguyễn Văn An?")
        self.assertEqual(sent[2][1]["options"], ["Nguyễn Văn An", "Khác"])
        self.assertEqual(sent[3][1]["rewritten_question"], "<PII_1>")

    def test_tool_rows_chart_and_explanations_are_unmasked_but_sql_is_kept(self) -> None:
        emit, sent = self.make()
        emit("tool", {
            "position": 1, "sql": "SELECT '<PII_1>'", "arguments": {"sql": "SELECT '<PII_1>'"},
            "rows": [["<PII_1>", 5], ["gọi <PII_2>", None]],
            "chart": {"title": "Mưa của <PII_1>", "colors": {"assign": {"<PII_2>": "c1"}, "highlight": ["<PII_1>"]}},
            "explanations": [{"kind": "group", "text": "Theo <PII_1>"}],
        })
        data = sent[0][1]
        self.assertEqual(data["rows"], [["Nguyễn Văn An", 5], ["gọi Trần Thị B", None]])
        self.assertEqual(data["chart"]["title"], "Mưa của Nguyễn Văn An")
        self.assertEqual(data["chart"]["colors"], {"assign": {"Trần Thị B": "c1"}, "highlight": ["Nguyễn Văn An"]})
        self.assertEqual(data["explanations"][0]["text"], "Theo Nguyễn Văn An")
        self.assertEqual((data["sql"], data["arguments"]["sql"]), ("SELECT '<PII_1>'", "SELECT '<PII_1>'"))


class PiiAgent(FakeAgent):
    def start(self, connection_id):
        self.run = super().start(connection_id)
        return self.run

    @property
    def masker(self) -> PiiMasker:
        # Đọc lúc trả lời như AgentRun thật: lượt chạy tiếp được gán masker đã khôi phục sau start().
        return self.run.masker

    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        self.prior[item.position] = [
            (answer.answer, [step.rows for step in answer.steps], [step.chart for step in answer.steps])
            for answer in prior
        ]
        rows, _ = self.masker.mask([MaskColumn("Khách hàng", "khach_hang", True)], [[f"Khách {item.position}"]])
        label = rows[0][0]
        step = AgentStepOut(
            tool="run_sql", arguments={"sql": "SELECT khach_hang"}, sql="SELECT khach_hang", columns=["khach_hang"],
            rows=rows, row_count=1, result_id=f"{item.position}-1", chart={"type": "table", "title": f"Đơn của {label}"},
        )
        return QuestionAnswerOut(
            position=item.position, question=item.question, answer=f"{label} mua nhiều nhất", steps=[step],
        )


class ChatUnmaskTests(unittest.TestCase):
    def test_tables_and_charts_are_unmasked_for_the_user_but_not_for_the_next_question(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        agent = PiiAgent()
        service, _, conversations = persisted_service(FakeCompletion(), owned, agent=agent)
        result = service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        step = result.answers[0].steps[0]
        self.assertEqual((step.rows, step.chart["title"]), ([["Khách 1"]], "Đơn của Khách 1"))
        self.assertEqual(step.sql, "SELECT khach_hang")
        self.assertEqual(conversations.completed["results"][0]["rows"], [["Khách 1"]])
        self.assertEqual(conversations.completed["results"][0]["chart"]["title"], "Đơn của Khách 1")
        self.assertEqual(conversations.completed["steps"][0]["steps"][0]["chart"]["title"], "Đơn của Khách 1")
        masked_chart = {"type": "table", "title": "Đơn của <PII_1>"}
        self.assertEqual(agent.prior[2], [("<PII_1> mua nhiều nhất", [[["<PII_1>"]]], [masked_chart])])

    def test_answer_is_unmasked_for_the_user_and_kept_masked_for_history(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        service, _, conversations = persisted_service(FakeCompletion(rewrite=SINGLE_REWRITE), owned, agent=PiiAgent())
        result = service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        self.assertEqual(result.answer, "Khách 1 mua nhiều nhất")
        self.assertEqual(result.answers[0].answer, "Khách 1 mua nhiều nhất")
        self.assertEqual(result.history_answer, "<PII> mua nhiều nhất")
        stored = conversations.completed
        self.assertEqual(stored["answer"], "Khách 1 mua nhiều nhất")
        self.assertEqual(stored["steps"][0]["answer"], "Khách 1 mua nhiều nhất")
        self.assertEqual(stored["pii"], {"history_answer": "<PII> mua nhiều nhất"})

    def test_answers_without_personal_data_have_no_history_answer(self) -> None:
        owned = SimpleNamespace(id=uuid4(), connection_id=CONNECTION_ID, user_id="user-1")
        service, _, conversations = persisted_service(FakeCompletion(rewrite=SINGLE_REWRITE), owned)
        result = service.chat(CONNECTION_ID, "câu hỏi", [], "user-1", owned.id)
        self.assertIsNone(result.history_answer)
        self.assertIsNone(conversations.completed["pii"])


class PausingPiiAgent(PiiAgent):
    def __init__(self) -> None:
        super().__init__()
        self.labels: list[str] = []

    def answer(self, preprocess, item, prior, pending=None, reply=None, emit=None):
        if item.position == 2 and pending is None:
            rows, _ = self.masker.mask([MaskColumn("Khách hàng", "khach_hang", True)], [["Khách 1"]])
            question = f"Ý bạn là {rows[0][0]}?"
            pause = ToolAgentPause("ask", "ask_user", {"question": question}, [HumanMessage("ngữ cảnh")], 1)
            step = AgentStepOut(tool="ask_user", arguments={"question": question})
            return PendingQuestion(item.position, question, [rows[0][0]], pause, [step])
        name = "Khách 1" if item.position == 1 else "Khách 2"
        rows, _ = self.masker.mask([MaskColumn("Khách hàng", "khach_hang", True)], [[name]])
        self.labels.append(rows[0][0])
        return QuestionAnswerOut(position=item.position, question=item.question, answer=f"{rows[0][0]} mua nhiều nhất")


class ClarificationUnmaskTests(unittest.TestCase):
    def test_resumed_turn_reuses_the_labels_of_the_paused_turn(self) -> None:
        agent = PausingPiiAgent()
        service, _, _, checkpoints = clarifying_service(agent)
        paused = service.chat(CONNECTION_ID, "câu hỏi", [])
        self.assertEqual(paused.answer, "Ý bạn là Khách 1?")
        self.assertEqual(paused.clarification_options, ["Khách 1"])
        self.assertEqual(checkpoints.rows[paused.resume_id].masked_values, {"<PII_1>": "Khách 1"})
        resumed = service.chat(CONNECTION_ID, "đúng", [], resume_id=paused.resume_id)
        self.assertEqual(agent.labels, ["<PII_1>", "<PII_2>"])
        self.assertEqual(resumed.answer, "Khách 1 mua nhiều nhất / Khách 2 mua nhiều nhất")
        self.assertEqual(resumed.history_answer, "<PII> mua nhiều nhất / <PII> mua nhiều nhất")


if __name__ == "__main__":
    unittest.main()
