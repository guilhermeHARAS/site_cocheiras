import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from assistant import answer_question


class FinanceAssistantTests(unittest.TestCase):
    def setUp(self):
        self.horses = [
            {"id": "h1", "name": "Aurora", "stage": "training"},
            {"id": "h2", "name": "Raio", "stage": "foals"},
            {"id": "h3", "name": "Sol", "stage": "ready"},
            {"id": "h4", "name": "Futuro", "stage": "creation"},
        ]
        self.expenses = [
            {"id": "e1", "date": "2026-10-03", "amountCents": 100000, "category": "food", "description": "Ração premium", "recurring": False},
            {"id": "e2", "date": "2026-10-12", "amountCents": 50000, "category": "veterinary", "description": "Consulta", "recurring": False},
            {"id": "e3", "date": "2026-09-10", "amountCents": 20000, "category": "training", "description": "Instrutor", "recurring": True, "recurrenceDay": 10},
            {"id": "e4", "date": "2026-09-05", "amountCents": 10000, "category": "other", "description": "Sela nova", "recurring": False},
        ]

    def ask(self, question):
        return answer_question(self.horses, question, expenses=self.expenses, reference_date="2026-10-18")

    def test_total_for_current_month_includes_recurring_projection(self):
        result = self.ask("Quanto gastamos este mês?")
        self.assertEqual(result["intent"], "costs")
        self.assertIn("R$ 1.700,00", result["answer"])

    def test_total_by_category(self):
        result = self.ask("Quanto gastei com ração em outubro de 2026?")
        self.assertIn("R$ 1.000,00", result["answer"])
        self.assertIn("Alimentação", result["answer"])

    def test_cost_per_horse_excludes_creation(self):
        result = self.ask("Qual o custo médio por cavalo este mês?")
        self.assertIn("R$ 566,67", result["answer"])
        self.assertIn("3 cavalos", result["answer"])

    def test_lists_fixed_expenses(self):
        result = self.ask("Quais são as despesas fixas deste mês?")
        self.assertIn("Instrutor", result["answer"])
        self.assertIn("R$ 200,00", result["answer"])

    def test_compares_with_previous_month(self):
        result = self.ask("Compare este mês com o mês passado")
        self.assertIn("R$ 1.700,00", result["answer"])
        self.assertIn("R$ 300,00", result["answer"])
        self.assertIn("aumento", result["answer"])

    def test_projects_next_month_from_fixed_expenses_only(self):
        result = self.ask("Quanto vamos gastar no próximo mês?")
        self.assertIn("faixa provável", result["answer"])
        self.assertIn("despesas fixas", result["answer"])

    def test_searches_free_text_in_description(self):
        result = self.ask("Quanto gastamos com sela em setembro de 2026?")
        self.assertIn("R$ 100,00", result["answer"])
        self.assertIn("Sela nova", result["answer"])

    def test_shows_category_distribution(self):
        result = self.ask("Como os custos deste mês estão distribuídos por categoria?")
        self.assertIn("Alimentação", result["answer"])
        self.assertIn("Veterinário", result["answer"])
        self.assertIn("Treinamento", result["answer"])

    def test_does_not_mutate_financial_records(self):
        before = copy.deepcopy(self.expenses)
        self.ask("Qual foi a maior despesa deste mês?")
        self.assertEqual(self.expenses, before)

    def test_remembers_period_for_follow_up(self):
        first = self.ask("Quanto gastamos em outubro de 2026?")
        second = answer_question(
            self.horses,
            "E somente com veterinário?",
            expenses=self.expenses,
            context=first["context"],
            reference_date="2026-10-18",
        )
        self.assertIn("Outubro de 2026", second["answer"])
        self.assertIn("R$ 500,00", second["answer"])

    def test_warns_about_large_category_increases(self):
        result = self.ask("Quais custos aumentaram muito este mês?")
        self.assertIn("Alertas de aumento", result["answer"])
        self.assertIn("Alimentação", result["answer"])

    def test_administrative_suggestions_are_not_promises(self):
        result = self.ask("Dê sugestões para economizar este mês")
        self.assertIn("não garantias", result["answer"])
        self.assertIn("revisar", result["answer"])

    def test_annual_forecast_has_range(self):
        result = self.ask("Faça uma projeção de custos para este ano")
        self.assertIn("faixa provável", result["answer"])
        self.assertIn("estimativas", result["answer"])

    def test_report_question_offers_pdf_and_xlsx(self):
        result = self.ask("Faça um relatório financeiro de outubro de 2026")
        self.assertEqual([action["format"] for action in result["actions"]], ["pdf", "xlsx"])
        self.assertEqual(result["actions"][0]["period"], "2026-10")


if __name__ == "__main__":
    unittest.main()
