"""Autenticação local com PBKDF2 e sessões em memória."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

ITERATIONS = 240_000
SESSION_TTL = 60 * 60 * 12
_sessions: dict[str, float] = {}


def new_password_record(email: str, password: str) -> dict[str, str | int]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return {
        "email": email.strip().lower(),
        "salt": salt.hex(),
        "password_hash": digest.hex(),
        "iterations": ITERATIONS,
    }


def verify(account: dict, email: str, password: str) -> bool:
    if not account or account.get("email") != email.strip().lower():
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(account["salt"]),
            int(account.get("iterations", ITERATIONS)),
        ).hex()
        return hmac.compare_digest(digest, account["password_hash"])
    except (KeyError, TypeError, ValueError):
        return False


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    return token


def valid_session(token: str | None) -> bool:
    if not token or token not in _sessions:
        return False
    if _sessions[token] < time.time():
        _sessions.pop(token, None)
        return False
    return True


def end_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)
