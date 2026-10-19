import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from assistant import answer_question


class AuditAssistantTests(unittest.TestCase):
    def setUp(self):
        self.horses = [
            {"id": "1", "name": "Persa", "stage": "training", "father": "Trovão", "mother": "", "owner": "", "age": None},
            {"id": "2", "name": "persa", "stage": "foals", "father": "Trovão", "mother": "Lua", "owner": "Caio", "age": 2},
            {"id": "3", "name": "Futuro", "stage": "ready", "birthDate": "2027-01-01", "owner": "Caio"},
        ]
        self.expenses = [
            {"id": "e1", "date": "2026-10-01", "category": "food", "amountCents": 10000, "description": "Ração"},
            {"id": "e2", "date": "2026-10-01", "category": "food", "amountCents": 10000, "description": "Ração"},
            {"id": "e3", "date": "2026-10-02", "category": "other", "amountCents": 100000, "description": "Compra especial"},
        ]

    def ask(self, question):
        return answer_question(self.horses, question, expenses=self.expenses, reference_date="2026-10-18")

    def test_full_audit_finds_duplicates_and_missing_data(self):
        result = self.ask("Faça uma auditoria dos dados")
        self.assertEqual(result["intent"], "audit")
        self.assertIn("2 cadastros", result["answer"])
        self.assertIn("sem idade", result["answer"])
        self.assertIn("nascimento no futuro", result["answer"])

    def test_specific_duplicate_question(self):
        result = self.ask("Existem cavalos duplicados?")
        self.assertEqual(result["matches"], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
