#!/usr/bin/env python3
"""Read-only Freelancer account control panel.

The panel intentionally uses only Python's standard library so it can be
started beside an FLServer account folder without installing dependencies.
"""
from __future__ import annotations

import argparse
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


def decode_fl_text(value: str) -> str:
    """Decode Freelancer UTF-16BE hex strings; return original value on failure."""
    compact = value.strip().replace(" ", "")
    if len(compact) >= 4 and len(compact) % 4 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact).decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return value.strip()
    return value.strip()


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
                parts = [part.strip() for part in rest.split(",", 1)]
                nickname = parts[0]
                name = parts[1] if len(parts) > 1 and parts[1] else nickname
                item = GameItem(code=code, nickname=nickname, name=name, category=category)
                items[code] = item
                self.by_code[code] = item
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


def account_display_name(path: Path) -> str:
    name_path = path / "name"
    if name_path.exists():
        raw = read_text(name_path).strip()
        if raw:
            return decode_fl_text(raw)
    return path.name


def character_name(data: dict[str, list[str]], file_path: Path) -> str:
    decoded = decode_fl_text(first(data, "name"))
    return decoded or file_path.stem


def build_character(account_id: str, file_path: Path, gamedata: GameData) -> dict[str, Any]:
    data = parse_fl(file_path)
    ship = gamedata.resolve(first(data, "ship_archetype"))
    system = gamedata.resolve(first(data, "system"))
    base = gamedata.resolve(first(data, "base"))
    last_base = gamedata.resolve(first(data, "last_base"))

    houses = []
    for raw in data.get("house", []):
        parts = split_csv(raw)
        reputation = parts[0] if parts else "0"
        faction_code = parts[1] if len(parts) > 1 else ""
        faction = gamedata.resolve(faction_code)
        houses.append({"code": faction_code, "name": faction["name"], "reputation": reputation})
    houses.sort(key=lambda item: float(item["reputation"]) if re.match(r"^-?\d+(\.\d+)?$", item["reputation"]) else 0, reverse=True)

    def parse_loadout(key: str) -> list[dict[str, str]]:
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

    def parse_cargo(key: str) -> list[dict[str, str]]:
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

    raw_fields = {key: values for key, values in data.items() if key not in {"equip", "cargo", "base_equip", "base_cargo", "house"}}
    return {
        "account_id": account_id,
        "file": file_path.name,
        "name": character_name(data, file_path),
        "description": decode_fl_text(first(data, "description")),
        "rank": intish(first(data, "rank")),
        "money": intish(first(data, "money")),
        "kills": intish(first(data, "num_kills")),
        "missions_success": intish(first(data, "num_misn_successes")),
        "missions_failed": intish(first(data, "num_misn_failures")),
        "ship": ship,
        "system": system,
        "base": base,
        "last_base": last_base,
        "equip": parse_loadout("equip"),
        "cargo": parse_cargo("cargo"),
        "base_equip": parse_loadout("base_equip"),
        "base_cargo": parse_cargo("base_cargo"),
        "houses": houses,
        "raw_fields": raw_fields,
        "updated": file_path.stat().st_mtime,
    }


