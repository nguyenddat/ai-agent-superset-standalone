import unittest

from backend.modules.text2sql.query.pii import MaskColumn, PiiMasker, hinted_entities

masker = PiiMasker()


def column(label: str, name: str = "c", scan: bool = True, flagged: bool = False) -> MaskColumn:
    return MaskColumn(label=label, name=name, scan=scan, flagged=flagged)


def mask_one(value: str, label: str = "Ghi chú", **kwargs) -> str:
    rows, _ = masker.mask([column(label, **kwargs)], [[value]])
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
        rows, report = masker.mask(
            [column("Khách hàng", flagged=True)],
            [["Nguyễn Văn A"], ["Trần Thị B"], ["Nguyễn Văn A"], [None], [""]],
        )
        self.assertEqual([row[0] for row in rows], ["<PII_1>", "<PII_2>", "<PII_1>", None, ""])
        self.assertEqual(report.masked_columns, ["Khách hàng"])
        self.assertEqual(report.detected, {"PII": 2})

    def test_flagged_column_uses_the_specific_entity_when_one_is_recognized(self) -> None:
        rows, _ = masker.mask([column("Khách hàng", flagged=True)], [["0912345678"], ["Lê Văn C"]])
        self.assertEqual([row[0] for row in rows], ["<VN_PHONE_NUMBER_1>", "<PII_1>"])

    def test_same_value_gets_the_same_placeholder_across_columns_and_rows(self) -> None:
        rows, report = masker.mask(
            [column("Liên hệ"), column("Ghi chú")],
            [["0912345678", "gọi 0912345678"], ["0987654321", "x"]],
        )
        self.assertEqual(rows[0], ["<VN_PHONE_NUMBER_1>", "gọi <VN_PHONE_NUMBER_1>"])
        self.assertEqual(rows[1], ["<VN_PHONE_NUMBER_2>", "x"])
        self.assertEqual(report.detected, {"VN_PHONE_NUMBER": 2})

    def test_unscanned_columns_such_as_metrics_are_never_touched(self) -> None:
        rows, report = masker.mask([column("Doanh thu", scan=False), column("Khu vực")], [["0912345678", "Bắc"]])
        self.assertEqual(rows[0], ["0912345678", "Bắc"])
        self.assertEqual(report.detected, {})

    def test_report_never_contains_raw_values(self) -> None:
        _, report = masker.mask(
            [column("Khách hàng", flagged=True), column("Liên hệ")],
            [["Nguyễn Văn A", "a@example.com"]],
        )
        text = repr(report)
        self.assertNotIn("Nguyễn", text)
        self.assertNotIn("example.com", text)

    def test_flagged_non_string_cells_are_masked_except_none(self) -> None:
        rows, _ = masker.mask([column("Số lượng", flagged=True)], [[5], [None]])
        self.assertEqual([row[0] for row in rows], ["<PII_1>", None])

    def test_unflagged_non_string_cells_are_left_as_they_are(self) -> None:
        rows, _ = masker.mask([column("Số lượng")], [[5], [None]])
        self.assertEqual([row[0] for row in rows], [5, None])


if __name__ == "__main__":
    unittest.main()
