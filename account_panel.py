#!/usr/bin/env python3
"""Read-only Freelancer account control panel.

The panel intentionally uses only Python's standard library so it can be
started beside an FLServer account folder without installing dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import secrets
import sys
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ACCOUNTS_DIR = ROOT / "Accts" / "MultiPlayer"
IONCROSS_DIR = ROOT / "IONCROSS"
BANK_DIR = ROOT / "PanelData" / "banks"

DATA_FILES = {
    "ammo": "GAMEDATA_ammo.txt",
    "bases": "GAMEDATA_bases.txt",
    "cargo": "GAMEDATA_cargo.txt",
    "countermeasures": "GAMEDATA_countermeasures.txt",
    "engines": "GAMEDATA_engines.txt",
    "factions": "GAMEDATA_factions.txt",
    "guns": "GAMEDATA_guns.txt",
    "lights": "GAMEDATA_lights.txt",
    "mapinfo": "GAMEDATA_mapinfo.txt",
    "mines": "GAMEDATA_mines.txt",
    "misc_equipment": "GAMEDATA_miscequipment.txt",
    "power_generators": "GAMEDATA_powergenerators.txt",
    "projectiles": "GAMEDATA_projectiles.txt",
    "scanners": "GAMEDATA_scanners.txt",
    "shields": "GAMEDATA_shields.txt",
    "ships": "GAMEDATA_ships.txt",
    "systems": "GAMEDATA_systems.txt",
    "thrusters": "GAMEDATA_thrusters.txt",
    "tractorbeams": "GAMEDATA_tractorbeams.txt",
    "turrets": "GAMEDATA_turrets.txt",
}

CATEGORY_LABELS = {
    "ammo": "Боеприпасы",
    "bases": "Базы",
    "cargo": "Груз/товары",
    "countermeasures": "Контрмеры",
    "engines": "Двигатели",
    "factions": "Фракции",
    "guns": "Оружие",
    "lights": "Огни",
    "mapinfo": "Карта",
    "mines": "Мины",
    "misc_equipment": "Оборудование",
    "power_generators": "Генераторы",
    "projectiles": "Снаряды",
    "scanners": "Сканеры",
    "shields": "Щиты",
    "ships": "Корабли",
    "systems": "Системы",
    "thrusters": "Форсаж",
    "tractorbeams": "Тракторы",
    "turrets": "Турели",
    "unknown": "Неизвестно",
}

VISIT_TYPES = {
    "1": "система",
    "17": "прыжковая дыра/ворота",
    "33": "объект карты",
    "41": "база/объект",
    "45": "торговая линия/зона",
    "65": "информационная отметка",
}

# Freelancer nickname hash. Algorithm documented in the public flhash/CreateID
# tooling ecosystem and mirrored by dwmunster's hasher.go gist.
LOGICAL_BITS = 30
PHYSICAL_BITS = 32
FL_HASH_POLYNOMIAL = 0xA001 << (LOGICAL_BITS - 16)


def make_crc_table(polynomial: int) -> list[int]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            if value & 1:
                value = (value >> 1) ^ polynomial
            else:
                value >>= 1
            value &= 0xFFFFFFFF
        table.append(value)
    return table


CRC_TABLE = make_crc_table(FL_HASH_POLYNOMIAL)


def raw_fl_hash(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value >> 8) ^ CRC_TABLE[(value ^ byte) & 0xFF]
    return ((value >> 24) | ((value >> 8) & 0x0000FF00) | ((value << 8) & 0x00FF0000) | (value << 24)) & 0xFFFFFFFF


def nickname_hash(nickname: str) -> str:
    value = (raw_fl_hash(nickname.lower().encode()) >> (PHYSICAL_BITS - LOGICAL_BITS)) | 0x80000000
    return str(value)


def decode_fl_text(value: str) -> str:
    """Decode Freelancer UTF-16BE hex strings; return original value on failure."""
    compact = value.strip().replace(" ", "")
    if len(compact) >= 4 and len(compact) % 4 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact).decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return value.strip()
    return value.strip()


def decode_account_password(raw: bytes) -> str:
    """Decode the account-wide password stored in each account folder's name file."""
    if len(raw) >= 2 and set(raw[1::2]) == {0x2E}:
        try:
            return "".join(chr(byte ^ 0x6E) for byte in raw[::2]).strip("\x00\r\n")
        except ValueError:
            pass
    text = raw.decode("utf-8", errors="ignore").strip()
    return decode_fl_text(text) if text else ""


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


