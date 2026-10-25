import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from domain import apply_once, change_workout, normalize_state, transition_horse, validate_horse


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = {
            "accounts": [{"email": "pai@example.com", "salt": "abc", "password_hash": "hash", "iterations": 240000}],
            "sessions": {"token": {"email": "pai@example.com", "expires": 9999999999}},
            "horses": [{
                "id": "horse-1", "name": "Radamés", "photo": "data:image/png;base64,AAA",
                "breed": "PA", "age": 3, "sex": "Macho", "father": "Pai", "mother": "Mãe",
                "owner": "Clube", "notes": "Preservar", "workouts": 61, "lastWorkout": "2026-09-20",
            }],
        }

    def test_legacy_data_is_preserved_except_retired_photo_and_defaults_to_training(self):
        migrated = normalize_state(self.legacy, reference_date="2026-10-13")
        horse = migrated["horses"][0]
        account = migrated["accounts"][0]
        self.assertEqual(account["email"], self.legacy["accounts"][0]["email"])
        self.assertEqual(account["salt"], self.legacy["accounts"][0]["salt"])
        self.assertEqual(account["password_hash"], self.legacy["accounts"][0]["password_hash"])
        self.assertEqual(horse["workspaceId"], account["workspaceId"])
        self.assertEqual(migrated["sessions"], self.legacy["sessions"])
        self.assertEqual(horse["id"], "horse-1")
        self.assertEqual(horse["photo"], "")
        self.assertEqual(horse["workouts"], 61)
        self.assertEqual(horse["stage"], "training")
        self.assertEqual(horse["age"], 3)
        self.assertEqual(horse["ageRecordedAt"], "2026-10-13")
        self.assertNotEqual(horse["stage"], "ready")
        self.assertEqual(migrated["expenses"], [])

    def test_legacy_horses_are_assigned_to_requested_account(self):
        source = copy.deepcopy(self.legacy)
        source["accounts"].append({
            "email": "caio.ferreira@radames.com", "salt": "def",
            "password_hash": "hash-2", "iterations": 240000,
        })
        migrated = normalize_state(
            source,
            reference_date="2026-10-13",
            legacy_owner_email="caio.ferreira@radames",
        )
        father = next(account for account in migrated["accounts"] if account["email"].startswith("caio.ferreira@radames"))
        other = next(account for account in migrated["accounts"] if account["email"] == "pai@example.com")
        self.assertEqual(migrated["horses"][0]["workspaceId"], father["workspaceId"])
        self.assertNotEqual(father["workspaceId"], other["workspaceId"])

    def test_migration_is_idempotent(self):
        first = normalize_state(self.legacy, reference_date="2026-10-13")
        second = normalize_state(first, reference_date="2026-11-01")
        self.assertEqual(first, second)
        self.assertEqual(len(second["horses"]), 1)


class LifecycleTests(unittest.TestCase):
    def test_creation_needs_only_parents_and_keeps_forecast_optional(self):
        horse = validate_horse({"stage": "creation", "father": "Drink", "mother": "Juíza"}, stage="creation")
        self.assertEqual((horse["father"], horse["mother"]), ("Drink", "Juíza"))
        self.assertEqual(horse["name"], "")
        self.assertIsNone(horse["expectedBirthDate"])

    def test_born_horse_can_be_saved_with_name_only(self):
        horse = validate_horse({"stage": "foals", "name": "Sem idade"}, stage="foals")
        self.assertEqual(horse["name"], "Sem idade")
        self.assertIsNone(horse["birthDate"])
        self.assertIsNone(horse["age"])

    def test_future_birth_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "futuro"):
            validate_horse(
                {"stage": "foals", "name": "Futuro", "birthDate": "2026-10-14"},
                reference_date="2026-10-13",
            )

    def test_full_flow_preserves_identity_and_forecast(self):
        horse = validate_horse({
            "stage": "creation", "name": "Futuro", "father": "Pai", "mother": "Mãe",
            "expectedBirthDate": "2027-02-10",
        }, stage="creation", reference_date="2026-10-13")
        original_id = horse["id"]
        transition_horse(horse, "foals", payload={"name": "Nascido", "birthDate": "2027-02-12"}, reference_date="2027-02-12")
        self.assertEqual(horse["id"], original_id)
        self.assertEqual(horse["originalExpectedBirthDate"], "2027-02-10")
        self.assertEqual(horse["birthDate"], "2027-02-12")
        transition_horse(horse, "training", reference_date="2029-02-12")
        self.assertEqual(horse["workouts"], 0)
        with self.assertRaises(ValueError):
            transition_horse(horse, "ready")
        horse["workouts"] = 60
        transition_horse(horse, "ready", reference_date="2030-01-01")
        self.assertEqual(horse["stage"], "ready")
        self.assertEqual(horse["workouts"], 60)
        self.assertEqual(horse["id"], original_id)

    def test_workout_never_becomes_negative(self):
        horse = validate_horse({"stage": "training", "name": "Teste", "age": 3, "workouts": 0}, stage="training")
        change_workout(horse, -1)
        self.assertEqual(horse["workouts"], 0)

    def test_repeated_mutation_is_applied_once(self):
        state = normalize_state({"horses": []}, reference_date="2026-10-13")
        counter = {"value": 0}
        def operation():
            counter["value"] += 1
            return {"value": counter["value"]}
        first = apply_once(state, "same-click", operation)
        second = apply_once(state, "same-click", operation)
        self.assertEqual(first, second)
        self.assertEqual(counter["value"], 1)

    def test_edit_keeps_internal_workouts_for_ready_horse(self):
        current = validate_horse({"stage": "training", "name": "Pronto", "age": 5, "workouts": 72}, stage="training")
        current["stage"] = "ready"
        edited = validate_horse({"name": "Pronto Editado", "age": 5}, existing=current, stage="ready")
        self.assertEqual(edited["workouts"], 72)

    def test_new_and_legacy_photos_are_removed(self):
        created = validate_horse({
            "stage": "training", "name": "Sem foto",
            "photo": "data:image/png;base64,NOVA",
        }, stage="training")
        self.assertEqual(created["photo"], "")

        legacy = validate_horse({"stage": "training", "name": "Legado"}, stage="training")
        legacy["photo"] = "data:image/png;base64,ANTIGA"
        edited = validate_horse({
            "name": "Legado editado", "photo": "data:image/png;base64,SUBSTITUTA",
        }, existing=legacy, stage="training")
        self.assertEqual(edited["photo"], "")

        migrated = normalize_state({
            "schemaVersion": 7,
            "horses": [{
                "id": "cavalo-com-foto",
                "name": "Legado",
                "photo": "data:image/png;base64,ANTIGA",
            }],
        })
        self.assertEqual(migrated["schemaVersion"], 8)
        self.assertEqual(migrated["horses"][0]["photo"], "")

    def test_location_is_optional_and_preserved_when_editing(self):
        horse = validate_horse({
            "stage": "foals", "name": "Localizado", "location": "Piquete norte",
        }, stage="foals")
        self.assertEqual(horse["location"], "Piquete norte")
        edited = validate_horse({"name": "Localizado"}, existing=horse, stage="foals")
        self.assertEqual(edited["location"], "Piquete norte")


if __name__ == "__main__":
    unittest.main()
