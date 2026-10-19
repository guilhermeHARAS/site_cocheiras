"""Persistência compatível em JSON local ou PostgreSQL/Supabase."""
from __future__ import annotations

import hashlib
import json
import os
import threading
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


if DATABASE_CONFIGURED:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("Instale as dependências com: pip install -r requirements.txt") from exc


def _connect():
    if DATABASE_PASSWORD:
        return psycopg.connect(
            host=DATABASE_HOST,
            dbname=DATABASE_NAME,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            connect_timeout=10,
            sslmode="require",
        )
    return psycopg.connect(DATABASE_URL, connect_timeout=10, sslmode="require")


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
        with _connect() as connection:
            _ensure_database(connection)
            row = connection.execute("SELECT data FROM app_state WHERE id = 1").fetchone()
            source = row[0] if row else empty_state()
            data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
            if data != source:
                _backup_before_migration(connection, source)
                connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
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
        with _connect() as connection:
            _ensure_database(connection)
            connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
        return
    with _lock:
        _write_local(data)


def update(mutator):
    if DATABASE_CONFIGURED:
        with _connect() as connection:
            _ensure_database(connection)
            row = connection.execute("SELECT data FROM app_state WHERE id = 1 FOR UPDATE").fetchone()
            source = row[0] if row else empty_state()
            data = normalize_state(source, legacy_owner_email=LEGACY_OWNER_EMAIL)
            if data != source:
                _backup_before_migration(connection, source)
            result = mutator(data)
            connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
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