@dataclass(frozen=True)
class GameItem:
    code: str
    nickname: str
    name: str
    category: str


class GameData:
    def __init__(self, directory: Path) -> None:
        self.by_category: dict[str, dict[str, GameItem]] = {}
        self.by_code: dict[str, GameItem] = {}
        self.by_nickname: dict[str, GameItem] = {}
        self.load(directory)

    def load(self, directory: Path) -> None:
        for category, filename in DATA_FILES.items():
            items: dict[str, GameItem] = {}
            path = directory / filename
            if not path.exists():
                self.by_category[category] = items
                continue
            for raw_line in read_text(path).splitlines():
                line = raw_line.strip()
                if not line or line.startswith(("#", ";")) or "=" not in line:
                    continue
                code, rest = [part.strip() for part in line.split("=", 1)]
                if category == "mapinfo" and code == "visit":
                    parts = split_csv(rest)
                    code = parts[0] if parts else rest.strip()
                    nickname = code
                    visit_type = parts[1] if len(parts) > 1 else ""
                    name = f"Отметка карты {code} ({VISIT_TYPES.get(visit_type, visit_type or 'тип неизвестен')})"
                else:
                    parts = [part.strip() for part in rest.split(",", 1)]
                    nickname = parts[0]
                    name = parts[1] if len(parts) > 1 and parts[1] else nickname
                item = GameItem(code=code, nickname=nickname, name=name, category=category)
                for lookup_code in {code, nickname_hash(code), nickname, nickname_hash(nickname)}:
                    items[lookup_code] = item
                    self.by_code[lookup_code] = item
                self.by_nickname[nickname.lower()] = item
            self.by_category[category] = items

    def resolve(self, token: str | None) -> dict[str, str]:
        token = (token or "").strip()
        item = self.by_code.get(token) or self.by_nickname.get(token.lower())
        if item:
            return {
                "code": item.code,
                "nickname": item.nickname,
                "name": item.name,
                "category": item.category,
                "category_label": CATEGORY_LABELS.get(item.category, item.category),
            }
        return {
            "code": token,
            "nickname": token,
            "name": token or "—",
            "category": "unknown",
            "category_label": CATEGORY_LABELS["unknown"],
        }


def parse_fl(path: Path) -> dict[str, list[str]]:
    data: dict[str, list[str]] = defaultdict(list)
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#", "[")) or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        data[key].append(value)
    return dict(data)


def first(data: dict[str, list[str]], key: str, default: str = "") -> str:
    values = data.get(key) or []
    return values[0] if values else default


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")]


def intish(value: str, default: int = 0) -> int:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return default


def format_seconds(value: int | float) -> str:
    seconds = int(value)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} дн.")
    if hours or days:
        parts.append(f"{hours} ч.")
    if minutes or hours or days:
        parts.append(f"{minutes} мин.")
    parts.append(f"{seconds} сек.")
    return " ".join(parts)


