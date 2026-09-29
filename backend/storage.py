"""Persistência JSON simples e segura para a Cocheira RADAMÉS."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_FILE = DATA_DIR / "store.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
_lock = threading.RLock()


def _empty_state() -> dict[str, Any]:
    return {"accounts": [], "sessions": {}, "horses": []}


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    # Migra automaticamente a conta única usada pelas versões anteriores.
    legacy_account = data.pop("account", None)
    data.setdefault("accounts", [legacy_account] if legacy_account else [])
    data.setdefault("sessions", {})
    data.setdefault("horses", [])
    return data

if DATABASE_URL:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("Instale as dependências com: pip install -r requirements.txt") from exc


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        save(_empty_state())


def load() -> dict[str, Any]:
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL, connect_timeout=10, sslmode="require") as connection:
            _ensure_database(connection)
            row = connection.execute("SELECT data FROM app_state WHERE id = 1").fetchone()
            return _normalize(row[0] if row else _empty_state())
    with _lock:
        _ensure()
        try:
            data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = _empty_state()
        return _normalize(data)


def save(data: dict[str, Any]) -> None:
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL, connect_timeout=10, sslmode="require") as connection:
            _ensure_database(connection)
            connection.execute("UPDATE app_state SET data = %s WHERE id = 1", (Jsonb(data),))
        return
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary = STORE_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, STORE_FILE)


def update(mutator):
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL, connect_timeout=10, sslmode="require") as connection:
            _ensure_database(connection)
            row = connection.execute("SELECT data FROM app_state WHERE id = 1 FOR UPDATE").fetchone()
            data = _normalize(row[0] if row else _empty_state())
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
        (Jsonb(_empty_state()),),
    )
