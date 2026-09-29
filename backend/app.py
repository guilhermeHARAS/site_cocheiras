#!/usr/bin/env python3
"""Servidor e API da Cocheira RADAMÉS, sem dependências externas."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import uuid
import webbrowser
from datetime import date
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import unquote, urlparse

from auth import SESSION_TTL, create_session, end_session, new_password_record, valid_session, verify
from storage import load, update

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
COOKIE_NAME = "radames_session"
MAX_BODY = 4 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Handler(BaseHTTPRequestHandler):
    server_version = "CocheiraRadames/2.0"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json(self, payload, status=HTTPStatus.OK, cookie=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > MAX_BODY:
                raise ValueError("Arquivo ou requisição muito grande.")
            return json.loads(self.rfile.read(size) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Dados enviados são inválidos.") from exc

    def _token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        item = cookie.get(COOKIE_NAME)
        return item.value if item else None

    def _authorized(self):
        return valid_session(load(), self._token())

    def _require_auth(self):
        if self._authorized():
            return True
        self._json({"error": "Faça login para continuar."}, HTTPStatus.UNAUTHORIZED)
        return False

    def _session_cookie(self, token, delete=False):
        max_age = 0 if delete else SESSION_TTL
        value = "" if delete else token
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() == "https" else ""
        return f"{COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/session":
            data = load()
            return self._json({
                "setupRequired": not data["accounts"],
                "authenticated": valid_session(data, self._token()),
                "email": data["accounts"][0].get("email") if len(data["accounts"]) == 1 else None,
            })
        if path == "/api/horses":
            if self._require_auth():
                self._json(load()["horses"])
            return
        self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._body()
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        if path in ("/api/setup", "/api/signup"):
            return self._signup(payload)
        if path == "/api/login":
            return self._login(payload)
        if path == "/api/logout":
            token = self._token()
            update(lambda data: end_session(data, token))
            return self._json({"ok": True}, cookie=self._session_cookie("", True))
        if not self._require_auth():
            return
        if path == "/api/horses":
            return self._create_horse(payload)
        match = re.fullmatch(r"/api/horses/([^/]+)/(train|undo)", path)
        if match:
            return self._change_workout(match.group(1), match.group(2))
        self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        match = re.fullmatch(r"/api/horses/([^/]+)", path)
        if not match:
            return self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)
        try:
            payload = self._body()
            horse = self._validated_horse(payload, match.group(1))
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def mutate(data):
            for index, current in enumerate(data["horses"]):
                if current["id"] == horse["id"]:
                    horse["lastWorkout"] = current.get("lastWorkout")
                    data["horses"][index] = horse
                    return horse
            raise LookupError

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        match = re.fullmatch(r"/api/horses/([^/]+)", path)
        if not match:
            return self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)
        horse_id = match.group(1)

        def mutate(data):
            before = len(data["horses"])
            data["horses"] = [h for h in data["horses"] if h["id"] != horse_id]
            return before != len(data["horses"])

        if update(mutate):
            self._json({"ok": True})
        else:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)

    def _signup(self, payload):
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if not EMAIL_RE.match(email) or len(password) < 6:
            return self._json({"error": "Informe um e-mail válido e uma senha com 6 caracteres ou mais."}, HTTPStatus.BAD_REQUEST)

        def mutate(data):
            if any(account.get("email") == email for account in data["accounts"]):
                raise FileExistsError
            data["accounts"].append(new_password_record(email, password))
            return create_session(data, email)

        try:
            token = update(mutate)
        except FileExistsError:
            return self._json({"error": "Já existe uma conta com este e-mail."}, HTTPStatus.CONFLICT)
        self._json({"ok": True, "email": email}, HTTPStatus.CREATED, self._session_cookie(token))

    def _login(self, payload):
        data = load()
        email = str(payload.get("email", "")).strip().lower()
        account = next((item for item in data["accounts"] if item.get("email") == email), None)
        if not verify(account, str(payload.get("email", "")), str(payload.get("password", ""))):
            return self._json({"error": "E-mail ou senha incorretos."}, HTTPStatus.UNAUTHORIZED)
        token = update(lambda current: create_session(current, account["email"]))
        self._json({"ok": True, "email": account["email"]}, cookie=self._session_cookie(token))

    def _validated_horse(self, payload, horse_id=None):
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Informe o nome do cavalo.")
        photo = str(payload.get("photo", ""))
        if len(photo) > 3_600_000:
            raise ValueError("A foto deve ter no máximo 2,5 MB.")
        try:
            workouts = max(0, int(payload.get("workouts", 0)))
            age_value = payload.get("age")
            age = None if age_value in (None, "") else max(0, min(60, int(age_value)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Idade ou quantidade de treinos inválida.") from exc
        return {
            "id": horse_id or uuid.uuid4().hex,
            "name": name[:80], "photo": photo, "breed": str(payload.get("breed", "")).strip()[:80],
            "age": age, "sex": str(payload.get("sex", ""))[:20],
            "father": str(payload.get("father", "")).strip()[:80],
            "mother": str(payload.get("mother", "")).strip()[:80],
            "owner": str(payload.get("owner", "")).strip()[:100],
            "notes": str(payload.get("notes", "")).strip()[:600],
            "workouts": workouts, "lastWorkout": None,
        }

    def _create_horse(self, payload):
        try:
            horse = self._validated_horse(payload)
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        update(lambda data: data["horses"].insert(0, horse))
        self._json(horse, HTTPStatus.CREATED)

    def _change_workout(self, horse_id, action):
        def mutate(data):
            for horse in data["horses"]:
                if horse["id"] == horse_id:
                    if action == "train":
                        horse["workouts"] += 1
                        horse["lastWorkout"] = date.today().isoformat()
                    else:
                        horse["workouts"] = max(0, horse["workouts"] - 1)
                        if horse["workouts"] == 0:
                            horse["lastWorkout"] = None
                    return horse
            raise LookupError

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)

    def _serve_static(self, path):
        relative = "index.html" if path in ("/", "") else unquote(path.lstrip("/"))
        target = (FRONTEND / relative).resolve()
        if FRONTEND.resolve() not in target.parents and target != FRONTEND.resolve():
            return self.send_error(HTTPStatus.FORBIDDEN)
        if not target.is_file():
            target = FRONTEND / "index.html"
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime in ("application/javascript", "application/manifest+json") else mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description="Cocheira RADAMÉS")
    default_host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    parser.add_argument("--host", default=os.environ.get("HOST", default_host))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Cocheira RADAMÉS disponível em {url}\nPressione Ctrl+C para encerrar.")
    if not args.no_browser:
        Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