def file_time(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def account_password(path: Path) -> str:
    name_path = path / "name"
    return decode_account_password(name_path.read_bytes()) if name_path.exists() else ""


def character_name(data: dict[str, list[str]], file_path: Path) -> str:
    decoded = decode_fl_text(first(data, "name"))
    return decoded or file_path.stem


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
        cargo.append({
            "name": item["name"],
            "nickname": item["nickname"],
            "category": item["category_label"],
            "count": parts[1] if len(parts) > 1 else "1",
            "raw": raw,
        })
    return cargo


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


def parse_rep_group(data: dict[str, list[str]], gamedata: GameData) -> list[dict[str, str]]:
    groups = data.get("rep_group", [])
    reps = data.get("rep", [])
    result = []
    for index, code in enumerate(groups):
        faction = gamedata.resolve(code)
        result.append({"code": code, "name": faction["name"], "reputation": reps[index] if index < len(reps) else ""})
    return result


def parse_visits(data: dict[str, list[str]], gamedata: GameData) -> dict[str, Any]:
    systems = [gamedata.resolve(value) for value in data.get("sys_visited", [])]
    bases = [gamedata.resolve(value) for value in data.get("base_visited", [])]
    holes = [gamedata.resolve(value) for value in data.get("holes_visited", [])]
    raw_visits = []
    for raw in data.get("visit", [])[:250]:
        parts = split_csv(raw)
        target = gamedata.resolve(parts[0] if parts else "")
        visit_type = parts[1] if len(parts) > 1 else ""
        raw_visits.append({
            "code": parts[0] if parts else "",
            "name": target["name"],
            "nickname": target["nickname"],
            "type": VISIT_TYPES.get(visit_type, visit_type or "—"),
        })
    return {
        "systems": systems,
        "bases": bases,
        "holes": holes,
        "raw": raw_visits,
        "raw_total": len(data.get("visit", [])),
    }


def build_character(account_id: str, account_path: Path, file_path: Path, gamedata: GameData) -> dict[str, Any]:
    data = parse_fl(file_path)
    raw_fields = {key: values for key, values in data.items() if key not in {"equip", "cargo", "base_equip", "base_cargo", "house", "rep", "rep_group", "visit", "sys_visited", "base_visited", "holes_visited"}}
    deaths = intish(first(data, "num_deaths", first(data, "deaths", "0")))
    created = decode_fl_text(first(data, "created", "")) or file_time(file_path)
    played_seconds = intish(first(data, "total_time_played", "0"))
    return {
        "account_id": account_id,
        "account_password": account_password(account_path),
        "file": file_path.name,
        "path": str(file_path),
        "name": character_name(data, file_path),
        "description": decode_fl_text(first(data, "description")),
        "created": created,
        "updated": file_time(file_path),
        "rank": intish(first(data, "rank")),
        "money": intish(first(data, "money")),
        "bank": read_bank_balance(account_id, file_path.name),
        "kills": intish(first(data, "num_kills")),
        "deaths": deaths,
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


def read_bank_balance(account_id: str, character_file: str) -> int:
    bank_path = BANK_DIR / account_id / f"{character_file}.json"
    if not bank_path.exists():
        return 0
    try:
        payload = json.loads(read_text(bank_path))
    except json.JSONDecodeError:
        return 0
    return intish(str(payload.get("balance", 0)))


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
            "password": account_password(account_path),
            "created": created_at,
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
        return {
            "accounts": len(self.accounts),
            "characters": sum(account["character_count"] for account in self.accounts),
            "gamedata_items": len(self.gamedata.by_code),
        }

    def authenticate(self, character_name_value: str, password: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        for account, character in self.characters.get(character_name_value.casefold(), []):
            if secrets.compare_digest(account["password"], password.strip()):
                return account, character
        return None


CSS = """
:root { color-scheme: dark; --bg:#07101e; --card:#101d31; --panel:#0b1728; --muted:#8ea3bd; --text:#eef5ff; --accent:#65d6ff; --accent2:#766bff; --good:#71f2a6; --bad:#ff8585; --warn:#ffd166; --line:#22344f; }
*{box-sizing:border-box} body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:radial-gradient(circle at top left,#13355b,var(--bg) 42rem);color:var(--text)}
a{color:var(--accent)} .wrap{width:min(1280px,94vw);margin:0 auto;padding:32px 0}.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:24px;align-items:stretch}.card{background:rgba(16,29,49,.94);border:1px solid var(--line);border-radius:22px;padding:24px;box-shadow:0 18px 60px rgba(0,0,0,.28)}
h1,h2,h3{margin:.2rem 0 1rem} h1{font-size:clamp(2.1rem,5vw,4.6rem);line-height:.98}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}.stat{padding:16px;border-radius:16px;background:var(--panel);border:1px solid var(--line)}.stat b{display:block;font-size:1.55rem}.pill{display:inline-flex;gap:8px;align-items:center;padding:6px 10px;border-radius:999px;background:var(--panel);border:1px solid var(--line);color:var(--muted);margin:4px 4px 4px 0}.ship{font-size:1.25rem;color:var(--accent)}
form{display:grid;gap:12px} input,button,select{border-radius:12px;border:1px solid var(--line);padding:12px 14px;font:inherit} input,select{background:#071222;color:var(--text)} button{background:linear-gradient(135deg,#2bd7ff,var(--accent2));color:#03101b;font-weight:800;cursor:pointer}.disabled button,button:disabled{filter:grayscale(1);opacity:.55;cursor:not-allowed} table{width:100%;border-collapse:collapse;margin-top:10px} th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top} th{color:var(--muted);font-weight:700}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.search{min-width:280px;flex:1}.money{color:var(--good);font-weight:800}.negative{color:var(--bad)}.warning{color:var(--warn)} details{margin:14px 0} summary{cursor:pointer;color:var(--accent);font-weight:700}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.small{font-size:.92rem}.raw{max-height:360px;overflow:auto;background:#071222;border-radius:12px;padding:14px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}.tab{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:999px;padding:10px 14px}.tab.active{background:linear-gradient(135deg,#153c63,#252d70);color:var(--text);border-color:var(--accent)}.tab-panel{display:none}.tab-panel.active{display:block}.footer{padding:28px 0;color:var(--muted)} @media(max-width:820px){.hero,.two{grid-template-columns:1fr} h1{font-size:2.5rem}}
"""


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style><body><main class="wrap">{body}<p class="footer">Read-only Freelancer Account Panel · клиентская часть показывает только персонажа после входа · админская логика отдельно в /admin</p></main><script>{TABS_JS}</script></body></html>""".encode()


TABS_JS = """
document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-tab]');
  if (!tab) return;
  const id = tab.dataset.tab;
  document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item === tab));
  document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.toggle('active', panel.id === id));
});
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_login(repo: Repository, message: str = "") -> bytes:
    stats = repo.public_stats()
    body = f"""
    <section class="hero">
      <div class="card"><span class="pill">FREELANCER · ACCOUNT CP</span><h1>Личный кабинет пилота</h1>
      <p class="muted">Введите имя персонажа и пароль аккаунта из файла <code>name</code>. После проверки откроется только личный кабинет указанного персонажа.</p>
      {f'<p class="pill negative">{esc(message)}</p>' if message else ''}
      <form method="post" action="/login"><label>Имя персонажа</label><input name="character" placeholder="например: Athlon0104" autocomplete="username" required autofocus><label>Пароль аккаунта</label><input name="password" type="password" placeholder="пароль из файла name" autocomplete="current-password" required><button>Войти в кабинет</button></form>
      <p class="muted small">Администрирование вынесено отдельно: <a href="/admin">/admin</a>. Клиентская часть не показывает список чужих аккаунтов.</p></div>
      <div class="card"><h2>Что будет внутри</h2><div class="grid"><div class="stat"><b>{stats['characters']}</b>персонажей в архиве</div><div class="stat"><b>{stats['gamedata_items']}</b>записей IONCROSS</div></div>
      <p><span class="pill">Инвентарь</span><span class="pill">Снаряжение</span><span class="pill">Статистика</span><span class="pill">Финансы и банк</span><span class="pill">Репутация</span><span class="pill">Навигация</span></p>
      <p class="muted small">Панель read-only для сохранений. Банковские операции показаны как подготовленная клиентская зона и пока не меняют файлы персонажа.</p></div>
    </section>"""
    return page("Вход · Freelancer Account Panel", body)


