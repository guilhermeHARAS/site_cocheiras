import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import storage


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))


class MigrationBackupTests(unittest.TestCase):
    def test_backup_is_content_addressed_and_keeps_original_state(self):
        source = {
            "schemaVersion": 1,
            "accounts": [{"email": "caio.ferreira@radames", "password_hash": "preservar"}],
            "horses": [{"id": "cavalo-1", "name": "Persa", "workouts": 42}],
        }
        original = copy.deepcopy(source)
        connection = FakeConnection()
        previous_jsonb = getattr(storage, "Jsonb", None)
        storage.Jsonb = lambda value: value
        try:
            storage._backup_before_migration(connection, source)
            storage._backup_before_migration(connection, source)
        finally:
            if previous_jsonb is None:
                del storage.Jsonb
            else:
                storage.Jsonb = previous_jsonb

        self.assertEqual(source, original)
        self.assertEqual(len(connection.calls), 2)
        first_params = connection.calls[0][1]
        second_params = connection.calls[1][1]
        self.assertEqual(first_params[0], second_params[0])
        self.assertEqual(first_params[1], 1)
        self.assertEqual(first_params[3], original)


if __name__ == "__main__":
    unittest.main()
