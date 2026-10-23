"""Persistência compatível em JSON local ou PostgreSQL/Supabase."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from domain import empty_state, normalize_state

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_FILE = Path(os.environ.get("DATA_FILE", DEFAULT_DATA_DIR / "store.json")).resolve()
DATA_DIR = STORE_FILE.parent
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")
DATABASE_HOST = os.environ.get("DATABASE_HOST", "").strip()
DATABASE_USER = os.environ.get("DATABASE_USER", "").strip()
DATABASE_NAME = os.environ.get("DATABASE_NAME", "postgres").strip()
DATABASE_CONFIGURED = bool(DATABASE_URL or DATABASE_PASSWORD)
LEGACY_OWNER_EMAIL = os.environ.get("LEGACY_OWNER_EMAIL", "caio.ferreira@radames").strip().lower()
_lock = threading.RLock()
_database_lock = threading.Lock()
_pool = None
_database_ready = False
_state_cache: dict[str, Any] | None = None
PERF_LOG_ENABLED = os.environ.get("PERF_LOG_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


if DATABASE_CONFIGURED:
    try:
        import psycopg
        from psycopg_pool import ConnectionPool
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("Instale as dependências com: pip install -r requirements.txt") from exc


def _log_performance(operation: str, started: float, **details: float) -> None:
    if not PERF_LOG_ENABLED:
        return
    elapsed = (time.perf_counter() - started) * 1000
    suffix = " ".join(f"{key}={value:.1f}ms" for key, value in details.items())
    print(f"[PERF] storage.{operation} total={elapsed:.1f}ms{(' ' + suffix) if suffix else ''}", flush=True)


def _pool_instance():
    global _pool
    if _pool is not None:
        return _pool
    with _database_lock:
        if _pool is None:
            if DATABASE_PASSWORD:
                conninfo = psycopg.conninfo.make_conninfo(
                    host=DATABASE_HOST,
                    dbname=DATABASE_NAME,
                    user=DATABASE_USER,
                    password=DATABASE_PASSWORD,
                )
            else:
                conninfo = DATABASE_URL
            _pool = ConnectionPool(
                conninfo=conninfo,
                min_size=1,
                max_size=6,
                timeout=10,
                open=True,
                kwargs={"connect_timeout": 10, "sslmode": "require"},
            )
    return _pool


def initialize() -> None:
    """Prepara banco e pool uma única vez durante a inicialização do servidor."""
    global _database_ready, _state_cache
    if not DATABASE_CONFIGURED or _database_ready:
        return
    pool = _pool_instance()
    with _database_lock:
        if _database_ready:
            return
        with pool.connection() as connection:
            _ensure_database(connection)
            _migrate_to_relational(connection)
            _state_cache = _load_relational(connection)
        _database_ready = True


def close() -> None:
    global _pool, _database_ready, _state_cache
    if _pool is not None:
        _pool.close()
    _pool = None
    _database_ready = False
    _state_cache = None


def _connect():
    initialize()
    return _pool_instance().connection()


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        _write_local(empty_state())


def _write_local(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STORE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, STORE_FILE)


def load() -> dict[str, Any]:
    if DATABASE_CONFIGURED:
        started = time.perf_counter()
        initialize()
        with _lock:
            data = copy.deepcopy(_state_cache or empty_state())
        _log_performance("load_cache", started)
        return data
    with _lock:
        _ensure()
        try:
            source = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            source = empty_state()
        data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
        if data != source:
            _write_local(data)
        return data


def save(data: dict[str, Any]) -> None:
    global _state_cache
    data = normalize_state(data, legacy_owner_email=LEGACY_OWNER_EMAIL)
    if DATABASE_CONFIGURED:
        started = time.perf_counter()
        initialize()
        with _lock:
            with _connect() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(82374419)")
                before = _load_relational(connection)
                _sync_relational(connection, before, data)
                _sync_legacy_snapshot(connection, data)
            _state_cache = copy.deepcopy(data)
        _log_performance("save", started)
        return
    with _lock:
        _write_local(data)


def update(mutator):
    global _state_cache
    if DATABASE_CONFIGURED:
        started = time.perf_counter()
        initialize()
        with _lock:
            with _connect() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(82374419)")
                before = _load_relational(connection)
                data = copy.deepcopy(before)
                result = mutator(data)
                data = normalize_state(data, legacy_owner_email=LEGACY_OWNER_EMAIL)
                _sync_relational(connection, before, data)
                _sync_legacy_snapshot(connection, data)
            _state_cache = copy.deepcopy(data)
            _log_performance("update", started)
            return result
    with _lock:
        data = load()
        result = mutator(data)
        save(data)
        return result


def _ensure_database(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            data JSONB NOT NULL
        )
    """)
    connection.execute(
        "INSERT INTO app_state (id, data) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",
        (Jsonb(empty_state()),),
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS app_state_backups (
            id BIGSERIAL PRIMARY KEY,
            source_hash TEXT NOT NULL UNIQUE,
            schema_version INTEGER,
            reason TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_meta (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_accounts (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            workspace_id TEXT NOT NULL,
            data JSONB NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_accounts_workspace_idx ON cocheira_accounts (workspace_id)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_sessions (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            expires BIGINT NOT NULL,
            data JSONB NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_sessions_email_idx ON cocheira_sessions (email)")
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_sessions_expires_idx ON cocheira_sessions (expires)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_horses (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            name TEXT NOT NULL,
            data JSONB NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_horses_workspace_stage_idx ON cocheira_horses (workspace_id, stage)")
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_horses_name_idx ON cocheira_horses (workspace_id, LOWER(name))")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_expenses (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            expense_date DATE NOT NULL,
            category TEXT NOT NULL,
            amount_cents BIGINT NOT NULL,
            data JSONB NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_expenses_workspace_date_idx ON cocheira_expenses (workspace_id, expense_date DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS cocheira_expenses_category_idx ON cocheira_expenses (workspace_id, category)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS cocheira_mutations (
            mutation_key TEXT PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)


def _load_relational(connection) -> dict[str, Any]:
    row = connection.execute("""
        SELECT
            COALESCE((SELECT jsonb_agg(data ORDER BY email) FROM cocheira_accounts), '[]'::jsonb),
            COALESCE((SELECT jsonb_object_agg(token_hash, data) FROM cocheira_sessions), '{}'::jsonb),
            COALESCE((SELECT jsonb_agg(data ORDER BY LOWER(name), id) FROM cocheira_horses), '[]'::jsonb),
            COALESCE((SELECT jsonb_agg(data ORDER BY expense_date DESC, id) FROM cocheira_expenses), '[]'::jsonb),
            COALESCE((SELECT jsonb_object_agg(mutation_key, data) FROM cocheira_mutations), '{}'::jsonb)
    """).fetchone()
    if not row:
        return empty_state()
    return normalize_state({
        "schemaVersion": empty_state()["schemaVersion"],
        "accounts": row[0],
        "sessions": row[1],
        "horses": row[2],
        "expenses": row[3],
        "processedMutations": row[4],
    }, legacy_owner_email=LEGACY_OWNER_EMAIL)


def _migrate_to_relational(connection) -> None:
    ready = connection.execute(
        "SELECT value FROM cocheira_meta WHERE key = 'relational_storage_v1'"
    ).fetchone()
    if ready:
        return

    row = connection.execute("SELECT data FROM app_state WHERE id = 1 FOR UPDATE").fetchone()
    source = row[0] if row else empty_state()
    data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
    _backup_before_migration(connection, source)

    # Como a confirmação só é gravada no fim da mesma transação, uma tentativa
    # interrompida pode ser executada novamente sem duplicar registros.
    for table in (
        "cocheira_mutations", "cocheira_sessions", "cocheira_expenses",
        "cocheira_horses", "cocheira_accounts",
    ):
        connection.execute(f"DELETE FROM {table}")
    _sync_relational(connection, empty_state(), data)

    actual = connection.execute("""
        SELECT
            (SELECT COUNT(*) FROM cocheira_accounts),
            (SELECT COUNT(*) FROM cocheira_sessions),
            (SELECT COUNT(*) FROM cocheira_horses),
            (SELECT COUNT(*) FROM cocheira_expenses),
            (SELECT COUNT(*) FROM cocheira_mutations)
    """).fetchone()
    expected = (
        len(data["accounts"]), len(data["sessions"]), len(data["horses"]),
        len(data["expenses"]), len(data["processedMutations"]),
    )
    if tuple(actual or ()) != expected:
        raise RuntimeError(f"Migração relacional incompleta: esperado {expected}, obtido {actual}.")
    connection.execute("""
        INSERT INTO cocheira_meta (key, value, updated_at)
        VALUES ('relational_storage_v1', %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (Jsonb({"completed": True, "counts": expected}),))
    print(
        "[MIGRATION] relational_storage_v1 completed "
        f"accounts={expected[0]} sessions={expected[1]} horses={expected[2]} "
        f"expenses={expected[3]} mutations={expected[4]}",
        flush=True,
    )


def _execute_many(connection, query: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def _changed(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for key, value in after.items() if before.get(key) != value]


def _delete_missing(connection, table: str, column: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    removed = [key for key in before if key not in after]
    if removed:
        connection.execute(f"DELETE FROM {table} WHERE {column} = ANY(%s)", (removed,))


def _sync_relational(connection, before: dict[str, Any], after: dict[str, Any]) -> None:
    before_accounts = {item["id"]: item for item in before.get("accounts", [])}
    after_accounts = {item["id"]: item for item in after.get("accounts", [])}
    _delete_missing(connection, "cocheira_accounts", "id", before_accounts, after_accounts)
    _execute_many(connection, """
        INSERT INTO cocheira_accounts (id, email, workspace_id, data)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            workspace_id = EXCLUDED.workspace_id,
            data = EXCLUDED.data
    """, [
        (item["id"], item["email"], item["workspaceId"], Jsonb(item))
        for item in _changed(before_accounts, after_accounts)
    ])

    before_sessions = before.get("sessions", {})
    after_sessions = after.get("sessions", {})
    _delete_missing(connection, "cocheira_sessions", "token_hash", before_sessions, after_sessions)
    _execute_many(connection, """
        INSERT INTO cocheira_sessions (token_hash, email, expires, data)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (token_hash) DO UPDATE SET
            email = EXCLUDED.email,
            expires = EXCLUDED.expires,
            data = EXCLUDED.data
    """, [
        (key, item.get("email", ""), int(item.get("expires", 0)), Jsonb(item))
        for key, item in after_sessions.items() if before_sessions.get(key) != item
    ])

    before_horses = {item["id"]: item for item in before.get("horses", [])}
    after_horses = {item["id"]: item for item in after.get("horses", [])}
    _delete_missing(connection, "cocheira_horses", "id", before_horses, after_horses)
    _execute_many(connection, """
        INSERT INTO cocheira_horses (id, workspace_id, stage, name, data)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            workspace_id = EXCLUDED.workspace_id,
            stage = EXCLUDED.stage,
            name = EXCLUDED.name,
            data = EXCLUDED.data
    """, [
        (item["id"], item.get("workspaceId") or "", item["stage"], item.get("name") or "", Jsonb(item))
        for item in _changed(before_horses, after_horses)
    ])

    before_expenses = {item["id"]: item for item in before.get("expenses", [])}
    after_expenses = {item["id"]: item for item in after.get("expenses", [])}
    _delete_missing(connection, "cocheira_expenses", "id", before_expenses, after_expenses)
    _execute_many(connection, """
        INSERT INTO cocheira_expenses (id, workspace_id, expense_date, category, amount_cents, data)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            workspace_id = EXCLUDED.workspace_id,
            expense_date = EXCLUDED.expense_date,
            category = EXCLUDED.category,
            amount_cents = EXCLUDED.amount_cents,
            data = EXCLUDED.data
    """, [
        (
            item["id"], item.get("workspaceId") or "", item["date"],
            item["category"], int(item.get("amountCents", 0)), Jsonb(item),
        )
        for item in _changed(before_expenses, after_expenses)
    ])

    before_mutations = before.get("processedMutations", {})
    after_mutations = after.get("processedMutations", {})
    _delete_missing(connection, "cocheira_mutations", "mutation_key", before_mutations, after_mutations)
    _execute_many(connection, """
        INSERT INTO cocheira_mutations (mutation_key, data)
        VALUES (%s, %s)
        ON CONFLICT (mutation_key) DO UPDATE SET data = EXCLUDED.data
    """, [
        (key, Jsonb(item))
        for key, item in after_mutations.items() if before_mutations.get(key) != item
    ])


def _sync_legacy_snapshot(connection, data: dict[str, Any]) -> None:
    """Mantém uma rota de retorno segura enquanto a migração é estabilizada."""
    connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))


def _backup_before_migration(connection, source: Any) -> None:
    """Guarda uma cópia idempotente do estado bruto antes de migrá-lo."""
    serialized = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    source_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    schema_version = source.get("schemaVersion") if isinstance(source, dict) else None
    if not isinstance(schema_version, int):
        schema_version = None
    connection.execute(
        """
        INSERT INTO app_state_backups (source_hash, schema_version, reason, data)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source_hash) DO NOTHING
        """,
        (source_hash, schema_version, "automatic schema migration", Jsonb(source)),
    )
