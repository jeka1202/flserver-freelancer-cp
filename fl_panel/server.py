from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import secrets
import sys
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import ACCOUNTS_DIR, IONCROSS_DIR, STATIC_DIR
from .ioncross_db import sync_ioncross_names
from .repository import Repository, money
from .cargo_service import analyze_cargo
from .views import render_admin, render_admin_account, render_admin_pilot, render_cabinet, render_login, render_craft_panel, render_finance_history_panel, render_hold_panel, render_warehouse_tab_panel, render_contracts_panel
from .warehouse import add_test_item, remove_test_item, transfer_test_item, admin_add_item_to_warehouse, admin_remove_item_from_warehouse, admin_move_item_between_warehouses, warehouse_to_hold_via_flhook, hold_to_warehouse_smart, current_base_warehouse, all_character_warehouses, get_warehouse_history, parse_positive_int
from .craft import start_craft_job, claim_craft_job, cancel_craft_job, sync_craft_recipes, current_craft_context
from .contracts import create_contract, buy_contract, cancel_contract, current_contract_context
from .finance_history import get_finance_history
from .flhook_client import flhook_status, status_to_dict
from .admin_service import online_pilots, run_admin_flhook_command, admin_live_location, apply_admin_reputation_changes


def parse_finance_amount(value: str) -> int:
    cleaned = re.sub(r"[\s\u00A0\u202F_.,']", "", str(value).strip())

    if not cleaned or not re.fullmatch(r"\d+", cleaned):
        return -1

    amount = int(cleaned)
    return amount if amount > 0 else -1


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
            account, character = session
            hold_rows, hold_source = self.current_hold_cargo_rows(character)
            live_character = dict(character)
            live_character["cargo_rows"] = hold_rows
            live_character["hold_source"] = hold_source

            if flash:
                ok, text = flash
<<<<<<< Updated upstream
                self.send_html(render_cabinet(self.repo, session[0], session[1], message=text if ok else "", error="" if ok else text))
            else:
                self.send_html(render_cabinet(self.repo, session[0], session[1]))
=======
                self.send_html(render_cabinet(account, live_character, message=text if ok else "", error="" if ok else text))
            else:
                self.send_html(render_cabinet(account, live_character))
>>>>>>> Stashed changes
        elif path == "/logout":
            self.logout()
        elif path == "/game":
            self.send_static("game.html")
        elif path == "/admin":
            self.send_html(render_admin(self.repo, online_pilots(self.repo)))
        elif path.startswith("/admin/pilot/"):
            parts = path.split("/", 4)
            if len(parts) < 5:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            account_id = urllib.parse.unquote(parts[3])
            character_file = urllib.parse.unquote(parts[4])
            found = self.repo.refresh_character(account_id, character_file) or self.repo.find_character_by_file(account_id, character_file)
            if not found:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            flash = self.pop_flash()
            account, character = found
            character["admin_live_location"] = admin_live_location(self.repo, character)
            hold_rows, hold_source = self.current_hold_cargo_rows(character)
            cargo_summary = analyze_cargo(character.get("ship_token", character.get("ship", {}).get("nickname", "")), hold_rows)
            cargo_summary["source"] = hold_source
            all_warehouses = all_character_warehouses(account["id"], character)
            online = self.repo.flhook_online(character.get("name", ""))
            message = ""
            error = ""
            if flash:
                ok, text = flash
                message = text if ok else ""
                error = "" if ok else text
            self.send_html(render_admin_pilot(account, character, cargo_summary, all_warehouses, online=online, message=message, error=error))
        elif path.startswith("/admin/account/"):
            account_id = urllib.parse.unquote(path.split("/", 3)[3]).lower()
            account = self.repo.by_id.get(account_id)
            self.send_html(render_admin_account(account)) if account else self.send_error(HTTPStatus.NOT_FOUND)
        elif path == "/api/live":
            self.handle_live_status()
        elif path == "/api/flhook":
            self.handle_flhook_status()
        elif path == "/api/accounts":
            self.send_json(self.admin_json())
