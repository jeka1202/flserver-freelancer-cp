from __future__ import annotations

from typing import Any

from .db import connect
from .fl_ini_parser import to_int


NANOBOT_NICKNAMES = {
    "ge_s_repair_01",
}

SHIELD_BATTERY_NICKNAMES = {
    "ge_s_battery_01",
}

AMMO_HINTS = (
    "_ammo",
    "ammo",
    "munition",
    "missile",
    "mine",
    "torpedo",
    "cm_",
    "countermeasure",
)


def row_value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError):
        return default




def load_name_map_entry(conn, *tokens: str):
    expanded: list[str] = []

    for token in tokens:
        token = str(token or "").strip()
        if not token:
            continue

        expanded.append(token)

        # Account .fl files often have ku_gunboat while IONCROSS has dsy_ku_gunboat.
        if "_" in token and not token.lower().startswith("dsy_") and not token.isdigit():
            expanded.append("dsy_" + token)

    seen: set[str] = set()
    for token in expanded:
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())

        row = conn.execute(
            """
            SELECT hash, nickname, display_name, category
            FROM name_map
            WHERE token = ? OR lower(token) = lower(?)
            LIMIT 1
            """,
            (token, token),
        ).fetchone()

        if row:
            return row

        alias = conn.execute(
            """
            SELECT hash, nickname, display_name, category
            FROM ioncross_aliases
            WHERE alias_token = ? OR lower(alias_token) = lower(?)
            LIMIT 1
            """,
            (token, token),
        ).fetchone()

        if alias:
            return alias

    return None


def is_technical_name(value: str) -> bool:
    value = str(value or "").strip()
    if not value:
        return True
    if value.lower() in {"unknown", "none", "null"}:
        return True
    return "_" in value or value.isdigit()


def human_ship_name(conn, ship, ship_token: str) -> str:
    if ship:
        display_name = str(row_value(ship, "display_name", "") or "").strip()
        nickname = str(row_value(ship, "nickname", "") or "").strip()
        hash_code = str(row_value(ship, "hash", "") or "").strip()

        mapped = load_name_map_entry(conn, ship_token, hash_code, nickname)
        if mapped and str(row_value(mapped, "display_name", "") or "").strip():
            return str(row_value(mapped, "display_name")).strip()

        if display_name and not is_technical_name(display_name):
            return display_name

        # Last non-technical fallback. In normal operation this should not be used.
        if nickname and not is_technical_name(nickname):
            return nickname

    mapped = load_name_map_entry(conn, ship_token)
    if mapped and str(row_value(mapped, "display_name", "") or "").strip():
        return str(row_value(mapped, "display_name")).strip()

    return "Неизвестный корабль"


def human_item_name(conn, item, item_hash: str) -> str:
    if item:
        display_name = str(row_value(item, "display_name", "") or "").strip()
        nickname = str(row_value(item, "nickname", "") or "").strip()
        good_nickname = str(row_value(item, "good_nickname", "") or "").strip()
        equipment_nickname = str(row_value(item, "equipment_nickname", "") or "").strip()
        hash_code = str(row_value(item, "hash", "") or "").strip()

        mapped = load_name_map_entry(conn, item_hash, hash_code, nickname, good_nickname, equipment_nickname)
        if mapped and str(row_value(mapped, "display_name", "") or "").strip():
            return str(row_value(mapped, "display_name")).strip()

        if display_name and not is_technical_name(display_name):
            return display_name

    mapped = load_name_map_entry(conn, item_hash)
    if mapped and str(row_value(mapped, "display_name", "") or "").strip():
        return str(row_value(mapped, "display_name")).strip()

    return "Неизвестный предмет"


def pct(value: float, limit: float) -> float:
    if not limit:
        return 0.0
    return round((value / limit) * 100, 1)


def bar_percent(value: float, limit: float) -> float:
    if not limit:
        return 0.0
    return max(0.0, min(100.0, (value / limit) * 100))



def item_token_candidates(token: str | int) -> list[str]:
    """Return possible DB tokens for a cargo hash/archid.

    Freelancer save files usually store cargo as cargo = <hash>,<count>.
    FLHook enumcargo returns archid as a number. Depending on signed/unsigned
    representation, the same 32-bit value may appear as:
      - 1234567890
      - -123456789
      - 4171510507

    The panel should resolve all of them to the same item where possible.
    """
    raw = str(token or "").strip()
    result: list[str] = []

    def add(value: str) -> None:
        value = str(value or "").strip()
        if value and value not in result:
            result.append(value)

    add(raw)

    try:
        value = int(raw, 0)
    except Exception:
        value = None

    if value is not None:
        unsigned = value & 0xFFFFFFFF
        signed = unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned

        add(str(value))
        add(str(unsigned))
        add(str(signed))
        add(hex(unsigned))
        add(hex(unsigned).upper().replace("X", "x"))

    return result


