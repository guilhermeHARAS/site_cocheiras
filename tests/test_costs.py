import sys
import unittest
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from costs import parse_expense_notes, parse_expense_spreadsheet, parse_expense_text, validate_expense


class CostValidationTests(unittest.TestCase):
    def test_brazilian_amount_is_stored_in_cents(self):
        expense = validate_expense({"amount": "R$ 1.200,50", "date": "2026-10-18"})
        self.assertEqual(expense["amountCents"], 120050)

    def test_horse_scope_requires_a_horse(self):
        with self.assertRaisesRegex(ValueError, "Selecione o cavalo"):
            validate_expense({"amount": "50", "date": "2026-10-18", "scope": "horse"})

    def test_monthly_expense_keeps_recurrence_day(self):
        expense = validate_expense({"amount": "350", "date": "2026-10-18", "recurring": True})
        self.assertTrue(expense["recurring"])
        self.assertEqual(expense["recurrenceDay"], 18)


class SmartCostParserTests(unittest.TestCase):
    def setUp(self):
        self.horses = [{"id": "horse-1", "name": "Trovão"}]

    def test_understands_value_category_horse_and_relative_date(self):
        result = parse_expense_text(
            "Veterinário, R$ 480 para Trovão ontem",
            self.horses,
            reference_date="2026-10-18",
        )
        self.assertEqual(result["draft"]["amountCents"], 48000)
        self.assertEqual(result["draft"]["category"], "veterinary")
        self.assertEqual(result["draft"]["horseId"], "horse-1")
        self.assertEqual(result["draft"]["date"], "2026-10-17")

    def test_understands_general_stable_cost(self):
        result = parse_expense_text(
            "Ração 1.200 reais para a cocheira hoje",
            self.horses,
            reference_date="2026-10-18",
        )
        self.assertEqual(result["draft"]["amountCents"], 120000)
        self.assertEqual(result["draft"]["category"], "food")
        self.assertEqual(result["draft"]["scope"], "general")

    def test_detects_monthly_cost(self):
        result = parse_expense_text("Ração R$ 1.200 mensal", [], reference_date="2026-10-18")
        self.assertTrue(result["draft"]["recurring"])

    def test_does_not_confuse_date_with_amount(self):
        result = parse_expense_text("18/10/2026 ração 1.200 reais", [], reference_date="2026-10-18")
        self.assertEqual(result["draft"]["amountCents"], 120000)


class CostImportTests(unittest.TestCase):
    def test_reads_notes_as_separate_costs(self):
        result = parse_expense_notes(
            "Ração R$ 1.200 mensal\nVeterinário R$ 480 em 17/10/2026",
            reference_date="2026-10-18",
        )
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["amountCents"], 120000)
        self.assertTrue(result["records"][0]["recurring"])
        self.assertEqual(result["records"][1]["category"], "veterinary")

    def test_reads_csv_with_flexible_headers(self):
        raw = "Descrição;Custo;Data;Tipo;Fixa\nRação;1200,50;18/10/2026;Alimentação;sim\n".encode("utf-8")
        result = parse_expense_spreadsheet(
            "custos.csv",
            base64.b64encode(raw).decode("ascii"),
            reference_date="2026-10-18",
        )
        record = result["records"][0]
        self.assertEqual(record["amountCents"], 120050)
        self.assertEqual(record["category"], "food")
        self.assertTrue(record["recurring"])


if __name__ == "__main__":
    unittest.main()
