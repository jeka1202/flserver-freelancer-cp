from __future__ import annotations

import re
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import CRAFTING_RECIPES_PATH, DATA_DIR, VISIT_TYPES
from .crafting import CraftingSystem, read_cargo_inventory
from .finance import read_bank_balance, read_character_money, write_bank_balance, write_character_money
from .finance_history import log_finance_event
from .flhook_client import FlHookClient, FlHookError, FlHookUnavailable
from .gamedata import GameData
from .utils import (
    character_code_candidates,
    character_auth_code_file_status,
    normalize_auth_code,
    decode_fl_text,
    file_time,
    first,
    format_seconds,
    intish,
    parse_fl,
    read_text,
    split_csv,
)


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def character_name(data: dict[str, list[str]], file_path: Path) -> str:
    return decode_fl_text(first(data, "name")) or file_path.stem


def parse_loadout(data: dict[str, list[str]], key: str, gamedata: GameData) -> list[dict[str, str]]:
    loadout = []
    for raw in data.get(key, []):
        parts = split_csv(raw)
        item = gamedata.resolve(parts[0] if parts else "")
        loadout.append({
            "name": item["name"],
            "nickname": item["nickname"],
            "category": item["category_label"],
            "hardpoint": parts[1] if len(parts) > 1 and parts[1] else "—",
            "mounted": parts[2] if len(parts) > 2 else "",
        })
    return loadout


def parse_cargo(data: dict[str, list[str]], key: str, gamedata: GameData) -> list[dict[str, str]]:
    cargo = []
    for raw in data.get(key, []):
        parts = split_csv(raw)
        item = gamedata.resolve(parts[0] if parts else "")
        cargo.append({"name": item["name"], "nickname": item["nickname"], "category": item["category_label"], "count": parts[1] if len(parts) > 1 else "1", "raw": raw})
    return cargo


def parse_rep_group(data: dict[str, list[str]], gamedata: GameData) -> list[dict[str, str]]:
    groups = data.get("rep_group", [])
    reps = data.get("rep", [])
    result = []
    for index, code in enumerate(groups):
        faction = gamedata.resolve(code)
        result.append({"code": code, "name": faction["name"], "reputation": reps[index] if index < len(reps) else ""})
    return result


def parse_houses(data: dict[str, list[str]], gamedata: GameData) -> list[dict[str, str]]:
    houses = []
    for raw in data.get("house", []):
        parts = split_csv(raw)
        reputation = parts[0] if parts else "0"
        faction_code = parts[1] if len(parts) > 1 else ""
        faction = gamedata.resolve(faction_code)
        houses.append({"code": faction_code, "name": faction["name"], "reputation": reputation})
    houses.extend(parse_rep_group(data, gamedata))
    houses.sort(key=lambda item: float(item["reputation"]) if re.match(r"^-?\d+(\.\d+)?$", item["reputation"]) else 0, reverse=True)
    return houses


def parse_visits(data: dict[str, list[str]], gamedata: GameData) -> dict[str, Any]:
    raw_visits = []
    for raw in data.get("visit", [])[:250]:
        parts = split_csv(raw)
        target = gamedata.resolve(parts[0] if parts else "")
        visit_type = parts[1] if len(parts) > 1 else ""
        raw_visits.append({"code": parts[0] if parts else "", "name": target["name"], "nickname": target["nickname"], "type": VISIT_TYPES.get(visit_type, visit_type or "—")})
    return {
        "systems": [gamedata.resolve(value) for value in data.get("sys_visited", [])],
        "bases": [gamedata.resolve(value) for value in data.get("base_visited", [])],
        "holes": [gamedata.resolve(value) for value in data.get("holes_visited", [])],
        "raw": raw_visits,
        "raw_total": len(data.get("visit", [])),
    }




def _short_game_item(item: Any) -> dict[str, str]:
    return {"code": item.code, "nickname": item.nickname, "name": item.name}