def load_ship(conn, ship_token: str):
    return conn.execute(
        """
        SELECT *
        FROM ships
        WHERE hash = ? OR nickname = ?
        LIMIT 1
        """,
        (ship_token, ship_token),
    ).fetchone()


def load_item(conn, token: str):
    for candidate in item_token_candidates(token):
        row = conn.execute(
            """
            SELECT *
            FROM items
            WHERE hash = ?
               OR nickname = ?
               OR good_nickname = ?
               OR equipment_nickname = ?
            LIMIT 1
            """,
            (candidate, candidate, candidate, candidate),
        ).fetchone()
        if row:
            return row

    return None


def item_kind(item: Any, item_hash: str) -> str:
    if not item:
        return "unknown"

    nickname = str(row_value(item, "nickname") or "").lower()
    good = str(row_value(item, "good_nickname") or "").lower()
    equipment = str(row_value(item, "equipment_nickname") or "").lower()
    section = str(row_value(item, "section") or "").lower()
    category = str(row_value(item, "category") or "").lower()

    names = " ".join([nickname, good, equipment, section, category, item_hash.lower()])

    if nickname in NANOBOT_NICKNAMES or equipment in NANOBOT_NICKNAMES or section == "repairkit":
        return "nanobot"

    if nickname in SHIELD_BATTERY_NICKNAMES or equipment in SHIELD_BATTERY_NICKNAMES or section == "shieldbattery":
        return "shield_battery"

    if any(hint in names for hint in AMMO_HINTS):
        return "ammo"

    volume = float(row_value(item, "volume", 0) or 0)
    if volume > 0:
        return "hold"

    return "equipment"


def parse_cargo_line(raw: str) -> dict[str, Any]:
    parts = [p.strip() for p in str(raw).split(",")]
    item_hash = parts[0] if parts else ""
    count = to_int(parts[1] if len(parts) > 1 else "1", 1)
    extra = parts[2:] if len(parts) > 2 else []
    return {
        "raw": raw,
        "hash": item_hash,
        "count": count,
        "extra": extra,
    }


def collect_cargo(conn, cargo_rows: list[str]) -> list[dict[str, Any]]:
    result = []

    for raw in cargo_rows:
        cargo = parse_cargo_line(raw)
        item_hash = cargo["hash"]
        count = cargo["count"]
        item = load_item(conn, item_hash)

        if item:
            nickname = row_value(item, "nickname", item_hash) or item_hash
            good_nickname = row_value(item, "good_nickname", "") or ""
            equipment_nickname = row_value(item, "equipment_nickname", "") or ""
            display_name = human_item_name(conn, item, item_hash)
            category = row_value(item, "category", "") or ""
            section = row_value(item, "section", "") or ""
            volume = float(row_value(item, "volume", 0) or 0)
            mass = float(row_value(item, "mass", 0) or 0)
            units_per_container = int(row_value(item, "units_per_container", 1) or 1)
        else:
            nickname = item_hash
            good_nickname = ""
            equipment_nickname = ""
            display_name = "Неизвестный предмет"
            category = "unknown"
            section = "unknown"
            volume = 0.0
            mass = 0.0
            units_per_container = 1

        total_volume = volume * count
        total_mass = mass * count
        kind = item_kind(item, item_hash)

        result.append({
            **cargo,
            "nickname": nickname,
            "good_nickname": good_nickname,
            "equipment_nickname": equipment_nickname,
            "display_name": display_name,
            "category": category,
            "section": section,
            "volume": volume,
            "mass": mass,
            "units_per_container": units_per_container,
            "total_volume": total_volume,
            "total_mass": total_mass,
            "kind": kind,
            "known": item is not None,
        })

    return result