<<<<<<< Updated upstream
        elif path == "/api/game-data":
            query = urllib.parse.parse_qs(parsed.query)
            self.send_json(self.repo.public_game_data((query.get("system") or ["Li01"])[0]))
=======
        elif path == "/api/craft":
            self.send_craft_response(True, "")
>>>>>>> Stashed changes
        elif path.startswith("/static/"):
            self.send_static(path.removeprefix("/static/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        form = self.read_form()
        if path == "/login":
            self.handle_login(form)
        elif path == "/admin/flhook":
            self.handle_admin_flhook(form)
        elif path == "/admin/warehouse/add":
            self.handle_admin_warehouse_add(form)
        elif path == "/admin/warehouse/remove":
            self.handle_admin_warehouse_remove(form)
        elif path == "/admin/warehouse/move":
            self.handle_admin_warehouse_move(form)
        elif path == "/admin/reputation/update":
            self.handle_admin_reputation_update(form)
        elif path == "/finance/transfer":
            self.handle_transfer(form)
        elif path == "/finance/bank":
            self.handle_bank(form)
<<<<<<< Updated upstream
        elif path == "/craft":
            self.handle_craft(form)
=======
        elif path == "/warehouse/add":
            self.handle_warehouse_add(form)
        elif path == "/warehouse/remove":
            self.handle_warehouse_remove(form)
        elif path == "/warehouse/transfer":
            # v69 policy: pilot-to-pilot transfer is SQLite warehouse -> SQLite warehouse only.
            # It must not edit .fl files and must not call FLHook.
            self.handle_warehouse_transfer(form)
        elif path == "/warehouse/to-hold":
            self.handle_warehouse_to_hold(form)
        elif path == "/craft/start":
            self.handle_craft_start(form)
        elif path == "/craft/claim":
            self.handle_craft_claim(form)
        elif path == "/craft/cancel":
            self.handle_craft_cancel(form)
        elif path == "/contracts/create":
            self.handle_contract_create(form)
        elif path == "/contracts/buy":
            self.handle_contract_buy(form)
        elif path == "/contracts/cancel":
            self.handle_contract_cancel(form)
>>>>>>> Stashed changes
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("content-length", "0"))
        return urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))




    @staticmethod
    def flhook_cargo_rows_from_enum(items: list[dict[str, Any]]) -> list[str]:
        """Convert FLHook enumcargo rows to Freelancer cargo-row compatible strings."""
        aggregated: dict[str, int] = {}

        for item in items or []:
            archid = str(item.get("archid", "")).strip()
            count = int(item.get("count", 0) or 0)

            if not archid or count <= 0:
                continue

            aggregated[archid] = aggregated.get(archid, 0) + count

        return [f"{archid}, {count}" for archid, count in aggregated.items() if count > 0]

    def current_hold_cargo_rows(self, character: dict[str, Any]) -> tuple[list[str], str]:
        """Return live hold cargo rows.

        Online/in-game pilot:
          use FLHook enumcargo, because the .fl file may still contain old cargo
          until the server saves the character.

        Offline/no FLHook:
          fall back to parsed cargo = lines from the .fl save file.
        """
        fallback_rows = list(character.get("cargo_rows", []) or [])
        char_name = str(character.get("name") or "").strip()

        if not char_name:
            return fallback_rows, "file"

        try:
            flhook_client = getattr(self.repo, "flhook", None)
            if not flhook_client or not flhook_client.enabled:
                return fallback_rows, "file"

            items = flhook_client.enum_cargo_items(char_name)
            return self.flhook_cargo_rows_from_enum(items), "flhook"
        except Exception:
            return fallback_rows, "file"


    def refresh_session(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        session = self.current_session()
        if not session:
            return None
        account, character = session
        refreshed = self.repo.refresh_character(account["id"], character["file"])
        return refreshed or session

    def live_payload(self, ok: bool = True, message: str = "") -> dict[str, Any]:
        session = self.refresh_session()
        if not session:
            return {"ok": False, "message": "Сессия истекла. Войдите заново."}

        account, character = session
        hold_rows, hold_source = self.current_hold_cargo_rows(character)
        cargo_summary = analyze_cargo(character.get("ship_token", character.get("ship", {}).get("nickname", "")), hold_rows)
        cargo_summary["source"] = hold_source
        warehouse = current_base_warehouse(account["id"], character)
        warehouse_history = get_warehouse_history(account["id"], character["file"], (warehouse.get("location") or {}).get("token", ""), limit=80)
        all_warehouses = all_character_warehouses(account["id"], character)
        contracts_context = current_contract_context(account["id"], character)
        finance_history_html = render_finance_history_panel(get_finance_history(account["id"], character["file"], limit=80))

        # Do not poll FLHook here. /api/live runs every few seconds and the UI
        # currently does not use pilot_online. Real operations still check FLHook
        # online/offline status at execution time.
        online = None

        return {
            "ok": ok,
            "message": message,
            "character_money": int(character.get("money", 0)),
            "character_money_formatted": money(int(character.get("money", 0))),
            "bank": int(account.get("bank", character.get("bank", 0))),
            "bank_formatted": money(int(account.get("bank", character.get("bank", 0)))),
            "hold_html": render_hold_panel(cargo_summary),
            "hold_source": hold_source,
            "warehouse_html": render_warehouse_tab_panel(warehouse, warehouse_history, all_warehouses),
            "contracts_html": render_contracts_panel(contracts_context, warehouse, account["id"], character),
            "finance_history_html": finance_history_html,
            "pilot_online": online,
        }

    def handle_live_status(self) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Сессия истекла. Войдите заново."}, HTTPStatus.UNAUTHORIZED)
            return
        self.send_json(self.live_payload(True, ""))

    def finish_warehouse_operation(self, ok: bool, text: str) -> None:
        if self.wants_json():
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.send_json(self.live_payload(ok, text), status=status)
            return
        if ok:
            self.refresh_session()
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def handle_flhook_status(self) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Сессия истекла. Войдите заново."}, HTTPStatus.UNAUTHORIZED)
            return

        _account, character = session
        status = flhook_status(character.get("name", ""))
        payload = status_to_dict(status, character.get("name", ""))
        payload["ok"] = bool(status.ok)
        self.send_json(payload)


    def handle_admin_flhook(self, form: dict[str, list[str]]) -> None:
        command = form.get("command", [""])[0]
        result = run_admin_flhook_command(self.repo, command)
        self.send_html(render_admin(self.repo, online_pilots(self.repo), command_result=result))


    def admin_character_from_form(self, form: dict[str, list[str]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
        account_id = (form.get("account_id", [""])[0] or "").strip()
        character_file = (form.get("character_file", [""])[0] or "").strip()
        if not account_id or not character_file:
            return None
        return self.repo.find_character_by_file(account_id, character_file)

    @staticmethod
    def admin_location_from_form(form: dict[str, list[str]], prefix: str = "") -> dict[str, str]:
        key = f"{prefix}location_hash"
        name_key = f"{prefix}location_name"
        type_key = f"{prefix}location_type"

        token = (form.get(key, [""])[0] or "").strip()
        name = (form.get(name_key, [""])[0] or "").strip()
        loc_type = (form.get(type_key, ["base"])[0] or "base").strip() or "base"

        return {
            "token": token,
            "name": name or token,
            "type": loc_type,
        }

    def redirect_admin_pilot(self, account: dict[str, Any], character: dict[str, Any], ok: bool, text: str) -> None:
        token = self.current_token() or secrets.token_urlsafe(16)
        self.flashes[token] = (ok, text)
        self.redirect(
            f"/admin/pilot/{urllib.parse.quote(str(account.get('id') or ''), safe='')}/{urllib.parse.quote(str(character.get('file') or ''), safe='')}",
            token=token,
        )

    def handle_admin_warehouse_add(self, form: dict[str, list[str]]) -> None:
        found = self.admin_character_from_form(form)
        if not found:
            self.send_error(HTTPStatus.BAD_REQUEST, "Pilot not found")
            return

        account, character = found
        amount = parse_positive_int(form.get("amount", ["0"])[0])
        item_token = (form.get("item_token", [""])[0] or "").strip()
        location = self.admin_location_from_form(form)

        if not location.get("token"):
            self.redirect_admin_pilot(account, character, False, "Не выбран склад / база.")
            return

        ok, text = admin_add_item_to_warehouse(account["id"], character, item_token, amount, location)
        self.redirect_admin_pilot(account, character, ok, text)

    def handle_admin_warehouse_remove(self, form: dict[str, list[str]]) -> None:
        found = self.admin_character_from_form(form)
        if not found:
            self.send_error(HTTPStatus.BAD_REQUEST, "Pilot not found")
            return

        account, character = found
        amount = parse_positive_int(form.get("amount", ["0"])[0])
        item_token = (form.get("item_token", [""])[0] or "").strip()
        location = self.admin_location_from_form(form)

        if not location.get("token"):
            self.redirect_admin_pilot(account, character, False, "Не выбран склад / база.")
            return

        ok, text = admin_remove_item_from_warehouse(account["id"], character, item_token, amount, location)
        self.redirect_admin_pilot(account, character, ok, text)

    def handle_admin_warehouse_move(self, form: dict[str, list[str]]) -> None:
        found = self.admin_character_from_form(form)
        if not found:
            self.send_error(HTTPStatus.BAD_REQUEST, "Pilot not found")
            return

        account, character = found
        amount = parse_positive_int(form.get("amount", ["0"])[0])
        item_token = (form.get("item_token", [""])[0] or "").strip()
        target = (form.get("target", [""])[0] or "").strip()
        source_location = self.admin_location_from_form(form, "source_")
        target_location = self.admin_location_from_form(form, "target_")

        if not source_location.get("token") or not target_location.get("token"):
            self.redirect_admin_pilot(account, character, False, "Не выбран исходный или целевой склад.")
            return

        ok, text = admin_move_item_between_warehouses(
            self.repo,
            account["id"],
            character,
            item_token,
            amount,
            source_location,
            target,
            target_location,
        )
        self.redirect_admin_pilot(account, character, ok, text)


    def handle_admin_reputation_update(self, form: dict[str, list[str]]) -> None:
        found = self.admin_character_from_form(form)
        if not found:
            self.send_error(HTTPStatus.BAD_REQUEST, "Pilot not found")
            return

        account, character = found
        codes = form.get("rep_code", [])
        values = form.get("rep_value", [])
        old_values = form.get("rep_old", [])

        changes = []
        for index, code in enumerate(codes):
            changes.append({
                "code": code,
                "value": values[index] if index < len(values) else "",
                "old": old_values[index] if index < len(old_values) else "",
            })

        result = apply_admin_reputation_changes(self.repo, character, changes)
        self.redirect_admin_pilot(account, character, bool(result.get("ok")), str(result.get("message") or ""))

    def handle_login(self, form: dict[str, list[str]]) -> None:
        login = (form.get("login") or [""])[0].strip()
        password = form.get("password", [""])[0]
        match = self.repo.authenticate(login, password)
        if not match:
            try:
                print(self.repo.debug_auth_login(login, password))
            except Exception as exc:
                print(f"AUTH login: WRONG ({exc})")
            self.send_html(render_login(self.repo, "Имя пилота или код не совпали. Проверь: код должен быть создан после /set cashcode, а панель читает только *-givecash.ini."), HTTPStatus.UNAUTHORIZED)
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
        amount = parse_finance_amount(form.get("amount", [""])[0])
        ok, text = self.repo.transfer_to_character(account["id"], character["file"], target, amount)
        self.finish_finance_operation(ok, text)

    def handle_bank(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.send_finance_response(False, "Сессия истекла. Войдите заново.", HTTPStatus.UNAUTHORIZED)
            return
        account, character = session
        action = form.get("action", [""])[0]
        amount = parse_finance_amount(form.get("amount", [""])[0])
        ok, text = self.repo.bank_operation(account["id"], character["file"], action, amount)
        self.finish_finance_operation(ok, text)

<<<<<<< Updated upstream
    def handle_craft(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.redirect("/")
            return
        account, character = session
        recipe_id = form.get("recipe_id", [""])[0].strip()
        ok, text = self.repo.craft_item(account["id"], character["file"], recipe_id)
        self.set_flash(ok, text)
        self.redirect("/cabinet")

=======


    def warehouse_location_from_form(self, form: dict[str, list[str]], character: dict[str, Any]) -> dict[str, str] | None:
        location_hash = (form.get("location_hash", [""])[0] or "").strip()
        location_name = (form.get("location_name", [""])[0] or "").strip()
        location_type = (form.get("location_type", [""])[0] or "base").strip() or "base"

        if not location_hash:
            return None

        return {
            "token": location_hash,
            "name": location_name or location_hash,
            "type": location_type,
        }

    def handle_warehouse_add(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        item_hash = form.get("item_hash", [""])[0]
        amount = parse_positive_int(form.get("amount", [""])[0])

        ok, text = hold_to_warehouse_smart(self.repo, account["id"], character, item_hash, amount)
        self.finish_warehouse_operation(ok, text)

    def handle_warehouse_remove(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        item_hash = form.get("item_hash", [""])[0]
        amount = parse_positive_int(form.get("amount", [""])[0])

        source_location = self.warehouse_location_from_form(form, character)
        ok, text = remove_test_item(account["id"], character, item_hash, amount, source_location)
        self.finish_warehouse_operation(ok, text)





    def handle_warehouse_to_hold(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        item_hash = form.get("item_hash", [""])[0]
        amount = parse_positive_int(form.get("amount", [""])[0])

        ok, text = warehouse_to_hold_via_flhook(self.repo, account["id"], character, item_hash, amount)
        self.finish_warehouse_operation(ok, text)


    def handle_warehouse_transfer(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        item_hash = form.get("item_hash", [""])[0]
        target = form.get("target", [""])[0]
        amount = parse_positive_int(form.get("amount", [""])[0])

        source_location = self.warehouse_location_from_form(form, character)
        started_at = time.perf_counter()
        ok, text = transfer_test_item(self.repo, account["id"], character, item_hash, target, amount, source_location)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        if elapsed_ms >= 250:
            print(f"WAREHOUSE transfer SQL: {elapsed_ms} ms {'OK' if ok else 'WRONG'}")

        # v74/v76 speedup:
        # Pilot-to-pilot transfer is SQLite warehouse -> SQLite warehouse only.
        # Do not build full /api/live payload here. Rendering hold + warehouse +
        # finance history can take seconds and is not needed to confirm the SQL
        # transaction. The browser will refresh panels asynchronously.
        if self.wants_json():
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.send_json({
                "ok": ok,
                "message": text,
                "refresh_later": bool(ok),
                "operation": "warehouse_transfer",
            }, status=status)
            return

        self.finish_warehouse_operation(ok, text)


    def handle_craft_start(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        recipe_code = form.get("recipe_code", [""])[0]
        quantity = parse_positive_int(form.get("quantity", ["1"])[0])

        ok, text = start_craft_job(account["id"], character, recipe_code, quantity)
        if self.wants_json():
            self.send_craft_response(ok, text, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
            return
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def handle_craft_claim(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        job_id = parse_positive_int(form.get("job_id", [""])[0])

        ok, text = claim_craft_job(account["id"], character, job_id)
        if self.wants_json():
            self.send_craft_response(ok, text, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
            return
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def handle_craft_cancel(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        job_id = parse_positive_int(form.get("job_id", [""])[0])

        ok, text = cancel_craft_job(account["id"], character, job_id)
        if self.wants_json():
            self.send_craft_response(ok, text, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
            return
        self.set_flash(ok, text)
        self.redirect("/cabinet")


    def handle_contract_create(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            if self.wants_json():
                self.send_json({"ok": False, "message": "Сессия истекла. Войдите заново."}, HTTPStatus.UNAUTHORIZED)
                return
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        item_hash = form.get("item_hash", [""])[0]
        quantity = parse_positive_int(form.get("quantity", [""])[0])
        price = parse_finance_amount(form.get("price", [""])[0])
        lifetime_value = parse_positive_int(form.get("lifetime_value", [""])[0])
        lifetime_unit = form.get("lifetime_unit", ["hours"])[0]
        source_location = self.warehouse_location_from_form(form, character)

        ok, text = create_contract(account["id"], character, item_hash, quantity, price, lifetime_value, lifetime_unit, source_location)

        if self.wants_json():
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.send_json({
                "ok": ok,
                "message": text,
                "refresh_later": bool(ok),
                "operation": "contract_create",
            }, status=status)
            return

        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def handle_contract_buy(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        contract_id = parse_positive_int(form.get("contract_id", [""])[0])

        ok, text = buy_contract(self.repo, account["id"], character, contract_id)
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def handle_contract_cancel(self, form: dict[str, list[str]]) -> None:
        session = self.current_session()
        if not session:
            self.set_flash(False, "Сессия истекла. Войдите заново.")
            self.redirect("/")
            return

        account, character = session
        contract_id = parse_positive_int(form.get("contract_id", [""])[0])

        ok, text = cancel_contract(account["id"], character, contract_id)
        self.set_flash(ok, text)
        self.redirect("/cabinet")


>>>>>>> Stashed changes
    def finish_finance_operation(self, ok: bool, text: str) -> None:
        if self.wants_json():
            self.send_finance_response(ok, text)
            return
        self.set_flash(ok, text)
        self.redirect("/cabinet")

    def wants_json(self) -> bool:
        return self.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in self.headers.get("Accept", "")

    def send_craft_response(self, ok: bool, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Сессия истекла. Войдите заново.", "html": ""}, HTTPStatus.UNAUTHORIZED)
            return

        account, character = session
        html = render_craft_panel(current_craft_context(account["id"], character))
        self.send_json({
            "ok": ok,
            "message": text,
            "html": html,
        }, status=status)


    def send_finance_response(self, ok: bool, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        session = self.current_session()
        account, character = session if session else ({"id": "", "bank": 0}, {"file": "", "money": 0, "bank": 0})
        history_html = ""
        if session:
            history_html = render_finance_history_panel(get_finance_history(account["id"], character["file"], limit=80))

        self.send_json({
            "ok": ok,
            "message": text,
            "character_money": int(character.get("money", 0)),
            "character_money_formatted": money(int(character.get("money", 0))),
            "bank": int(account.get("bank", character.get("bank", 0))),
            "bank_formatted": money(int(account.get("bank", character.get("bank", 0)))),
            "finance_history_html": history_html,
        }, status=status)

    def redirect(self, location: str, token: str | None = None) -> None:
        try:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            if token:
                self.send_header("Set-Cookie", f"flpanel={token}; HttpOnly; SameSite=Lax; Path=/")
            self.end_headers()
        except OSError as exc:
            if self._is_client_disconnect(exc):
                return
            raise

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
        try:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "flpanel=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/")
            self.end_headers()
        except OSError as exc:
            if self._is_client_disconnect(exc):
                return
            raise

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


    def _is_client_disconnect(self, exc: BaseException) -> bool:
        if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return True

        winerror = getattr(exc, "winerror", None)
        if winerror in {10053, 10054, 10058}:
            return True

        errno_value = getattr(exc, "errno", None)
        if errno_value in {32, 104}:
            return True

        return False

    def _send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Send response body without noisy tracebacks if browser aborted request.

        Browsers may cancel /api/live fetches when the page is refreshed,
        closed, or another refresh starts. On Windows this shows up as
        ConnectionAbortedError [WinError 10053]. It is not a panel error.
        """
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except OSError as exc:
            if self._is_client_disconnect(exc):
                # Client/browser closed the socket. Ignore to keep console clean.
                return
            raise


    def send_static(self, relative_path: str) -> None:
        path = (STATIC_DIR / relative_path).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
<<<<<<< Updated upstream
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
=======
        suffix = path.suffix.lower()
        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".ttf": "font/ttf",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }
        content_type = content_types.get(suffix, "application/octet-stream")
        self._send_bytes(content, content_type, HTTPStatus.OK)
>>>>>>> Stashed changes

    def send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(content, "text/html; charset=utf-8", status)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self._send_bytes(content, "application/json; charset=utf-8", status)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))



def print_flhook_startup_status(repo: Repository) -> None:
    """Print clear FLHook connectivity status on panel startup."""
    try:
        client = getattr(repo, "flhook", None)
        if client is None:
            print("FLHook connect: WRONG (client not initialized)")
            return

        cfg = getattr(client, "config", None)
        host = getattr(cfg, "host", "unknown")
        port = getattr(cfg, "port", "unknown")

        if not getattr(client, "enabled", False):
            print(f"FLHook connect: WRONG ({host}:{port}, disabled)")
            return

        status = client.status()
        if status.connected and status.authenticated and status.ok:
            print(f"FLHook connect: OK ({status.host}:{status.port}, {status.command})")
        else:
            message = str(status.message or "no response").replace("\n", " ").strip()
            print(f"FLHook connect: WRONG ({status.host}:{status.port}, {message})")
    except Exception as exc:
        print(f"FLHook connect: WRONG ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Freelancer account web panel")
    parser.add_argument("--host", default=os.environ.get("FL_PANEL_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("FL_PANEL_PORT", "8080")), type=int)
    parser.add_argument("--accounts", default=str(ACCOUNTS_DIR), type=Path)
    parser.add_argument("--ioncross", default=str(IONCROSS_DIR), type=Path)
    args = parser.parse_args()

    try:
        sync_stats = sync_ioncross_names(args.ioncross)
        if sync_stats.get("found"):
            print(
                "IONCROSS sync: "
                f"files={sync_stats.get('files_total')} "
                f"changed={sync_stats.get('files_changed')} "
                f"skipped={sync_stats.get('files_skipped')} "
                f"imported={sync_stats.get('entries_imported')} "
                f"total={sync_stats.get('entries_total')} "
                f"aliases={sync_stats.get('aliases_total', sync_stats.get('aliases_added', 0))} "
                f"display_updates={sync_stats.get('display_updates')}"
            )
        else:
            print("IONCROSS sync: папка IONCROSS не найдена, пропускаю.")
    except Exception as exc:
        print(f"WARNING: IONCROSS sync failed: {exc}")

    try:
        craft_stats = sync_craft_recipes()
        print(
            "CRAFT sync: "
            f"files={craft_stats.get('files_total')} "
            f"changed={craft_stats.get('files_changed')} "
            f"recipes={craft_stats.get('recipes_total')}"
        )
        if craft_stats.get("errors"):
            print(f"CRAFT sync warnings: {len(craft_stats.get('errors', []))}")
    except Exception as exc:
        print(f"WARNING: CRAFT sync failed: {exc}")

    repo = Repository(args.accounts, args.ioncross)
    print_flhook_startup_status(repo)
    Handler.repo = repo
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Freelancer Account Panel: http://{args.host}:{args.port}")
    print(f"Loaded {len(repo.accounts)} accounts and {repo.public_stats()['characters']} characters")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")


if __name__ == "__main__":
    main()