def item_table(items: list[dict[str, str]], empty: str, third_label: str = "Кол-во / слот") -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(i['name'])}<br><span class='muted small'>{esc(i['nickname'])}</span></td><td>{esc(i.get('category',''))}</td><td>{esc(i.get('count') or i.get('hardpoint') or '—')}</td></tr>" for i in items)
    return f"<table><thead><tr><th>Название</th><th>Тип</th><th>{esc(third_label)}</th></tr></thead><tbody>{rows}</tbody></table>"


def render_cabinet(account: dict[str, Any], char: dict[str, Any]) -> bytes:
    top_factions = "".join(f"<span class='pill'>{esc(h['name'])}: {esc(h['reputation'])}</span>" for h in char["houses"][:8])
    bank_total = char["bank"]
    nav = char["navigation"]
    raw = esc(json.dumps(char["raw_fields"], ensure_ascii=False, indent=2))
    body = f"""
    <div class="card"><a class="pill" href="/logout">← выйти</a><span class="pill">Аккаунт: {esc(account['id'])}</span><h1>{esc(char['name'])}</h1>
    <p class="ship">{esc(char['ship']['name'])}</p><p class="muted">{esc(char['system']['name'])} · {esc(char['base']['name'])} · ранг {esc(char['rank'])}</p></div>
    <div class="tabs"><button class="tab active" data-tab="inventory">Инвентарь</button><button class="tab" data-tab="equipment">Снаряжение</button><button class="tab" data-tab="stats">Статистика</button><button class="tab" data-tab="finance">Финансы</button><button class="tab" data-tab="reputation">Репутация</button><button class="tab" data-tab="navigation">Навигация</button></div>

    <section id="inventory" class="card tab-panel active"><h2>Инвентарь</h2><p class="muted">Груз и предметы в трюме персонажа.</p>{item_table(char['cargo'], 'Груз отсутствует.', 'Кол-во')}</section>

    <section id="equipment" class="card tab-panel"><h2>Снаряжение</h2><div class="grid"><div class="stat"><b>{esc(char['ship']['name'])}</b>Корабль<br><span class="muted">{esc(char['ship']['nickname'])}</span></div><div class="stat"><b>{esc(char['base']['name'])}</b>Текущая база</div><div class="stat"><b>{esc(char['last_base']['name'])}</b>Последняя база</div></div><h3>Установлено на корабле</h3>{item_table(char['equip'], 'Нет установленного оборудования.', 'Слот')}<details><summary>Оборудование на базе/последнее сохранённое состояние</summary>{item_table(char['base_equip'], 'Нет данных base_equip.', 'Слот')}{item_table(char['base_cargo'], 'Нет данных base_cargo.', 'Кол-во')}</details></section>

    <section id="stats" class="card tab-panel"><h2>Статистика</h2><div class="grid"><div class="stat"><b>{esc(char['time_played'])}</b>Время в игре</div><div class="stat"><b>{esc(account['created'])}</b>Создан аккаунт</div><div class="stat"><b>{esc(char['created'])}</b>Создан персонаж / первая дата файла</div><div class="stat"><b>{esc(char['updated'])}</b>Последнее изменение</div><div class="stat"><b>{esc(char['kills'])}</b>Убийства</div><div class="stat"><b>{esc(char['deaths'])}</b>Смерти</div><div class="stat"><b>{esc(char['missions_success'])}/{esc(char['missions_failed'])}</b>Миссии успех/провал</div></div><details><summary>Все прочитанные сырые поля персонажа</summary><pre class="raw">{raw}</pre></details></section>

    <section id="finance" class="card tab-panel"><h2>Финансы</h2><div class="grid"><div class="stat"><b class="money">{money(char['money'])}</b>Деньги персонажа</div><div class="stat"><b class="money">{money(bank_total)}</b>Личный банк кабинета</div></div><div class="two"><div class="stat"><h3>Перевод на другого персонажа</h3><form class="disabled"><input placeholder="Имя получателя" disabled><input placeholder="Сумма" disabled><button disabled>Скоро</button></form><p class="muted small">Заготовка под внутренние переводы между персонажами.</p></div><div class="stat"><h3>Банк персонажа</h3><form class="disabled"><select disabled><option>Зачислить в банк</option><option>Вывести из банка</option></select><input placeholder="Сумма" disabled><button disabled>Скоро</button></form><p class="muted small">Будущая логика позволит перекладывать средства между игровым балансом и личным банком без ручного редактирования.</p></div></div></section>

    <section id="reputation" class="card tab-panel"><h2>Репутация</h2><p>{top_factions}</p><table><thead><tr><th>Фракция</th><th>Код</th><th>Отношение</th></tr></thead><tbody>{''.join(f'<tr><td>{esc(h["name"])}</td><td>{esc(h["code"])}</td><td class="{ "negative" if str(h["reputation"]).startswith("-") else "" }">{esc(h["reputation"])}</td></tr>' for h in char['houses'])}</tbody></table></section>

    <section id="navigation" class="card tab-panel"><h2>Навигация</h2><div class="grid"><div class="stat"><b>{esc(char['system']['name'])}</b>Текущая система</div><div class="stat"><b>{len(nav['systems'])}</b>Посещённых систем</div><div class="stat"><b>{len(nav['bases'])}</b>Посещённых баз</div><div class="stat"><b>{nav['raw_total']}</b>Отметок карты</div></div><div class="two"><div><h3>Посещённые системы</h3>{nav_table(nav['systems'], 'Нет записей sys_visited.')}</div><div><h3>Посещённые базы</h3>{nav_table(nav['bases'], 'Нет записей base_visited.')}</div></div><details><summary>Прыжковые дыры и сырые отметки карты</summary>{nav_table(nav['holes'], 'Нет записей holes_visited.')}<h3>Первые 250 visit-записей</h3>{raw_visit_table(nav['raw'])}</details></section>
    """
    return page(f"{char['name']} · Кабинет", body)


