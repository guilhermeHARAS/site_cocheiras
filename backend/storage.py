"""Persistência compatível em JSON local ou PostgreSQL/Supabase."""
from __future__ import annotations

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
    global _database_ready
    if not DATABASE_CONFIGURED or _database_ready:
        return
    pool = _pool_instance()
    with _database_lock:
        if _database_ready:
            return
        with pool.connection() as connection:
            _ensure_database(connection)
        _database_ready = True


def close() -> None:
    global _pool, _database_ready
    if _pool is not None:
        _pool.close()
    _pool = None
    _database_ready = False


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
        with _connect() as connection:
            row = connection.execute("SELECT data FROM app_state WHERE id = 1").fetchone()
            queried = time.perf_counter()
            source = row[0] if row else empty_state()
            data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
            normalized = time.perf_counter()
            if data != source:
                _backup_before_migration(connection, source)
                connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
            _log_performance(
                "load",
                started,
                query=(queried - started) * 1000,
                normalize=(normalized - queried) * 1000,
            )
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
    data = normalize_state(data, legacy_owner_email=LEGACY_OWNER_EMAIL)
    if DATABASE_CONFIGURED:
        started = time.perf_counter()
        with _connect() as connection:
            connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
        _log_performance("save", started)
        return
    with _lock:
        _write_local(data)


def update(mutator):
    if DATABASE_CONFIGURED:
        started = time.perf_counter()
        with _connect() as connection:
            row = connection.execute("SELECT data FROM app_state WHERE id = 1 FOR UPDATE").fetchone()
            source = row[0] if row else empty_state()
            data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
            if data != source:
                _backup_before_migration(connection, source)
            result = mutator(data)
            connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
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
