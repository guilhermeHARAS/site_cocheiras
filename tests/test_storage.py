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


class DatabaseInitializationTests(unittest.TestCase):
    def test_database_schema_is_ensured_only_once(self):
        class ConnectionContext:
            def __enter__(self):
                return object()

            def __exit__(self, *_args):
                return False

        class Pool:
            def __init__(self):
                self.connections = 0

            def connection(self):
                self.connections += 1
                return ConnectionContext()

        pool = Pool()
        ensured = []
        previous = {
            "configured": storage.DATABASE_CONFIGURED,
            "ready": storage._database_ready,
            "pool_instance": storage._pool_instance,
            "ensure_database": storage._ensure_database,
        }
        try:
            storage.DATABASE_CONFIGURED = True
            storage._database_ready = False
            storage._pool_instance = lambda: pool
            storage._ensure_database = lambda connection: ensured.append(connection)
            storage.initialize()
            storage.initialize()
        finally:
            storage.DATABASE_CONFIGURED = previous["configured"]
            storage._database_ready = previous["ready"]
            storage._pool_instance = previous["pool_instance"]
            storage._ensure_database = previous["ensure_database"]

        self.assertEqual(pool.connections, 1)
        self.assertEqual(len(ensured), 1)


if __name__ == "__main__":
    unittest.main()