def nav_table(items: list[dict[str, str]], empty: str) -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(item['name'])}</td><td>{esc(item['nickname'])}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Название</th><th>Код</th></tr></thead><tbody>{rows}</tbody></table>"


def raw_visit_table(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>Нет visit-записей.</p>"
    rows = "".join(f"<tr><td>{esc(item['name'])}<br><span class='muted small'>{esc(item['nickname'])}</span></td><td>{esc(item['type'])}</td><td>{esc(item['code'])}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Объект</th><th>Тип</th><th>Код</th></tr></thead><tbody>{rows}</tbody></table>"


def render_admin(repo: Repository) -> bytes:
    rows = "".join(
        f"<tr><td><a href='/admin/account/{esc(account['id'])}'>{esc(account['id'])}</a></td><td>{account['character_count']}</td><td>{money(account['total_money'])}</td><td>{account['max_rank']}</td><td>{', '.join(esc(c['name']) for c in account['characters'][:5])}</td></tr>"
        for account in repo.accounts
    )
    body = f"""<div class="card"><h1>Админская зона</h1><p class="muted">Отдельная операторская логика: список аккаунтов, поиск и JSON. Клиентский вход находится на <a href="/">главной</a>.</p><div class="toolbar"><input class="search" id="q" placeholder="Поиск по аккаунту или персонажу..."><a class="pill" href="/api/accounts">JSON API</a></div><table id="accounts"><thead><tr><th>ID</th><th>Перс.</th><th>Кредиты</th><th>Max rank</th><th>Персонажи</th></tr></thead><tbody>{rows}</tbody></table></div><script>q.oninput=()=>{{const v=q.value.toLowerCase();document.querySelectorAll('#accounts tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(v)?'':'none')}};</script>"""
    return page("Админ · Freelancer Account Panel", body)


def render_admin_account(account: dict[str, Any]) -> bytes:
    rows = "".join(f"<tr><td>{esc(char['name'])}</td><td>{esc(char['file'])}</td><td>{esc(char['ship']['name'])}</td><td>{money(char['money'])}</td><td>{esc(char['system']['name'])}</td></tr>" for char in account["characters"])
    body = f"<div class='card'><a class='pill' href='/admin'>← админка</a><h1>{esc(account['id'])}</h1><table><thead><tr><th>Персонаж</th><th>Файл</th><th>Корабль</th><th>Кредиты</th><th>Система</th></tr></thead><tbody>{rows}</tbody></table></div>"
    return page(f"Админ · {account['id']}", body)


class Handler(BaseHTTPRequestHandler):
    repo: Repository
    sessions: dict[str, tuple[str, str]] = {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self.send_html(render_login(self.repo))
        elif path == "/cabinet":
            session = self.current_session()
            if not session:
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.send_html(render_cabinet(session[0], session[1]))
        elif path == "/logout":
            self.logout()
        elif path == "/admin":
            self.send_html(render_admin(self.repo))
        elif path.startswith("/admin/account/"):
            account_id = urllib.parse.unquote(path.split("/", 3)[3]).lower()
            account = self.repo.by_id.get(account_id)
            if account:
                self.send_html(render_admin_account(account))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        elif path == "/api/accounts":
            self.send_json(self.admin_json())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/login":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("content-length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        character_name_value = (form.get("character", [""])[0]).strip()
        password = form.get("password", [""])[0]
        match = self.repo.authenticate(character_name_value, password)
        if not match:
            self.send_html(render_login(self.repo, "Имя персонажа или пароль не совпали"), HTTPStatus.UNAUTHORIZED)
            return
        account, character = match
        token = secrets.token_urlsafe(32)
        self.sessions[token] = (account["id"], character["file"])
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/cabinet")
        self.send_header("Set-Cookie", f"flpanel={token}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()

    def current_session(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        cookie = self.headers.get("Cookie", "")
        token = ""
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "flpanel":
                token = value
        stored = self.sessions.get(token)
        if not stored:
            return None
        account = self.repo.by_id.get(stored[0].lower())
        if not account:
            return None
        for character in account["characters"]:
            if character["file"] == stored[1]:
                return account, character
        return None

    def logout(self) -> None:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "flpanel":
                self.sessions.pop(value, None)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", "flpanel=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()

    def admin_json(self) -> list[dict[str, Any]]:
        safe_accounts = []
        for account in self.repo.accounts:
            safe_characters = []
            for character in account["characters"]:
                safe_characters.append({key: value for key, value in character.items() if key != "account_password"})
            safe_accounts.append({
                "id": account["id"],
                "created": account["created"],
                "characters": safe_characters,
                "character_count": account["character_count"],
                "total_money": account["total_money"],
                "max_rank": account["max_rank"],
            })
        return safe_accounts

    def send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: Any) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Freelancer account web panel")
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


if __name__ == "__main__":
    main()