def load_accounts(accounts_dir: Path, gamedata: GameData) -> list[dict[str, Any]]:
    accounts = []
    if not accounts_dir.exists():
        return accounts
    for account_path in sorted(path for path in accounts_dir.iterdir() if path.is_dir()):
        characters = [build_character(account_path.name, fl, gamedata) for fl in sorted(account_path.glob("*.fl"))]
        accounts.append({
            "id": account_path.name,
            "display_name": account_display_name(account_path),
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
        self.by_character = {char["name"].lower(): account for account in self.accounts for char in account["characters"]}

    def public_stats(self) -> dict[str, int]:
        return {
            "accounts": len(self.accounts),
            "characters": sum(account["character_count"] for account in self.accounts),
            "gamedata_items": len(self.gamedata.by_code),
        }


CSS = """
:root { color-scheme: dark; --bg:#08111f; --card:#101d31; --muted:#8ea3bd; --text:#eef5ff; --accent:#65d6ff; --good:#71f2a6; --bad:#ff8585; --line:#22344f; }
*{box-sizing:border-box} body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:radial-gradient(circle at top left,#132b4b,var(--bg) 42rem);color:var(--text)}
a{color:var(--accent)} .wrap{width:min(1280px,94vw);margin:0 auto;padding:32px 0}.hero{display:grid;grid-template-columns:1.3fr .7fr;gap:24px;align-items:stretch}.card{background:rgba(16,29,49,.92);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 18px 60px rgba(0,0,0,.28)}
h1,h2,h3{margin:.2rem 0 1rem} h1{font-size:clamp(2rem,5vw,4.5rem);line-height:.98} .muted{color:var(--muted)} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.stat{padding:16px;border-radius:14px;background:#0b1728;border:1px solid var(--line)}.stat b{display:block;font-size:1.7rem}.pill{display:inline-flex;gap:8px;align-items:center;padding:6px 10px;border-radius:999px;background:#0b1728;border:1px solid var(--line);color:var(--muted);margin:4px 4px 4px 0}
form{display:grid;gap:12px} input,button{border-radius:12px;border:1px solid var(--line);padding:12px 14px;font:inherit} input{background:#071222;color:var(--text)} button{background:linear-gradient(135deg,#2bd7ff,#766bff);color:#03101b;font-weight:800;cursor:pointer} table{width:100%;border-collapse:collapse;margin-top:10px} th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top} th{color:var(--muted);font-weight:700}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.search{min-width:280px;flex:1}.character{margin:24px 0}.money{color:var(--good);font-weight:800}.negative{color:var(--bad)} details{margin:14px 0} summary{cursor:pointer;color:var(--accent);font-weight:700}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.small{font-size:.92rem}.raw{max-height:360px;overflow:auto;background:#071222;border-radius:12px;padding:14px}.footer{padding:28px 0;color:var(--muted)} @media(max-width:820px){.hero,.two{grid-template-columns:1fr} h1{font-size:2.4rem}}
"""


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style><body><main class="wrap">{body}<p class="footer">Read-only Freelancer Account Panel · данные читаются из Accts/MultiPlayer и IONCROSS/GAMEDATA_*.txt</p></main></body></html>""".encode()


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_login(repo: Repository, message: str = "") -> bytes:
    stats = repo.public_stats()
    body = f"""
    <section class="hero">
      <div class="card"><span class="pill">FREELANCER · ACCOUNT CP</span><h1>Панель управления аккаунтом</h1>
      <p class="muted">Игрок входит по ID папки аккаунта и видит персонажей, корабли, инвентарь, деньги, репутацию по фракциям, базу, систему и сырые поля сохранения.</p>
      {f'<p class="pill negative">{esc(message)}</p>' if message else ''}
      <form method="post" action="/login"><label>ID аккаунта</label><input name="account" placeholder="например: 23-f73f713c" autocomplete="username" required><label>Имя персонажа (доп. проверка, если знаете)</label><input name="character" placeholder="например: Athlon0104"><button>Войти</button></form>
      <p class="muted small">Важно: в текущем архиве нет паролей. Для публикации в интернет подключите внешний SSO/пароли или ограничьте доступ reverse proxy.</p></div>
      <div class="card"><h2>Данные загружены</h2><div class="grid"><div class="stat"><b>{stats['accounts']}</b>аккаунтов</div><div class="stat"><b>{stats['characters']}</b>персонажей</div><div class="stat"><b>{stats['gamedata_items']}</b>IONCROSS записей</div></div>
      <details><summary>Администраторский поиск</summary><p class="muted small">Локальная read-only витрина всех аккаунтов: <a href="/admin">/admin</a>. Не открывайте её публично без авторизации.</p></details></div>
    </section>"""
    return page("Freelancer Account Panel", body)


def render_admin(repo: Repository) -> bytes:
    rows = "".join(
        f"<tr><td><a href='/account/{esc(account['id'])}'>{esc(account['id'])}</a></td><td>{esc(account['display_name'])}</td><td>{account['character_count']}</td><td>{money(account['total_money'])}</td><td>{account['max_rank']}</td><td>{', '.join(esc(c['name']) for c in account['characters'][:4])}</td></tr>"
        for account in repo.accounts
    )
    body = f"""<div class="card"><h1>Администраторский список аккаунтов</h1><p class="muted">Поиск работает на стороне браузера по ID, имени аккаунта и персонажам.</p><div class="toolbar"><input class="search" id="q" placeholder="Поиск..."><a class="pill" href="/">← вход игрока</a><a class="pill" href="/api/accounts">JSON API</a></div><table id="accounts"><thead><tr><th>ID</th><th>Имя</th><th>Перс.</th><th>Кредиты</th><th>Max rank</th><th>Персонажи</th></tr></thead><tbody>{rows}</tbody></table></div><script>q.oninput=()=>{{const v=q.value.toLowerCase();document.querySelectorAll('#accounts tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(v)?'':'none')}};</script>"""
    return page("Админ · Freelancer Account Panel", body)


def item_table(items: list[dict[str, str]], empty: str) -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(i['name'])}<br><span class='muted small'>{esc(i['nickname'])}</span></td><td>{esc(i.get('category',''))}</td><td>{esc(i.get('count') or i.get('hardpoint') or '—')}</td></tr>" for i in items)
    return f"<table><thead><tr><th>Название</th><th>Тип</th><th>Кол-во / слот</th></tr></thead><tbody>{rows}</tbody></table>"


def render_account(account: dict[str, Any]) -> bytes:
    chars_html = []
    for char in account["characters"]:
        top_factions = "".join(f"<span class='pill'>{esc(h['name'])}: {esc(h['reputation'])}</span>" for h in char["houses"][:8])
        negative_factions = "".join(f"<span class='pill negative'>{esc(h['name'])}: {esc(h['reputation'])}</span>" for h in char["houses"][-5:] if h["reputation"].startswith('-'))
        raw = esc(json.dumps(char["raw_fields"], ensure_ascii=False, indent=2))
        chars_html.append(f"""
        <section class="card character"><h2>{esc(char['name'])}</h2><p class="muted">Файл: {esc(char['file'])} · описание/дата: {esc(char['description'] or '—')}</p>
        <div class="grid"><div class="stat"><b>{esc(char['rank'])}</b>Ранг</div><div class="stat"><b class="money">{money(char['money'])}</b>Кредиты</div><div class="stat"><b>{esc(char['kills'])}</b>Убийства</div><div class="stat"><b>{esc(char['missions_success'])}/{esc(char['missions_failed'])}</b>Миссии успех/провал</div></div>
        <div class="grid"><div class="stat"><b>{esc(char['ship']['name'])}</b><span class="muted">{esc(char['ship']['nickname'])}</span></div><div class="stat"><b>{esc(char['system']['name'])}</b><span class="muted">Система: {esc(char['system']['nickname'])}</span></div><div class="stat"><b>{esc(char['base']['name'])}</b><span class="muted">Текущая база</span></div><div class="stat"><b>{esc(char['last_base']['name'])}</b><span class="muted">Последняя база</span></div></div>
        <div class="two"><div><h3>Установленное оборудование</h3>{item_table(char['equip'], 'Нет установленного оборудования.')}</div><div><h3>Инвентарь/груз</h3>{item_table(char['cargo'], 'Груз отсутствует.')}</div></div>
        <details><summary>Оборудование на базе/последнее сохранённое состояние</summary>{item_table(char['base_equip'], 'Нет данных base_equip.')}{item_table(char['base_cargo'], 'Нет данных base_cargo.')}</details>
        <details open><summary>Фракции и репутация</summary><p>{top_factions}{negative_factions}</p><table><thead><tr><th>Фракция</th><th>Код</th><th>Репутация</th></tr></thead><tbody>{''.join(f'<tr><td>{esc(h["name"])}</td><td>{esc(h["code"])}</td><td>{esc(h["reputation"])}</td></tr>' for h in char['houses'])}</tbody></table></details>
        <details><summary>Все распознанные сырые поля сохранения</summary><pre class="raw">{raw}</pre></details></section>""")
    body = f"<div class='card'><a class='pill' href='/'>← выйти</a><a class='pill' href='/admin'>админ-список</a><h1>{esc(account['display_name'])}</h1><p class='muted'>ID аккаунта: {esc(account['id'])} · персонажей: {account['character_count']} · всего кредитов: {money(account['total_money'])}</p></div>{''.join(chars_html)}"
    return page(f"Аккаунт {account['id']}", body)


class Handler(BaseHTTPRequestHandler):
    repo: Repository

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self.send_html(render_login(self.repo))
        elif path == "/admin":
            self.send_html(render_admin(self.repo))
        elif path == "/api/accounts":
            self.send_json(self.repo.accounts)
        elif path.startswith("/account/"):
            account_id = urllib.parse.unquote(path.split("/", 2)[2]).lower()
            account = self.repo.by_id.get(account_id)
            if not account:
                self.send_html(render_login(self.repo, "Аккаунт не найден"), HTTPStatus.NOT_FOUND)
            else:
                self.send_html(render_account(account))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/login":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("content-length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        account_id = (form.get("account", [""])[0]).strip().lower()
        character = (form.get("character", [""])[0]).strip().lower()
        account = self.repo.by_id.get(account_id)
        if not account:
            self.send_html(render_login(self.repo, "Аккаунт не найден"), HTTPStatus.UNAUTHORIZED)
            return
        if character and all(char["name"].lower() != character for char in account["characters"]):
            self.send_html(render_login(self.repo, "Имя персонажа не принадлежит этому аккаунту"), HTTPStatus.UNAUTHORIZED)
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/account/{urllib.parse.quote(account['id'])}")
        self.send_header("Set-Cookie", f"flpanel={secrets.token_urlsafe(16)}; HttpOnly; SameSite=Lax")
        self.end_headers()

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
