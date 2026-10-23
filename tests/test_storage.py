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
            "cache": storage._state_cache,
            "pool_instance": storage._pool_instance,
            "ensure_database": storage._ensure_database,
            "migrate": storage._migrate_to_relational,
            "load_relational": storage._load_relational,
        }
        try:
            storage.DATABASE_CONFIGURED = True
            storage._database_ready = False
            storage._pool_instance = lambda: pool
            storage._ensure_database = lambda connection: ensured.append(connection)
            storage._migrate_to_relational = lambda connection: None
            storage._load_relational = lambda connection: {"loaded": True}
            storage.initialize()
            storage.initialize()
        finally:
            storage.DATABASE_CONFIGURED = previous["configured"]
            storage._database_ready = previous["ready"]
            storage._state_cache = previous["cache"]
            storage._pool_instance = previous["pool_instance"]
            storage._ensure_database = previous["ensure_database"]
            storage._migrate_to_relational = previous["migrate"]
            storage._load_relational = previous["load_relational"]

        self.assertEqual(pool.connections, 1)
        self.assertEqual(len(ensured), 1)

    def test_cached_load_does_not_open_database_connection(self):
        previous = {
            "configured": storage.DATABASE_CONFIGURED,
            "ready": storage._database_ready,
            "cache": storage._state_cache,
        }
        try:
            storage.DATABASE_CONFIGURED = True
            storage._database_ready = True
            storage._state_cache = {
                "schemaVersion": 8,
                "accounts": [],
                "sessions": {},
                "horses": [{"id": "horse-1", "name": "Persa"}],
                "expenses": [],
                "processedMutations": {},
            }
            first = storage.load()
            first["horses"][0]["name"] = "Alterado fora do cache"
            second = storage.load()
        finally:
            storage.DATABASE_CONFIGURED = previous["configured"]
            storage._database_ready = previous["ready"]
            storage._state_cache = previous["cache"]

        self.assertEqual(second["horses"][0]["name"], "Persa")


class RelationalSyncTests(unittest.TestCase):
    def test_sync_writes_only_changed_rows_and_removes_deleted_rows(self):
        class Cursor:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def executemany(self, query, rows):
                self.connection.many.append((" ".join(query.split()), list(rows)))

        class Connection:
            def __init__(self):
                self.calls = []
                self.many = []

            def execute(self, query, params=None):
                self.calls.append((" ".join(query.split()), params))

            def cursor(self):
                return Cursor(self)

        before = {
            "accounts": [], "sessions": {}, "processedMutations": {},
            "horses": [
                {"id": "h1", "workspaceId": "w1", "stage": "training", "name": "Persa"},
                {"id": "h2", "workspaceId": "w1", "stage": "foals", "name": "Potro"},
            ],
            "expenses": [{
                "id": "e1", "workspaceId": "w1", "date": "2026-10-01",
                "category": "food", "amountCents": 100,
            }],
        }
        after = copy.deepcopy(before)
        after["horses"][0]["name"] = "Persa editado"
        after["expenses"] = []
        connection = Connection()
        previous_jsonb = getattr(storage, "Jsonb", None)
        storage.Jsonb = lambda value: value
        try:
            storage._sync_relational(connection, before, after)
        finally:
            if previous_jsonb is None:
                del storage.Jsonb
            else:
                storage.Jsonb = previous_jsonb

        deletes = [call for call in connection.calls if call[0].startswith("DELETE")]
        horse_batches = [batch for batch in connection.many if "cocheira_horses" in batch[0]]
        self.assertEqual(len(deletes), 1)
        self.assertIn("cocheira_expenses", deletes[0][0])
        self.assertEqual(deletes[0][1], (["e1"],))
        self.assertEqual(len(horse_batches), 1)
        self.assertEqual(len(horse_batches[0][1]), 1)
        self.assertEqual(horse_batches[0][1][0][0], "h1")


if __name__ == "__main__":
    unittest.main()
