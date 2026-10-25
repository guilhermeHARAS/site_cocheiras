import base64
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from importer import duplicate_of, parse_notes, parse_spreadsheet


class NotesImportTests(unittest.TestCase):
    def test_reproduction_reads_one_cross_per_line_without_expected_name_or_date(self):
        records = parse_notes(
            "Drink x Juíza\nTrovão × Lua\nRelâmpago cruzado com Estrela\nVento com Aurora",
            "creation",
        )["records"]
        self.assertEqual(len(records), 4)
        self.assertEqual([(item["father"], item["mother"]) for item in records], [
            ("Drink", "Juíza"), ("Trovão", "Lua"), ("Relâmpago", "Estrela"), ("Vento", "Aurora"),
        ])
        self.assertTrue(all(item["name"] == "" and item["expectedBirthDate"] is None for item in records))
        self.assertTrue(all(item["issues"] == [] for item in records))

    def test_reproduction_reads_labeled_parents_and_optional_forecast(self):
        record = parse_notes("Pai: Drink\nMãe: Juíza\nPrevisão: 10/12/2027", "creation")["records"][0]
        self.assertEqual((record["father"], record["mother"]), ("Drink", "Juíza"))
        self.assertEqual(record["expectedBirthDate"], "2027-12-10")

    def test_reads_labeled_notepad_records(self):
        result = parse_notes(
            "Nome: Relâmpago\nPai: Trovão\nMãe: Estrela\nIdade: 3\nTreinos: 12\n\n"
            "Cavalo: Lua\nNascimento: 15/03/2023\nProprietário: Ana",
            "training",
        )
        self.assertEqual(len(result["records"]), 2)
        first, second = result["records"]
        self.assertEqual(first["name"], "Relâmpago")
        self.assertEqual(first["father"], "Trovão")
        self.assertEqual(first["workouts"], 12)
        self.assertEqual(first["issues"], [])
        self.assertEqual(second["birthDate"], "2023-03-15")

    def test_reads_location_from_notes(self):
        record = parse_notes("Nome: Aurora\nLocalização: Baia 7", "training")["records"][0]
        self.assertEqual(record["location"], "Baia 7")

    def test_name_only_is_ready_to_import(self):
        record = parse_notes("Nome: Sem data", "foals")["records"][0]
        self.assertEqual(record["name"], "Sem data")
        self.assertEqual(record["issues"], [])

    def test_reads_simple_list_with_name_and_optional_age(self):
        records = parse_notes("Relâmpago - 3 anos\nEstrela\nLua, 2", "foals")["records"]
        self.assertEqual([(item["name"], item["age"]) for item in records], [
            ("Relâmpago", 3), ("Estrela", None), ("Lua", 2),
        ])

    def test_continuous_lines_complete_a_horse_and_blank_line_starts_another(self):
        records = parse_notes(
            "Persa\nDuelo x Leide\n3 anos\n\nEstrela\nTrovão x Lua",
            "training",
        )["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual((records[0]["name"], records[0]["father"], records[0]["mother"], records[0]["age"]),
                         ("Persa", "Duelo", "Leide", 3))
        self.assertEqual((records[1]["name"], records[1]["father"], records[1]["mother"]),
                         ("Estrela", "Trovão", "Lua"))

    def test_inline_pedigree_is_interpreted_but_requires_review(self):
        record = parse_notes("Persa DueloXLeide", "training")["records"][0]
        self.assertEqual((record["name"], record["father"], record["mother"]), ("Persa", "Duelo", "Leide"))
        self.assertIn("Confira a interpretação", record["issues"][0])

    def test_understands_continuous_voice_phrase_and_spoken_date(self):
        record = parse_notes(
            "nome Relâmpago pai Trovão mãe Estrela nascimento dia 15 de março de 2023 treinos 9",
            "training",
            "Ditado",
        )["records"][0]
        self.assertEqual(record["name"], "Relâmpago")
        self.assertEqual(record["father"], "Trovão")
        self.assertEqual(record["mother"], "Estrela")
        self.assertEqual(record["birthDate"], "2023-03-15")
        self.assertEqual(record["workouts"], 9)

    def test_finds_probable_duplicate_without_deleting_anything(self):
        record = parse_notes("Nome: Raio\nPai: Sol\nIdade: 4", "training")["records"][0]
        duplicate = duplicate_of(record, [{"name": "RAIO", "father": "Outro", "mother": "Outra", "birthDate": None}])
        self.assertEqual(duplicate, "RAIO")


class SpreadsheetImportTests(unittest.TestCase):
    def test_reads_csv_with_semicolon_and_alias_headers(self):
        raw = "Animal;Garanhão;Matriz;Idade em anos;Total treinos;Fase\nFlecha;Trovão;Lua;5;61;Tropa pronta\n".encode()
        result = parse_spreadsheet("cavalos.csv", base64.b64encode(raw).decode(), "training")
        record = result["records"][0]
        self.assertEqual(record["name"], "Flecha")
        self.assertEqual(record["father"], "Trovão")
        self.assertEqual(record["stage"], "training")
        self.assertEqual(record["workouts"], 61)

    def test_reads_location_from_spreadsheet(self):
        raw = "Nome;Localização\nFlecha;Piquete norte\n".encode()
        result = parse_spreadsheet("cavalos.csv", base64.b64encode(raw).decode(), "training")
        self.assertEqual(result["records"][0]["location"], "Piquete norte")

    def test_reads_xlsx_and_preserves_unknown_columns_in_notes(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl não instalado")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Plantel"
        sheet.append(["Nome do cavalo", "Pai", "Mãe", "Nascimento", "Pelagem"])
        sheet.append(["Safira", "Vento", "Aurora", "02/04/2022", "Alazã"])
        content = io.BytesIO()
        workbook.save(content)
        result = parse_spreadsheet("plantel.xlsx", base64.b64encode(content.getvalue()).decode(), "foals")
        record = result["records"][0]
        self.assertEqual(record["name"], "Safira")
        self.assertEqual(record["birthDate"], "2022-04-02")
        self.assertIn("Pelagem: Alazã", record["notes"])

    def test_spreadsheet_row_without_name_completes_previous_horse(self):
        raw = (
            "Nome;Pai;Mãe;Idade\n"
            "Persa;;;\n"
            ";Duelo;Leide;3\n"
            ";;;\n"
            "Estrela;Trovão;Lua;4\n"
        ).encode()
        result = parse_spreadsheet("continuacao.csv", base64.b64encode(raw).decode(), "training")
        self.assertEqual(len(result["records"]), 2)
        persa = result["records"][0]
        self.assertEqual((persa["name"], persa["father"], persa["mother"], persa["age"]),
                         ("Persa", "Duelo", "Leide", 3))
        self.assertIn("linhas 2–3 reunidas", persa["importOrigin"])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
