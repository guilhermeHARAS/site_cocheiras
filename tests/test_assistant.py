import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from assistant import answer_question


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.horses = [
            {"id": "1", "name": "Aurora", "father": "Trovão", "mother": "Estrela", "stage": "training", "workouts": 80, "age": 3, "ageRecordedAt": "2026-10-13", "location": "Baia 7"},
            {"id": "2", "name": "Raio", "father": "Trovão", "mother": "Lua", "stage": "foals", "workouts": 0, "birthDate": "2026-04-13"},
            {"id": "3", "name": "Sol", "father": "Vento", "mother": "Estrela", "stage": "ready", "workouts": 72, "age": 5, "ageRecordedAt": "2025-01-01"},
        ]

    def test_ambiguous_parent_question_offers_choices(self):
        result = answer_question(self.horses, "Quais cavalos são filhos de Trovão?")
        self.assertEqual(result["intent"], "clarification")
        self.assertEqual([option["label"] for option in result["options"]], ["Como pai", "Como mãe", "Pai ou mãe"])

    def test_finds_children_by_either_parent_after_choice(self):
        result = answer_question(self.horses, "Mostrar filhos de Trovão como pai ou mãe")
        self.assertEqual(result["matches"], ["1", "2"])
        self.assertIn("Aurora", result["answer"])
        self.assertIn("Raio", result["answer"])

    def test_counts_children_of_explicit_father(self):
        result = answer_question(self.horses, "Quantos filhos tem o pai Trovão?")
        self.assertEqual(result["matches"], ["1", "2"])
        self.assertIn("2 filhos", result["answer"])

    def test_filters_children_by_stage(self):
        result = answer_question(self.horses, "Quais filhos do pai Trovão estão em treinamento?")
        self.assertEqual(result["matches"], ["1"])

    def test_can_limit_parent_search_to_mother(self):
        result = answer_question(self.horses, "Quais são os filhos da égua Estrela?")
        self.assertEqual(result["matches"], ["1", "3"])

    def test_counts_children_of_explicit_mother(self):
        result = answer_question(self.horses, "Quantos filhos a mãe Estrela tem?")
        self.assertEqual(result["matches"], ["1", "3"])
        self.assertIn("2 filhos cadastrados como mãe", result["answer"])

    def test_answers_stage_count(self):
        result = answer_question(self.horses, "Quantos cavalos estão em treinamento?")
        self.assertEqual(result["answer"], "Há 1 registro na etapa Preparação e Treinamento.")

    def test_answers_counts_for_every_stage(self):
        result = answer_question(self.horses, "Quantos cavalos existem em cada etapa?")
        self.assertIn("Reprodução: 0", result["answer"])
        self.assertIn("Potros e Desenvolvimento: 1", result["answer"])
        self.assertIn("Preparação e Treinamento: 1", result["answer"])
        self.assertIn("Tropa pronta: 1", result["answer"])

    def test_reports_horses_that_reached_goal(self):
        result = answer_question(self.horses, "Quem já atingiu 80 treinos?")
        self.assertEqual(result["matches"], ["1"])

    def test_ambiguous_birth_period_offers_expected_or_actual(self):
        result = answer_question(self.horses, "Quais são os nascimentos de outubro de 2026?")
        self.assertEqual(result["intent"], "clarification")
        self.assertEqual([option["label"] for option in result["options"]], ["Nascimentos previstos", "Animais que nasceram"])

    def test_filters_expected_births_by_month_and_year(self):
        horses = self.horses + [
            {"id": "4", "name": "Outubro", "stage": "creation", "expectedBirthDate": "2027-10-18"},
            {"id": "5", "name": "Novembro", "stage": "creation", "expectedBirthDate": "2027-11-02"},
        ]
        result = answer_question(horses, "Quais são os nascimentos previstos em outubro de 2027?")
        self.assertEqual(result["matches"], ["4"])
        self.assertIn("18/10/2027", result["answer"])
        self.assertNotIn("Novembro", result["answer"])

    def test_filters_expected_births_by_numeric_month_and_year(self):
        horses = self.horses + [
            {"id": "4", "name": "Numérico", "stage": "creation", "expectedBirthDate": "2028-11-18"},
        ]
        result = answer_question(horses, "Nascimentos previstos em 11/2028")
        self.assertEqual(result["matches"], ["4"])
        self.assertIn("Novembro de 2028", result["answer"])

    def test_filters_births_from_current_month(self):
        horses = self.horses + [
            {"id": "4", "name": "Do mês", "stage": "creation", "expectedBirthDate": "2026-10-20"},
            {"id": "5", "name": "Depois", "stage": "creation", "expectedBirthDate": "2026-11-02"},
        ]
        result = answer_question(horses, "Quantos nascimentos previstos existem neste mês?", reference_date="2026-10-13")
        self.assertEqual(result["matches"], ["4"])
        self.assertIn("1 nascimento previsto", result["answer"])

    def test_filters_actual_births_by_year(self):
        horses = self.horses + [
            {"id": "4", "name": "Antigo", "stage": "foals", "birthDate": "2025-12-20"},
        ]
        result = answer_question(horses, "Quais animais nasceram em 2026?")
        self.assertEqual(result["matches"], ["2"])
        self.assertIn("Raio", result["answer"])

    def test_informed_age_progresses(self):
        result = answer_question(self.horses, "Qual a idade de Aurora?", reference_date="2027-10-13")
        self.assertIn("4 anos", result["answer"])

    def test_exact_birth_date_reports_years_and_months(self):
        result = answer_question(self.horses, "Qual a idade de Raio?", reference_date="2027-10-13")
        self.assertIn("1 ano e 6 meses", result["answer"])

    def test_answers_current_location(self):
        result = answer_question(self.horses, "Onde está Aurora?")
        self.assertEqual(result["intent"], "location")
        self.assertEqual(result["matches"], ["1"])
        self.assertIn("Baia 7", result["answer"])

    def test_reports_missing_location_without_inventing_it(self):
        result = answer_question(self.horses, "Qual a localização de Raio?")
        self.assertEqual(result["intent"], "location")
        self.assertIn("ainda não foi informada", result["answer"])

    def test_never_mutates_database_records(self):
        before = copy.deepcopy(self.horses)
        answer_question(self.horses, "Qual a filiação de Aurora?")
        self.assertEqual(self.horses, before)


if __name__ == "__main__":
    unittest.main()