def _unique_game_items(items: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for item in items:
        key = (item.code.lower(), item.nickname.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _matches_system_ini(path: Path, system_code: str) -> bool:
    return path.is_file() and path.suffix.lower() == ".ini" and path.stem.lower() == system_code.lower()


def _object_kind(raw: dict[str, str]) -> str:
    nickname = raw.get("nickname", "").lower()
    archetype = raw.get("archetype", "").lower()
    if "trade_lane" in nickname or "trade_lane" in archetype or "tradelane" in nickname:
        return "trade_lane"
    if raw.get("base"):
        return "base"
    if "jump" in nickname or "jump" in archetype:
        return "jump"
    if "planet" in nickname or "planet" in archetype:
        return "planet"
    if "sun" in nickname or "sun" in archetype:
        return "sun"
    return "object"


def parse_system_objects(system_code: str, gamedata: GameData, limit: int = 180) -> tuple[list[dict[str, Any]], str]:
    systems_dir = DATA_DIR / "UNIVERSE" / "SYSTEMS"
    system_ini = next((path for path in systems_dir.rglob("*.ini") if _matches_system_ini(path, system_code)), None) if systems_dir.exists() else None
    if not system_ini:
        return [], ""

    objects: list[dict[str, Any]] = []
    current: dict[str, str] | None = None

    def flush() -> None:
        if not current or "pos" not in current or "nickname" not in current:
            return
        coords = split_csv(current["pos"])
        if len(coords) < 3:
            return
        try:
            x = float(coords[0])
            y = float(coords[1])
            z = float(coords[2])
        except ValueError:
            return
        nickname = current["nickname"]
        resolved = gamedata.resolve(current.get("base") or nickname)
        objects.append({
            "nickname": nickname,
            "name": resolved["name"] if resolved["name"] != nickname else nickname.replace("_", " "),
            "kind": _object_kind(current),
            "x": x,
            "y": y,
            "z": z,
            "base": current.get("base", ""),
            "archetype": current.get("archetype", ""),
        })

    for raw_line in read_text(system_ini).splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            if line.lower() == "[object]":
                flush()
                current = {}
            else:
                flush()
                current = None
            continue
        if current is None or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if key.lower() in {"nickname", "pos", "base", "archetype"}:
            current[key.lower()] = value
    flush()
    return objects[:limit], str(system_ini.relative_to(DATA_DIR.parent))

def build_character(account_id: str, account_path: Path, file_path: Path, gamedata: GameData) -> dict[str, Any]:
    data = parse_fl(file_path)
    auth_codes = character_code_candidates(file_path)
    auth_code_files = character_auth_code_file_status(file_path)
    raw_fields = {key: values for key, values in data.items() if key not in {"equip", "cargo", "base_equip", "base_cargo", "house", "rep", "rep_group", "visit", "sys_visited", "base_visited", "holes_visited"}}
    played_seconds = intish(first(data, "total_time_played", "0"))
    return {
        "account_id": account_id,
        "file": file_path.name,
        "file_stem": file_path.stem,
        "path": str(file_path),
        "name": character_name(data, file_path),
        "auth_codes": auth_codes,
        "auth_code_files": auth_code_files,
        "auth_ready": bool(auth_codes),
        "description": decode_fl_text(first(data, "description")),
        "created": decode_fl_text(first(data, "created", "")) or file_time(file_path),
        "updated": file_time(file_path),
        "rank": intish(first(data, "rank")),
        "money": intish(first(data, "money")),
        "bank": read_bank_balance(account_path),
        "kills": intish(first(data, "num_kills")),
        "deaths": intish(first(data, "num_deaths", first(data, "deaths", "0"))),
        "missions_success": intish(first(data, "num_misn_successes")),
        "missions_failed": intish(first(data, "num_misn_failures")),
        "time_played_seconds": played_seconds,
        "time_played": format_seconds(played_seconds),
        "ship_token": first(data, "ship_archetype"),
        "cargo_rows": data.get("cargo", []),
        "ship": gamedata.resolve(first(data, "ship_archetype")),
        "system": gamedata.resolve(first(data, "system")),
        "base": gamedata.resolve(first(data, "base")),
        "last_base": gamedata.resolve(first(data, "last_base")),
        "equip": parse_loadout(data, "equip", gamedata),
        "cargo": parse_cargo(data, "cargo", gamedata),
        "base_equip": parse_loadout(data, "base_equip", gamedata),
        "base_cargo": parse_cargo(data, "base_cargo", gamedata),
        "houses": parse_houses(data, gamedata),
        "navigation": parse_visits(data, gamedata),
        "raw_fields": raw_fields,
    }


def load_accounts(accounts_dir: Path, gamedata: GameData) -> list[dict[str, Any]]:
    accounts = []
    if not accounts_dir.exists():
        return accounts
    for account_path in sorted(path for path in accounts_dir.iterdir() if path.is_dir()):
        character_files = sorted(account_path.glob("*.fl"))
        characters = [build_character(account_path.name, account_path, fl, gamedata) for fl in character_files]
        dated_files = character_files + ([account_path / "name"] if (account_path / "name").exists() else [])
        created_at = min((file_time(path) for path in dated_files), default=file_time(account_path))
        accounts.append({
            "id": account_path.name,
            "passwords": set(),  # legacy account/name auth is disabled; auth is per-character now.
            "created": created_at,
            "bank": read_bank_balance(account_path),
            "characters": characters,
            "character_count": len(characters),
            "total_money": sum(char["money"] for char in characters),
            "max_rank": max((char["rank"] for char in characters), default=0),
        })
    return accounts


class Repository:
    def __init__(self, accounts_dir: Path, ioncross_dir: Path) -> None:
        self.accounts_dir = accounts_dir
        self.ioncross_dir = ioncross_dir
        self.flhook = FlHookClient.from_env()
        self._flhook_online_cache: dict[str, tuple[float, bool]] = {}
        self._flhook_online_cache_ttl = 2.0
        self.reload()

    def reload(self) -> None:
        self.gamedata = GameData(self.ioncross_dir)
        self.crafting = CraftingSystem(CRAFTING_RECIPES_PATH, self.gamedata)
        self.accounts = load_accounts(self.accounts_dir, self.gamedata)
        self.by_id = {account["id"].lower(): account for account in self.accounts}
        self.characters: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for account in self.accounts:
            for character in account["characters"]:
                self.characters[str(character.get("name", "")).casefold()].append((account, character))


    def refresh_character(self, account_id: str, character_file: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Refresh only one character from disk instead of reloading every account."""
        account = self.by_id.get(str(account_id).lower())
        if not account:
            return None

        account_path = self.accounts_dir / account["id"]
        file_path = account_path / character_file
        if not file_path.exists():
            return None

        updated = build_character(account["id"], account_path, file_path, self.gamedata)
        account["bank"] = read_bank_balance(account_path)

        replaced = False
        for index, character in enumerate(account.get("characters", [])):
            if character.get("file") == character_file:
                character.clear()
                character.update(updated)
                character["bank"] = account["bank"]
                replaced = True
                break

        if not replaced:
            updated["bank"] = account["bank"]
            account.setdefault("characters", []).append(updated)

        account["character_count"] = len(account.get("characters", []))
        account["total_money"] = sum(int(char.get("money", 0)) for char in account.get("characters", []))
        account["max_rank"] = max((int(char.get("rank", 0)) for char in account.get("characters", [])), default=0)

        self.characters = defaultdict(list)
        for acc in self.accounts:
            for char in acc.get("characters", []):
                self.characters[str(char.get("name", "")).casefold()].append((acc, char))

        for character in account.get("characters", []):
            if character.get("file") == character_file:
                return account, character

        return None


    def character_inventory(self, character: dict[str, Any]) -> dict[str, int]:
        return read_cargo_inventory(Path(character["path"]), self.gamedata)

    def crafting_recipes_for(self, character: dict[str, Any]) -> list[dict[str, Any]]:
        return self.crafting.public_recipes(self.character_inventory(character))

    def craft_item(self, account_id: str, character_file: str, recipe_id: str) -> tuple[bool, str]:
        account_path = self.accounts_dir / account_id
        character_path = account_path / character_file
        if not character_path.exists():
            return False, "Персонаж не найден."
        ok, message = self.crafting.craft(character_path, recipe_id)
        if ok:
            self.reload()
        return ok, message


    def public_game_data(self, system_code: str = "Li01") -> dict[str, Any]:
        systems = sorted(_unique_game_items(list(self.gamedata.by_category.get("systems", {}).values())), key=lambda item: item.name.lower())
        ships = [item for item in sorted(_unique_game_items(list(self.gamedata.by_category.get("ships", {}).values())), key=lambda item: item.name.lower()) if "camera" not in item.nickname.lower() and "admin" not in item.name.lower()]
        bases = sorted(_unique_game_items(list(self.gamedata.by_category.get("bases", {}).values())), key=lambda item: item.name.lower())
        selected_system = next((item for item in systems if item.nickname.lower() == system_code.lower() or item.code.lower() == system_code.lower()), systems[0] if systems else None)
        selected_code = selected_system.code if selected_system else system_code
        objects, system_file = parse_system_objects(selected_code, self.gamedata)
        local_bases = [_short_game_item(item) for item in bases if item.code.lower().startswith(selected_code.lower() + "_")][:24]
        return {
            "system": _short_game_item(selected_system) if selected_system else {"code": selected_code, "nickname": selected_code, "name": selected_code},
            "systems": [_short_game_item(item) for item in systems[:160]],
            "ships": [_short_game_item(item) for item in ships[:36]],
            "bases": local_bases,
            "objects": objects,
            "source_files": [
                "IONCROSS/GAMEDATA_systems.txt",
                "IONCROSS/GAMEDATA_ships.txt",
                "IONCROSS/GAMEDATA_bases.txt",
                system_file,
            ],
        }

    def public_stats(self) -> dict[str, int]:
        return {"accounts": len(self.accounts), "characters": sum(account["character_count"] for account in self.accounts), "gamedata_items": len(self.gamedata.by_code)}

    def character_auth_status(self, character: dict[str, Any]) -> dict[str, Any]:
        try:
            character_path = Path(str(character.get("path") or ""))
            files = character_auth_code_file_status(character_path) if character_path.exists() else []
            codes = character_code_candidates(character_path) if character_path.exists() else set()
        except Exception:
            files = []
            codes = set()

        return {
            "files": files,
            "code_count": len(codes),
            "ready": bool(codes),
        }

    def debug_auth_login(self, login: str, password: str) -> str:
        pilot_name = str(login or "").strip()
        code = normalize_auth_code(password)
        if not pilot_name:
            return "AUTH login: WRONG (empty pilot name)"
        if not code:
            return f"AUTH login: WRONG (pilot={pilot_name}, empty code)"

        matches = self.characters.get(pilot_name.casefold(), [])
        if not matches:
            return f"AUTH login: WRONG (pilot={pilot_name}, pilot not found)"

        if len(matches) > 1:
            return f"AUTH login: WRONG (pilot={pilot_name}, duplicate pilot names: {len(matches)})"

        _account, character = matches[0]
        status = self.character_auth_status(character)
        file_bits = []
        for file_info in status.get("files", []):
            file_bits.append(
                f"{file_info.get('file')}:exists={file_info.get('exists')},code={file_info.get('has_code')}"
            )
        files_text = "; ".join(file_bits) if file_bits else "no auth files"
        return f"AUTH login: WRONG (pilot={pilot_name}, code_files=[{files_text}], decoded_codes={status.get('code_count', 0)})"

    def character_code_matches(self, character: dict[str, Any], code: str) -> bool:
        # v82: re-read *-givecash.ini on every login attempt.
        # Before v82 codes were cached at panel startup, so a newly generated
        # in-game code required restarting the panel.
        code = normalize_auth_code(code)
        if not code:
            return False

        live_codes: set[str] = set()
        try:
            character_path = Path(str(character.get("path") or ""))
            if character_path.exists():
                live_codes = character_code_candidates(character_path)
                character["auth_codes"] = live_codes
                character["auth_code_files"] = character_auth_code_file_status(character_path)
                character["auth_ready"] = bool(live_codes)
        except Exception:
            live_codes = set()

        candidates = set(character.get("auth_codes", set())) | live_codes
        code_bytes = code.encode("utf-8", errors="surrogatepass")

        for candidate in candidates:
            candidate_text = normalize_auth_code(candidate)
            if not candidate_text:
                continue

            candidate_bytes = candidate_text.encode("utf-8", errors="surrogatepass")
            if secrets.compare_digest(candidate_bytes, code_bytes):
                return True

        return False

    def authenticate(self, login: str, password: str, character_hint: str = "") -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Authenticate only by pilot name + per-character code.

        Allowed login:
          - exact pilot name from the .fl character name field.

        Not allowed anymore:
          - account id login;
          - .fl filename / stem login;
          - empty password login;
          - account/name legacy password.
        """
        pilot_name = str(login or "").strip()
        code = str(password or "").strip()

        if not pilot_name or not code:
            return None

        matches = self.characters.get(pilot_name.casefold(), [])
        if len(matches) != 1:
            return None

        account, character = matches[0]
        if self.character_code_matches(character, code):
            return account, character

        return None

    def find_unique_character(self, character_name_value: str) -> tuple[dict[str, Any], dict[str, Any]] | None | str:
        matches = self.characters.get(character_name_value.casefold(), [])
        if not matches:
            return None
        if len(matches) > 1:
            return "ambiguous"
        return matches[0]

    def find_character_by_file(self, account_id: str, character_file: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        account = self.by_id.get(account_id.lower())
        if not account:
            return None
        for character in account["characters"]:
            if character["file"] == character_file:
                return account, character
        return None

    def set_account_bank(self, account: dict[str, Any], balance: int) -> None:
        account["bank"] = max(0, balance)
        for character in account["characters"]:
            character["bank"] = account["bank"]

    def set_character_money(self, account: dict[str, Any], character: dict[str, Any], balance: int) -> None:
        old_balance = int(character.get("money", 0))
        character["money"] = max(0, balance)
        account["total_money"] = int(account.get("total_money", 0)) - old_balance + character["money"]

    def flhook_online(self, character_name_value: str) -> bool:
        name = str(character_name_value or "").strip()
        if not name or not self.flhook.enabled:
            return False

        key = name.casefold()
        now = time.monotonic()
        cached = self._flhook_online_cache.get(key)
        if cached and (now - cached[0]) <= self._flhook_online_cache_ttl:
            return cached[1]

        try:
            online = bool(self.flhook.is_logged_in(name))
        except FlHookUnavailable:
            online = False
        except FlHookError:
            online = False

        self._flhook_online_cache[key] = (now, online)
        return online

    def get_live_or_file_money(self, character: dict[str, Any], character_path: Path) -> tuple[int, bool]:
        if self.flhook_online(character["name"]):
            return self.flhook.get_cash(character["name"]), True
        return read_character_money(character_path), False

    def add_cash_safe(self, character: dict[str, Any], character_path: Path, amount_delta: int) -> tuple[int, bool]:
        if self.flhook_online(character["name"]):
            new_cash = self.flhook.add_cash(character["name"], amount_delta)
            return new_cash, True

        old_cash = read_character_money(character_path)
        new_cash = old_cash + amount_delta
        if new_cash < 0:
            raise FlHookError("Недостаточно средств персонажа.")
        write_character_money(character_path, new_cash)
        return new_cash, False

    def bank_operation(self, account_id: str, character_file: str, action: str, amount: int) -> tuple[bool, str]:
        if amount <= 0:
            return False, "Сумма должна быть положительным целым числом."

        found = self.find_character_by_file(account_id, character_file)
        if not found:
            return False, "Персонаж не найден."
        account, character = found

        account_path = self.accounts_dir / account_id
        character_path = account_path / character_file
        if not character_path.exists():
            return False, "Файл персонажа не найден."

        bank_money = read_bank_balance(account_path)

        try:
            character_money, character_online = self.get_live_or_file_money(character, character_path)
        except FlHookError as exc:
            return False, f"FLHook не смог прочитать деньги персонажа: {exc}"

        if action == "deposit":
            if character_money < amount:
                return False, "На игровом счёте персонажа недостаточно средств для зачисления в банк."

            try:
                new_character_money, used_flhook = self.add_cash_safe(character, character_path, -amount)
            except FlHookError as exc:
                return False, f"FLHook не смог списать деньги с персонажа: {exc}"

            new_bank_money = bank_money + amount
            write_bank_balance(account_path, new_bank_money)

            self.set_character_money(account, character, new_character_money)
            self.set_account_bank(account, new_bank_money)

            mode = "через FLHook" if used_flhook or character_online else "через файл"
            message = f"{money(amount)} кредитов переведено с персонажа в bank.ini."
            log_finance_event(
                account["id"],
                character["file"],
                character["name"],
                "bank_deposit",
                "internal",
                amount,
                character_delta=-amount,
                bank_delta=amount,
                mode=mode,
                note=message,
            )
            return True, message

        if action == "withdraw":
            if bank_money < amount:
                return False, "В bank.ini недостаточно средств для вывода персонажу."

            try:
                new_character_money, used_flhook = self.add_cash_safe(character, character_path, amount)
            except FlHookError as exc:
                return False, f"FLHook не смог начислить деньги персонажу: {exc}"

            new_bank_money = bank_money - amount
            write_bank_balance(account_path, new_bank_money)

            self.set_character_money(account, character, new_character_money)
            self.set_account_bank(account, new_bank_money)

            mode = "через FLHook" if used_flhook or character_online else "через файл"
            message = f"{money(amount)} кредитов выведено из bank.ini персонажу."
            log_finance_event(
                account["id"],
                character["file"],
                character["name"],
                "bank_withdraw",
                "internal",
                amount,
                character_delta=amount,
                bank_delta=-amount,
                mode=mode,
                note=message,
            )
            return True, message

        return False, "Неизвестная банковская операция."

    def transfer_to_character(self, sender_account_id: str, sender_file: str, target_name: str, amount: int) -> tuple[bool, str]:
        if amount <= 0:
            return False, "Сумма перевода должна быть положительным целым числом."

        target = self.find_unique_character(target_name.strip())
        if target is None:
            return False, "Пилот-получатель не найден."
        if target == "ambiguous":
            return False, "Найдено несколько персонажей с таким именем. Перевод отменён."

        target_account, target_character = target

        sender_found = self.find_character_by_file(sender_account_id, sender_file)
        if not sender_found:
            return False, "Персонаж-отправитель не найден."
        sender_account, sender_character = sender_found

        if target_account["id"] == sender_account_id and target_character["file"] == sender_file:
            return False, "Нельзя выполнить перевод самому себе."

        sender_account_path = self.accounts_dir / sender_account_id
        sender_path = sender_account_path / sender_file
        target_path = self.accounts_dir / target_account["id"] / target_character["file"]

        if not sender_path.exists() or not target_path.exists():
            return False, "Файл отправителя или получателя не найден."

        try:
            sender_money, sender_online = self.get_live_or_file_money(sender_character, sender_path)
            target_money, target_online = self.get_live_or_file_money(target_character, target_path)
        except FlHookError as exc:
            return False, f"FLHook не смог прочитать баланс: {exc}"

        sender_bank = read_bank_balance(sender_account_path)

        if sender_money + sender_bank < amount:
            return False, "Средств недостаточно: денег персонажа и bank.ini вместе не хватает для перевода."

        debit_from_character = min(sender_money, amount)
        debit_from_bank = amount - debit_from_character

        new_sender_bank = sender_bank - debit_from_bank

        try:
            if debit_from_character:
                new_sender_money, sender_used_flhook = self.add_cash_safe(sender_character, sender_path, -debit_from_character)
            else:
                new_sender_money = sender_money
                sender_used_flhook = False

            if debit_from_bank:
                write_bank_balance(sender_account_path, new_sender_bank)

            new_target_money, target_used_flhook = self.add_cash_safe(target_character, target_path, amount)

        except FlHookError as exc:
            # Попытка отката, если уже что-то успели списать.
            try:
                if debit_from_character:
                    self.add_cash_safe(sender_character, sender_path, debit_from_character)
                if debit_from_bank:
                    write_bank_balance(sender_account_path, sender_bank)
            except Exception:
                pass
            return False, f"Ошибка перевода через FLHook/файл: {exc}"

        self.set_character_money(sender_account, sender_character, new_sender_money)
        if debit_from_bank:
            self.set_account_bank(sender_account, new_sender_bank)
        self.set_character_money(target_account, target_character, new_target_money)

        details = f"списано {money(debit_from_character)} с персонажа"
        if debit_from_bank:
            details += f" и {money(debit_from_bank)} из bank.ini"

        modes = []
        if sender_used_flhook or sender_online:
            modes.append("отправитель через FLHook")
        if target_used_flhook or target_online:
            modes.append("получатель через FLHook")
        if not modes:
            modes.append("файловый режим")

        mode_text = ", ".join(modes)
        message = f"Перевод {money(amount)} кредитов пилоту {target_character['name']} выполнен: {details}."

        log_finance_event(
            sender_account["id"],
            sender_character["file"],
            sender_character["name"],
            "pilot_transfer",
            "outgoing",
            amount,
            character_delta=-debit_from_character,
            bank_delta=-debit_from_bank,
            counterparty_account_id=target_account["id"],
            counterparty_character_file=target_character["file"],
            counterparty_character_name=target_character["name"],
            mode=mode_text,
            note=message,
        )

        log_finance_event(
            target_account["id"],
            target_character["file"],
            target_character["name"],
            "pilot_transfer",
            "incoming",
            amount,
            character_delta=amount,
            bank_delta=0,
            counterparty_account_id=sender_account["id"],
            counterparty_character_file=sender_character["file"],
            counterparty_character_name=sender_character["name"],
            mode=mode_text,
            note=f"Получено {money(amount)} кредитов от пилота {sender_character['name']}.",
        )

        return True, message
