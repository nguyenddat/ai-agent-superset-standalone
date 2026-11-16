import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlglot import exp

from backend.common.base_exceptions import AppError
from backend.modules.text2sql.dataset.expression import parse_dataset_expression
from backend.modules.text2sql.query.expression import compile_metric_expression
from backend.modules.text2sql.query.pii import MaskColumn, PiiMasker
from backend.modules.text2sql.query.service import format_cell

masker = PiiMasker()


def mask_column(value: object, flagged: bool, scan: bool = True, label: str = "Số điện thoại") -> list[list[object]]:
    column = MaskColumn(label=label, name="phone", scan=scan, flagged=flagged)
    rows, _ = masker.mask([column], [[format_cell(value)]])
    return rows


class FlaggedNonStringTests(unittest.TestCase):
    def test_flagged_values_of_any_type_are_masked(self) -> None:
        for value in (912345678, 84912345678, 3.5, True, Decimal("123.45"), date(1990, 1, 2)):
            with self.subTest(value=value):
                masked = mask_column(value, flagged=True)[0][0]
                self.assertIsInstance(masked, str)
                self.assertNotIn(str(value), masked)
                self.assertTrue(masked.startswith("<") and masked.endswith(">"))

    def test_same_number_gets_same_placeholder(self) -> None:
        column = MaskColumn(label="Số điện thoại", name="phone", scan=True, flagged=True)
        rows, report = masker.mask([column], [[912345678], [912345678], [987654321]])
        self.assertEqual(rows[0][0], rows[1][0])
        self.assertNotEqual(rows[0][0], rows[2][0])
        self.assertEqual(report.masked_columns, ["Số điện thoại"])

    def test_flagged_column_masked_even_without_scan(self) -> None:
        self.assertNotEqual(mask_column(912345678, flagged=True, scan=False)[0][0], 912345678)

    def test_none_stays_none(self) -> None:
        self.assertIsNone(mask_column(None, flagged=True)[0][0])

    def test_unflagged_numbers_untouched(self) -> None:
        for value in (912345678, 3.5, True):
            with self.subTest(value=value):
                self.assertEqual(mask_column(value, flagged=False)[0][0], value)


def resolve(table: str, name: str) -> exp.Column:
    return exp.column(name, table=table)


class DeepNestingTests(unittest.TestCase):
    def test_dataset_expression_deep_parens_is_business_error(self) -> None:
        text = "(" * 300 + "orders.total" + ")" * 300
        self.assertLess(len(text), 2000)
        with self.assertRaises(AppError):
            parse_dataset_expression(text, resolve)

    def test_metric_expression_deep_parens_is_business_error(self) -> None:
        text = "SUM(" + "(" * 300 + "total" + ")" * 300 + ")"
        self.assertLess(len(text), 2000)
        with self.assertRaises(AppError):
            compile_metric_expression(text, {"total": (uuid4(), "total")})


class CastCharTests(unittest.TestCase):
    def test_cast_char_rejected_in_metric(self) -> None:
        with self.assertRaises(AppError):
            compile_metric_expression("SUM(CAST(total AS CHAR))", {"total": (uuid4(), "total")})

    def test_cast_char_rejected_in_dataset(self) -> None:
        with self.assertRaises(AppError):
            parse_dataset_expression("CAST(orders.total AS CHAR)", resolve)

    def test_cast_varchar_still_allowed(self) -> None:
        parse_dataset_expression("CAST(orders.total AS VARCHAR)", resolve)


if __name__ == "__main__":
    unittest.main()
