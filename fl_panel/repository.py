from __future__ import annotations

import re
import secrets
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import VISIT_TYPES
from .finance import read_bank_balance, read_character_money, write_bank_balance, write_character_money
from .gamedata import GameData
from .utils import (
    account_password_candidates,
    decode_fl_text,
    file_time,
    first,
    format_seconds,
    intish,
    parse_fl,
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


def build_character(account_id: str, account_path: Path, file_path: Path, gamedata: GameData) -> dict[str, Any]:
    data = parse_fl(file_path)
    raw_fields = {key: values for key, values in data.items() if key not in {"equip", "cargo", "base_equip", "base_cargo", "house", "rep", "rep_group", "visit", "sys_visited", "base_visited", "holes_visited"}}
    played_seconds = intish(first(data, "total_time_played", "0"))
    return {
        "account_id": account_id,
        "file": file_path.name,
        "path": str(file_path),
        "name": character_name(data, file_path),
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
            "passwords": account_password_candidates(account_path),
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
        self.reload()

    def reload(self) -> None:
        self.gamedata = GameData(self.ioncross_dir)
        self.accounts = load_accounts(self.accounts_dir, self.gamedata)
        self.by_id = {account["id"].lower(): account for account in self.accounts}
        self.characters: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for account in self.accounts:
            for character in account["characters"]:
                self.characters[character["name"].casefold()].append((account, character))

    def public_stats(self) -> dict[str, int]:
        return {"accounts": len(self.accounts), "characters": sum(account["character_count"] for account in self.accounts), "gamedata_items": len(self.gamedata.by_code)}

    def password_matches(self, account: dict[str, Any], password: str) -> bool:
        password = password.strip()
        if not password:
            return True
        return any(secrets.compare_digest(candidate, password) for candidate in account.get("passwords", set()))

    def authenticate(self, login: str, password: str, character_hint: str = "") -> tuple[dict[str, Any], dict[str, Any]] | None:
        login = login.strip()
        character_hint = character_hint.strip().casefold()
        account = self.by_id.get(login.lower())
        if account and self.password_matches(account, password):
            if character_hint:
                for character in account["characters"]:
                    if character["name"].casefold() == character_hint:
                        return account, character
                return None
            return (account, account["characters"][0]) if account["characters"] else None
        for candidate_account, character in self.characters.get(login.casefold(), []):
            if self.password_matches(candidate_account, password):
                return candidate_account, character
        return None

    def find_unique_character(self, character_name_value: str) -> tuple[dict[str, Any], dict[str, Any]] | None | str:
        matches = self.characters.get(character_name_value.casefold(), [])
        if not matches:
            return None
        if len(matches) > 1:
            return "ambiguous"
        return matches[0]

    def set_account_bank(self, account: dict[str, Any], balance: int) -> None:
        account["bank"] = max(0, balance)
        for character in account["characters"]:
            character["bank"] = account["bank"]

    def set_character_money(self, account: dict[str, Any], character: dict[str, Any], balance: int) -> None:
        old_balance = int(character.get("money", 0))
        character["money"] = max(0, balance)
        account["total_money"] = int(account.get("total_money", 0)) - old_balance + character["money"]

    def bank_operation(self, account_id: str, character_file: str, action: str, amount: int) -> tuple[bool, str]:
        if amount <= 0:
            return False, "Сумма должна быть положительным целым числом."
        account = self.by_id.get(account_id.lower())
        if not account:
            return False, "Аккаунт не найден."
        character = next((item for item in account["characters"] if item["file"] == character_file), None)
        if not character:
            return False, "Персонаж не найден."
        account_path = self.accounts_dir / account_id
        character_path = account_path / character_file
        character_money = int(character.get("money", 0))
        bank_money = int(account.get("bank", 0))
        if action == "deposit":
            if character_money < amount:
                return False, "На игровом счёте персонажа недостаточно средств для зачисления в банк."
            write_character_money(character_path, character_money - amount)
            write_bank_balance(account_path, bank_money + amount)
            self.set_character_money(account, character, character_money - amount)
            self.set_account_bank(account, bank_money + amount)
            return True, f"{money(amount)} кредитов переведено с персонажа в bank.ini."
        if action == "withdraw":
            if bank_money < amount:
                return False, "В bank.ini недостаточно средств для вывода персонажу."
            write_bank_balance(account_path, bank_money - amount)
            write_character_money(character_path, character_money + amount)
            self.set_account_bank(account, bank_money - amount)
            self.set_character_money(account, character, character_money + amount)
            return True, f"{money(amount)} кредитов выведено из bank.ini персонажу."
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
        if target_account["id"] == sender_account_id and target_character["file"] == sender_file:
            return False, "Нельзя выполнить перевод самому себе."
        sender_account = self.by_id.get(sender_account_id.lower())
        if not sender_account:
            return False, "Аккаунт отправителя не найден."
        sender_character = next((item for item in sender_account["characters"] if item["file"] == sender_file), None)
        if not sender_character:
            return False, "Персонаж отправителя не найден."
        sender_account_path = self.accounts_dir / sender_account_id
        sender_path = sender_account_path / sender_file
        target_path = self.accounts_dir / target_account["id"] / target_character["file"]
        sender_money = int(sender_character.get("money", 0))
        sender_bank = int(sender_account.get("bank", 0))
        if sender_money + sender_bank < amount:
            return False, "Средств недостаточно: денег персонажа и bank.ini вместе не хватает для перевода."
        debit_from_character = min(sender_money, amount)
        debit_from_bank = amount - debit_from_character
        target_money = int(target_character.get("money", 0))
        write_character_money(sender_path, sender_money - debit_from_character)
        if debit_from_bank:
            write_bank_balance(sender_account_path, sender_bank - debit_from_bank)
        write_character_money(target_path, target_money + amount)
        self.set_character_money(sender_account, sender_character, sender_money - debit_from_character)
        if debit_from_bank:
            self.set_account_bank(sender_account, sender_bank - debit_from_bank)
        self.set_character_money(target_account, target_character, target_money + amount)
        details = f"списано {money(debit_from_character)} с персонажа"
        if debit_from_bank:
            details += f" и {money(debit_from_bank)} из bank.ini"
        return True, f"Перевод {money(amount)} кредитов пилоту {target_character['name']} выполнен: {details}."