def make_summary(ship, rows: list[dict[str, Any]], strict_limits: bool = False, conn=None, ship_token: str = "") -> dict[str, Any]:
    hold_size = int(row_value(ship, "hold_size", 0) or 0) if ship else 0
    ship_nanobot_limit = int(row_value(ship, "nanobot_limit", 0) or 0) if ship else 0
    ship_battery_limit = int(row_value(ship, "shield_battery_limit", 0) or 0) if ship else 0

    hold_used = sum(row["total_volume"] for row in rows if row["kind"] == "hold")
    nanobots = sum(row["count"] for row in rows if row["kind"] == "nanobot")
    shield_batteries = sum(row["count"] for row in rows if row["kind"] == "shield_battery")
    ammo_count = sum(row["count"] for row in rows if row["kind"] == "ammo")
    unknown_count = sum(row["count"] for row in rows if row["kind"] == "unknown")
    zero_equipment_count = sum(row["count"] for row in rows if row["kind"] == "equipment")

    effective_nanobot_limit = ship_nanobot_limit if strict_limits else max(ship_nanobot_limit, nanobots)
    effective_battery_limit = ship_battery_limit if strict_limits else max(ship_battery_limit, shield_batteries)

    groups = {
        "hold": [row for row in rows if row["kind"] == "hold"],
        "nanobot": [row for row in rows if row["kind"] == "nanobot"],
        "shield_battery": [row for row in rows if row["kind"] == "shield_battery"],
        "ammo": [row for row in rows if row["kind"] == "ammo"],
        "equipment": [row for row in rows if row["kind"] == "equipment"],
        "unknown": [row for row in rows if row["kind"] == "unknown"],
    }

    notes: list[str] = []
    if hold_size and hold_used > hold_size:
        notes.append(f"Трюм переполнен на {hold_used - hold_size:g} ед.")

    if not strict_limits:
        if ship_nanobot_limit and nanobots > ship_nanobot_limit:
            notes.append(f"Нанороботов больше штатного лимита корабля: {nanobots} > {ship_nanobot_limit}. Принято как текущий запас персонажа.")
        if ship_battery_limit and shield_batteries > ship_battery_limit:
            notes.append(f"Батарей щита больше штатного лимита корабля: {shield_batteries} > {ship_battery_limit}. Принято как текущий запас персонажа.")
    else:
        if effective_nanobot_limit and nanobots > effective_nanobot_limit:
            notes.append(f"Нанороботы переполнены на {nanobots - effective_nanobot_limit}.")
        if effective_battery_limit and shield_batteries > effective_battery_limit:
            notes.append(f"Батареи щита переполнены на {shield_batteries - effective_battery_limit}.")

    ship_dict = dict(ship) if ship else None
    ship_display_name = human_ship_name(conn, ship, ship_token)

    return {
        "available": True,
        "ship": ship_dict,
        "ship_display_name": ship_display_name,
        "hold_size": hold_size,
        "hold_used": hold_used,
        "hold_free": hold_size - hold_used if hold_size else None,
        "hold_pct": pct(hold_used, hold_size),
        "hold_bar": bar_percent(hold_used, hold_size),

        "ship_nanobot_limit": ship_nanobot_limit,
        "effective_nanobot_limit": effective_nanobot_limit,
        "nanobots": nanobots,
        "nanobot_free": effective_nanobot_limit - nanobots if effective_nanobot_limit else None,
        "nanobot_pct": pct(nanobots, effective_nanobot_limit),
        "nanobot_bar": bar_percent(nanobots, effective_nanobot_limit),

        "ship_shield_battery_limit": ship_battery_limit,
        "effective_shield_battery_limit": effective_battery_limit,
        "shield_batteries": shield_batteries,
        "shield_battery_free": effective_battery_limit - shield_batteries if effective_battery_limit else None,
        "shield_battery_pct": pct(shield_batteries, effective_battery_limit),
        "shield_battery_bar": bar_percent(shield_batteries, effective_battery_limit),

        "ammo_count": ammo_count,
        "zero_equipment_count": zero_equipment_count,
        "unknown_count": unknown_count,
        "total_mass": sum(row["total_mass"] for row in rows),
        "strict_limits": strict_limits,
        "groups": groups,
        "rows": rows,
        "notes": notes,
    }


def analyze_cargo(ship_token: str, cargo_rows: list[str], strict_limits: bool = False) -> dict[str, Any]:
    try:
        conn = connect()
        ship = load_ship(conn, ship_token)
        rows = collect_cargo(conn, cargo_rows)
        summary = make_summary(ship, rows, strict_limits=strict_limits, conn=conn, ship_token=ship_token)
        if not ship:
            summary["notes"].append("Корабль не найден в БД.")
        return summary
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "ship": None,
            "rows": [],
            "groups": {},
            "notes": ["БД груза недоступна. Выполни: py -m fl_panel.import_game_data --root ."],
        }
