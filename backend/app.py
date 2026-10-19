#!/usr/bin/env python3
"""Servidor e API da Cocheira RADAMÉS."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import socket
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import parse_qs, unquote, urlparse

from assistant import answer_question
from auth import SESSION_TTL, create_session, end_session, new_password_record, session_email, valid_session, verify
from costs import parse_expense_notes, parse_expense_spreadsheet, parse_expense_text, validate_expense
from domain import apply_once, change_workout, transition_horse, validate_horse
from importer import duplicate_of, parse_notes, parse_spreadsheet, refresh_record
from reports import financial_pdf, financial_xlsx
from storage import load, update

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
COOKIE_NAME = "radames_session"
MAX_BODY = 12 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AppHTTPServer(ThreadingHTTPServer):
    # No Windows, SO_REUSEADDR pode permitir dois servidores locais na mesma
    # porta. Isso mantém uma versão antiga atendendo parte das gravações.
    allow_reuse_address = os.name != "nt"


class Handler(BaseHTTPRequestHandler):
    server_version = "CocheiraRadames/3.0"

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

    def _file(self, content, content_type, filename):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > MAX_BODY:
                raise ValueError("Arquivo ou requisição muito grande.")
            value = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(value, dict):
                raise ValueError("Dados enviados são inválidos.")
            return value
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Dados enviados são inválidos.") from exc

    def _token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        item = cookie.get(COOKIE_NAME)
        return item.value if item else None

    def _mutation_id(self):
        return self.headers.get("Idempotency-Key", "").strip() or None

    def _authorized(self):
        return valid_session(load(), self._token())

    def _account(self, data):
        email = session_email(data, self._token())
        return next((item for item in data["accounts"] if item.get("email") == email), None)

    def _workspace(self, data):
        account = self._account(data)
        return account.get("workspaceId") if account else None

    def _visible_horses(self, data):
        workspace = self._workspace(data)
        return [horse for horse in data["horses"] if workspace and horse.get("workspaceId") == workspace]

    def _visible_expenses(self, data):
        workspace = self._workspace(data)
        return [expense for expense in data["expenses"] if workspace and expense.get("workspaceId") == workspace]

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
            email = session_email(data, self._token())
            return self._json({
                "setupRequired": not data["accounts"],
                "authenticated": bool(email),
                "email": email,
            })
        if path == "/api/horses":
            if self._require_auth():
                data = load()
                self._json(self._visible_horses(data))
            return
        if path == "/api/account":
            if self._require_auth():
                data = load()
                account = self._account(data)
                workspace = account.get("workspaceId") if account else None
                emails = sorted(item["email"] for item in data["accounts"] if item.get("workspaceId") == workspace)
                self._json({"currentEmail": account.get("email"), "emails": emails})
            return
        if path == "/api/expenses":
            if self._require_auth():
                data = load()
                self._json(self._visible_expenses(data))
            return
        report_match = re.fullmatch(r"/api/reports/financial\.(pdf|xlsx)", path)
        if report_match:
            if not self._require_auth():
                return
            try:
                data = load()
                period = parse_qs(urlparse(self.path).query).get("period", [""])[0]
                content = financial_pdf(self._visible_expenses(data), self._visible_horses(data), period) if report_match.group(1) == "pdf" else financial_xlsx(self._visible_expenses(data), self._visible_horses(data), period)
                mime = "application/pdf" if report_match.group(1) == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                return self._file(content, mime, f"relatorio-financeiro-{period}.{report_match.group(1)}")
            except (ValueError, RuntimeError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
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
        if path == "/api/account/emails":
            return self._add_account_email(payload)
        if path == "/api/account/password":
            return self._change_password(payload)
        if path == "/api/expenses":
            return self._create_expense(payload)
        if path == "/api/expenses/import/preview":
            return self._expense_import_preview(payload)
        if path == "/api/expenses/import/commit":
            return self._expense_import_commit(payload)
        if path == "/api/expenses/parse":
            data = load()
            try:
                return self._json(parse_expense_text(str(payload.get("text") or ""), self._visible_horses(data)))
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/horses":
            return self._create_horse(payload)
        if path == "/api/import/preview":
            return self._import_preview(payload)
        if path == "/api/import/commit":
            return self._import_commit(payload)
        if path == "/api/assistant":
            try:
                data = load()
                return self._json(answer_question(
                    self._visible_horses(data),
                    payload.get("question", ""),
                    expenses=self._visible_expenses(data),
                    context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
                ))
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        transition_match = re.fullmatch(r"/api/horses/([^/]+)/transition", path)
        if transition_match:
            return self._transition(transition_match.group(1), payload)
        workout_match = re.fullmatch(r"/api/horses/([^/]+)/workouts", path)
        if workout_match:
            return self._workout(workout_match.group(1), payload)
        legacy_match = re.fullmatch(r"/api/horses/([^/]+)/(train|undo)", path)
        if legacy_match:
            return self._workout(legacy_match.group(1), {"delta": 1 if legacy_match.group(2) == "train" else -1})
        self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        expense_match = re.fullmatch(r"/api/expenses/([^/]+)", path)
        if expense_match:
            try:
                payload = self._body()
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return self._update_expense(expense_match.group(1), payload)
        match = re.fullmatch(r"/api/horses/([^/]+)", path)
        if not match:
            return self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)
        try:
            payload = self._body()
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        horse_id = match.group(1)
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            for index, current in enumerate(data["horses"]):
                if current["id"] == horse_id and current.get("workspaceId") == workspace:
                    horse = validate_horse(payload, existing=current, stage=current.get("stage"))
                    data["horses"][index] = horse
                    return horse
            raise LookupError

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        account_match = re.fullmatch(r"/api/account/emails/([^/]+)", path)
        if account_match:
            email = unquote(account_match.group(1)).strip().lower()

            def remove_access(data):
                current = self._account(data)
                workspace = current.get("workspaceId") if current else None
                members = [item for item in data["accounts"] if item.get("workspaceId") == workspace]
                target = next((item for item in members if item.get("email") == email), None)
                if not target:
                    raise LookupError
                if target.get("email") == current.get("email"):
                    raise ValueError("Você não pode remover o e-mail que está usando agora.")
                if len(members) <= 1:
                    raise ValueError("A conta precisa manter pelo menos um e-mail de acesso.")
                data["accounts"].remove(target)
                for key, session in list(data.get("sessions", {}).items()):
                    if session.get("email") == email:
                        data["sessions"].pop(key, None)
                return True

            try:
                update(remove_access)
                return self._json({"ok": True})
            except LookupError:
                return self._json({"error": "E-mail não encontrado nesta conta."}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
        expense_match = re.fullmatch(r"/api/expenses/([^/]+)", path)
        if expense_match:
            expense_id = expense_match.group(1)
            snapshot = load()
            workspace = self._workspace(snapshot)

            def remove_expense(data):
                before = len(data["expenses"])
                data["expenses"] = [
                    expense for expense in data["expenses"]
                    if expense["id"] != expense_id or expense.get("workspaceId") != workspace
                ]
                return before != len(data["expenses"])

            if update(remove_expense):
                return self._json({"ok": True})
            return self._json({"error": "Despesa não encontrada."}, HTTPStatus.NOT_FOUND)
        match = re.fullmatch(r"/api/horses/([^/]+)", path)
        if not match:
            return self._json({"error": "Rota não encontrada."}, HTTPStatus.NOT_FOUND)
        horse_id = match.group(1)
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            before = len(data["horses"])
            data["horses"] = [
                horse for horse in data["horses"]
                if horse["id"] != horse_id or horse.get("workspaceId") != workspace
            ]
            return before != len(data["horses"])

        if update(mutate):
            self._json({"ok": True})
        else:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)

    def _add_account_email(self, payload):
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if not EMAIL_RE.match(email) or len(password) < 6:
            return self._json({"error": "Informe um e-mail válido e uma senha com 6 caracteres ou mais."}, HTTPStatus.BAD_REQUEST)

        def mutate(data):
            if any(account.get("email") == email for account in data["accounts"]):
                raise FileExistsError
            workspace = self._workspace(data)
            if not workspace:
                raise PermissionError
            data["accounts"].append(new_password_record(email, password, workspace_id=workspace))
            return {"email": email}

        try:
            result = update(mutate)
        except FileExistsError:
            return self._json({"error": "Este e-mail já está cadastrado."}, HTTPStatus.CONFLICT)
        except PermissionError:
            return self._json({"error": "Faça login novamente."}, HTTPStatus.UNAUTHORIZED)
        self._json(result, HTTPStatus.CREATED)

    def _change_password(self, payload):
        current_password = str(payload.get("currentPassword", ""))
        new_password = str(payload.get("newPassword", ""))
        if len(new_password) < 6:
            return self._json({"error": "A nova senha precisa ter pelo menos 6 caracteres."}, HTTPStatus.BAD_REQUEST)

        def mutate(data):
            account = self._account(data)
            if not account or not verify(account, account.get("email", ""), current_password):
                raise PermissionError
            replacement = new_password_record(account["email"], new_password, workspace_id=account["workspaceId"])
            account.update({
                "salt": replacement["salt"],
                "password_hash": replacement["password_hash"],
                "iterations": replacement["iterations"],
            })
            return {"ok": True}

        try:
            self._json(update(mutate))
        except PermissionError:
            self._json({"error": "A senha atual está incorreta."}, HTTPStatus.UNAUTHORIZED)

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
        if not verify(account, email, str(payload.get("password", ""))):
            return self._json({"error": "E-mail ou senha incorretos."}, HTTPStatus.UNAUTHORIZED)
        token = update(lambda current: create_session(current, account["email"]))
        self._json({"ok": True, "email": account["email"]}, cookie=self._session_cookie(token))

    def _create_horse(self, payload):
        try:
            horse = validate_horse(payload, stage=str(payload.get("stage") or "training"))
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        data = load()
        horse["workspaceId"] = self._workspace(data)
        mutation_id = self._mutation_id()
        self._json(update(lambda data: apply_once(data, mutation_id, lambda: self._insert(data, horse))), HTTPStatus.CREATED)

    def _create_expense(self, payload):
        data = load()
        workspace = self._workspace(data)
        try:
            expense = validate_expense(payload)
            if expense.get("scope") == "horse" and not any(
                horse.get("id") == expense.get("horseId") for horse in self._visible_horses(data)
            ):
                raise ValueError("O cavalo selecionado não pertence a esta conta.")
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        expense["workspaceId"] = workspace
        mutation_id = self._mutation_id()

        def mutate(current):
            return apply_once(current, mutation_id, lambda: self._insert_expense(current, expense))

        self._json(update(mutate), HTTPStatus.CREATED)

    @staticmethod
    def _insert_expense(data, expense):
        data["expenses"].insert(0, expense)
        return expense

    def _update_expense(self, expense_id, payload):
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            for index, current in enumerate(data["expenses"]):
                if current.get("id") != expense_id or current.get("workspaceId") != workspace:
                    continue
                expense = validate_expense(payload, existing=current)
                if expense.get("scope") == "horse" and not any(
                    horse.get("id") == expense.get("horseId") and horse.get("workspaceId") == workspace
                    for horse in data["horses"]
                ):
                    raise ValueError("O cavalo selecionado não pertence a esta conta.")
                data["expenses"][index] = expense
                return expense
            raise LookupError

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Despesa não encontrada."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _expense_import_preview(self, payload):
        source_type = str(payload.get("sourceType") or "notes")
        try:
            if source_type == "spreadsheet":
                result = parse_expense_spreadsheet(
                    str(payload.get("filename") or "custos.xlsx"),
                    str(payload.get("contentBase64") or ""),
                )
            elif source_type == "notes":
                result = parse_expense_notes(str(payload.get("text") or ""))
            else:
                raise ValueError("Tipo de importação de custos inválido.")
        except ValueError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        self._json(result)

    def _expense_import_commit(self, payload):
        records = payload.get("records")
        if not isinstance(records, list) or not records or len(records) > 2_000:
            return self._json({"error": "Selecione entre 1 e 2.000 despesas."}, HTTPStatus.BAD_REQUEST)
        mutation_id = self._mutation_id()
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            def operation():
                imported = []
                skipped = []
                for index, candidate in enumerate(records, 1):
                    if not isinstance(candidate, dict):
                        skipped.append({"row": index, "reason": "Despesa inválida"})
                        continue
                    try:
                        expense = validate_expense({**candidate, "scope": "general", "horseId": ""})
                    except (TypeError, ValueError) as exc:
                        skipped.append({"row": index, "reason": str(exc)})
                        continue
                    expense["workspaceId"] = workspace
                    expense["importOrigin"] = str(candidate.get("importOrigin") or "Importação")[:120]
                    data["expenses"].insert(0, expense)
                    imported.append(expense)
                return {"imported": len(imported), "skipped": skipped, "expenses": imported}
            return apply_once(data, mutation_id, operation)

        result = update(mutate)
        status = HTTPStatus.CREATED if result["imported"] else HTTPStatus.BAD_REQUEST
        self._json(result if result["imported"] else {**result, "error": "Nenhuma despesa pôde ser importada."}, status)

    def _import_preview(self, payload):
        source_type = str(payload.get("sourceType") or "text")
        default_stage = str(payload.get("defaultStage") or "training")
        try:
            if source_type == "spreadsheet":
                result = parse_spreadsheet(
                    str(payload.get("filename") or "planilha.xlsx"),
                    str(payload.get("contentBase64") or ""),
                    default_stage,
                )
            elif source_type in ("text", "voice", "document"):
                labels = {"voice": "Ditado", "document": "Documento", "text": "Anotações"}
                result = parse_notes(str(payload.get("text") or ""), default_stage, labels[source_type])
            else:
                raise ValueError("Tipo de importação inválido.")
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        data = load()
        horses = list(self._visible_horses(data))
        for record in result["records"]:
            duplicate = duplicate_of(record, horses)
            record["duplicate"] = duplicate
            record["selected"] = not record["issues"] and not duplicate
            if record.get("name"):
                horses.append(record)
        return self._json(result)

    def _import_commit(self, payload):
        records = payload.get("records")
        if not isinstance(records, list) or not records or len(records) > 2_000:
            return self._json({"error": "Selecione entre 1 e 2.000 cadastros."}, HTTPStatus.BAD_REQUEST)
        mutation_id = self._mutation_id()
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            def operation():
                imported = []
                skipped = []
                for index, candidate in enumerate(records, 1):
                    if not isinstance(candidate, dict):
                        skipped.append({"row": index, "reason": "Cadastro inválido"})
                        continue
                    normalized = refresh_record(candidate, str(candidate.get("stage") or "training"))
                    if normalized["issues"]:
                        skipped.append({"row": index, "reason": "; ".join(normalized["issues"])})
                        continue
                    visible = [item for item in data["horses"] if item.get("workspaceId") == workspace]
                    duplicate = duplicate_of(normalized, visible)
                    if duplicate and not candidate.get("allowDuplicate"):
                        skipped.append({"row": index, "reason": f"Possível duplicado de {duplicate}"})
                        continue
                    try:
                        horse = validate_horse(normalized, stage=normalized["stage"])
                    except ValueError as exc:
                        skipped.append({"row": index, "reason": str(exc)})
                        continue
                    horse["importOrigin"] = normalized.get("importOrigin")
                    horse["workspaceId"] = workspace
                    data["horses"].insert(0, horse)
                    imported.append(horse)
                return {"imported": len(imported), "skipped": skipped, "horses": imported}
            return apply_once(data, mutation_id, operation)

        result = update(mutate)
        status = HTTPStatus.CREATED if result["imported"] else HTTPStatus.BAD_REQUEST
        self._json(result if result["imported"] else {**result, "error": "Nenhum cadastro pôde ser importado."}, status)

    @staticmethod
    def _insert(data, horse):
        data["horses"].insert(0, horse)
        return horse

    def _transition(self, horse_id, payload):
        target = str(payload.get("target") or "")
        mutation_id = self._mutation_id()
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            def operation():
                horse = next((item for item in data["horses"] if item["id"] == horse_id and item.get("workspaceId") == workspace), None)
                if not horse:
                    raise LookupError
                return transition_horse(horse, target, payload=payload)
            return apply_once(data, mutation_id, operation)

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)

    def _workout(self, horse_id, payload):
        try:
            delta = int(payload.get("delta", 0))
        except (TypeError, ValueError):
            delta = 0
        if delta not in (-1, 1):
            return self._json({"error": "Alteração de treino inválida."}, HTTPStatus.BAD_REQUEST)
        mutation_id = self._mutation_id()
        snapshot = load()
        workspace = self._workspace(snapshot)

        def mutate(data):
            def operation():
                horse = next((item for item in data["horses"] if item["id"] == horse_id and item.get("workspaceId") == workspace), None)
                if not horse:
                    raise LookupError
                return change_workout(horse, delta)
            return apply_once(data, mutation_id, operation)

        try:
            self._json(update(mutate))
        except LookupError:
            self._json({"error": "Cavalo não encontrado."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)

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
    server = AppHTTPServer((args.host, args.port), Handler)
    browser_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{browser_host}:{args.port}"
    lines = [f"Cocheira RADAMÉS disponível neste computador: {url}"]
    if args.host == "0.0.0.0":
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                local_ip = probe.getsockname()[0]
            lines.append(f"No celular conectado ao mesmo Wi-Fi: http://{local_ip}:{args.port}")
        except OSError:
            lines.append("No celular, use o endereço IPv4 deste computador seguido de :8000.")
    lines.append("Pressione Ctrl+C para encerrar.")
    print("\n".join(lines))
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
