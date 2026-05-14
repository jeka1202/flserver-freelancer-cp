from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import ACCOUNTS_DIR, IONCROSS_DIR, STATIC_DIR
from .repository import Repository, money
from .utils import parse_amount
from .views import render_admin, render_admin_account, render_cabinet, render_login


class Handler(BaseHTTPRequestHandler):
    repo: Repository
    sessions: dict[str, tuple[str, str]] = {}
    flashes: dict[str, tuple[bool, str]] = {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self.send_html(render_login(self.repo))
        elif path == "/cabinet":
            session = self.current_session()
            if not session:
                self.redirect("/")
                return
            flash = self.pop_flash()
            if flash:
                ok, text = flash
                self.send_html(render_cabinet(session[0], session[1], message=text if ok else "", error="" if ok else text))
            else:
                self.send_html(render_cabinet(session[0], session[1]))
        elif path == "/logout":
            self.logout()
        elif path == "/admin":
            self.send_html(render_admin(self.repo))
        elif path.startswith("/admin/account/"):
            account_id = urllib.parse.unquote(path.split("/", 3)[3]).lower()
            account = self.repo.by_id.get(account_id)
            self.send_html(render_admin_account(account)) if account else self.send_error(HTTPStatus.NOT_FOUND)
        elif path == "/api/accounts":
            self.send_json(self.admin_json())
        elif path.startswith("/static/"):
            self.send_static(path.removeprefix("/static/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        form = self.read_form()
        if path == "/login":
            self.handle_login(form)
        elif path == "/finance/transfer":
            self.handle_transfer(form)
        elif path == "/finance/bank":
            self.handle_bank(form)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("content-length", "0"))
        return urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))

    def handle_login(self, form: dict[str, list[str]]) -> None:
        login = (form.get("login") or form.get("character") or [""])[0].strip()
        password = form.get("password", [""])[0]
        character_hint = form.get("character", [""])[0]
        match = self.repo.authenticate(login, password, character_hint)
        if not match:
            self.send_html(render_login(self.repo, "Логин или пароль не совпали. Можно войти старым способом: ID аккаунта без пароля."), HTTPStatus.UNAUTHORIZED)
            return
        account, character = match
        token = secrets.token_urlsafe(32)
        self.sessions[token] = (account["id"], character["file"])
        self.redirect("/cabinet", token=token)

    def handle_transfer(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.send_finance_response(False, "Сессия истекла. Войдите заново.", HTTPStatus.UNAUTHORIZED)
            return
        account, character = session
        target = (form.get("target", [""])[0]).strip()
        amount = parse_amount(form.get("amount", [""])[0])
        ok, text = self.repo.transfer_to_character(account["id"], character["file"], target, amount)
        self.finish_finance_operation(ok, text)

    def handle_bank(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.send_finance_response(False, "Сессия истекла. Войдите заново.", HTTPStatus.UNAUTHORIZED)
            return
        account, character = session
        action = form.get("action", [""])[0]
        amount = parse_amount(form.get("amount", [""])[0])
        ok, text = self.repo.bank_operation(account["id"], character["file"], action, amount)
        self.finish_finance_operation(ok, text)

    def finish_finance_operation(self, ok: bool, text: str) -> None:
        if self.wants_json():
            self.send_finance_response(ok, text)
            return
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def wants_json(self) -> bool:
        return self.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in self.headers.get("Accept", "")

    def send_finance_response(self, ok: bool, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        session = self.current_session()
        account, character = session if session else ({"bank": 0}, {"money": 0, "bank": 0})
        self.send_json({
            "ok": ok,
            "message": text,
            "character_money": int(character.get("money", 0)),
            "character_money_formatted": money(int(character.get("money", 0))),
            "bank": int(account.get("bank", character.get("bank", 0))),
            "bank_formatted": money(int(account.get("bank", character.get("bank", 0)))),
        }, status=status)

    def redirect(self, location: str, token: str | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if token:
            self.send_header("Set-Cookie", f"flpanel={token}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()

    def current_token(self) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "flpanel":
                return value
        return ""

    def current_session(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        stored = self.sessions.get(self.current_token())
        if not stored:
            return None
        account = self.repo.by_id.get(stored[0].lower())
        if not account:
            return None
        for character in account["characters"]:
            if character["file"] == stored[1]:
                return account, character
        return None

    def set_flash(self, ok: bool, text: str) -> None:
        token = self.current_token()
        if token:
            self.flashes[token] = (ok, text)

    def pop_flash(self) -> tuple[bool, str] | None:
        token = self.current_token()
        return self.flashes.pop(token, None) if token else None

    def logout(self) -> None:
        token = self.current_token()
        if token:
            self.sessions.pop(token, None)
            self.flashes.pop(token, None)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", "flpanel=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()

    def admin_json(self) -> list[dict[str, Any]]:
        safe_accounts = []
        for account in self.repo.accounts:
            safe_accounts.append({
                "id": account["id"],
                "created": account["created"],
                "bank": account["bank"],
                "characters": account["characters"],
                "character_count": account["character_count"],
                "total_money": account["total_money"],
                "max_rank": account["max_rank"],
            })
        return safe_accounts

    def send_static(self, relative_path: str) -> None:
        path = (STATIC_DIR / relative_path).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        content_type = "text/css; charset=utf-8" if path.suffix == ".css" else "application/javascript; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Freelancer account web panel")
    parser.add_argument("--host", default=os.environ.get("FL_PANEL_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("FL_PANEL_PORT", "8080")), type=int)
    parser.add_argument("--accounts", default=str(ACCOUNTS_DIR), type=Path)
    parser.add_argument("--ioncross", default=str(IONCROSS_DIR), type=Path)
    args = parser.parse_args()

    repo = Repository(args.accounts, args.ioncross)
    Handler.repo = repo
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Freelancer Account Panel: http://{args.host}:{args.port}")
    print(f"Loaded {len(repo.accounts)} accounts and {repo.public_stats()['characters']} characters")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
