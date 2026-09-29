"""Autenticação com PBKDF2 e sessões persistentes."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

ITERATIONS = 240_000
SESSION_TTL = 60 * 60 * 24 * 90


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


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(data: dict, email: str) -> str:
    token = secrets.token_urlsafe(32)
    sessions = data.setdefault("sessions", {})
    now = int(time.time())
    for key, session in list(sessions.items()):
        if int(session.get("expires", 0)) <= now:
            sessions.pop(key, None)
    sessions[_token_id(token)] = {
        "email": email.strip().lower(),
        "expires": now + SESSION_TTL,
    }
    return token


def valid_session(data: dict, token: str | None) -> bool:
    if not token:
        return False
    session = data.get("sessions", {}).get(_token_id(token))
    if not session or int(session.get("expires", 0)) <= time.time():
        return False
    return True


def end_session(data: dict, token: str | None) -> None:
    if token:
        data.setdefault("sessions", {}).pop(_token_id(token), None)
