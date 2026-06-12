from __future__ import annotations

import sqlite3
import threading
import re
from pathlib import Path
from datetime import datetime
from typing import Any

from .db import connect
from .fl_ini_parser import to_int
from .utils import read_text, nickname_hash


LEGACY_CHARACTER_FILE = "__legacy_shared__"

_WAREHOUSE_SCHEMA_READY = False
_WAREHOUSE_SCHEMA_LOCK = threading.Lock()



CARGO_BLOCKED_HINTS = (
    "weapon",
    "gun",
    "turret",
    "shield",
    "engine",
    "thruster",
    "scanner",
    "tractor",
    "countermeasure",
    "munition",
    "ammo",
    "missile",
    "mine",
    "torpedo",
    "launcher",
    "repairkit",
    "shieldbattery",
    "equipment",
)


def is_cargo_good_for_hold(*, category: str = "", section: str = "", volume: float = 0.0) -> bool:
    """Allow only real cargo/commodity items for FLHook addcargo from panel.

    We intentionally do NOT try to place weapons, turrets, shields, scanners or
    other equipment on the ship through the cabinet. For now the panel only moves
    items that behave like regular cargo = lines and occupy normal cargo hold
    volume.
    """

    category_text = str(category or "").strip().lower()
    section_text = str(section or "").strip().lower()
    combined = f"{category_text} {section_text}"

    try:
        item_volume = float(volume or 0)
    except Exception:
        item_volume = 0.0

    if item_volume <= 0:
        return False

    # Commodity / cargo sections are explicitly allowed.
    if "commodity" in combined or section_text in {"cargo", "good", "goods"}:
        return True

    # Positive volume is the old cockpit/hold rule used by the cabinet for
    # "Товары / commodity в трюме". Reject obvious equipment-like records.
    if any(hint in combined for hint in CARGO_BLOCKED_HINTS):
        return False

    return True


def cargo_hold_reject_reason() -> str:
    return "В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0. Эквипмент и снаряжение пока не трогаем."



def cargo_item_tokens(item: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("hash", "nickname", "good_nickname", "equipment_nickname"):
        value = str(item.get(key) or "").strip()
        if not value:
            continue
        tokens.add(value.lower())
        if not value.isdigit():
            try:
                tokens.add(nickname_hash(value).lower())
            except Exception:
                pass
    return tokens


def cargo_file_token(item: dict[str, Any]) -> str:
    value = str(item.get("hash") or "").strip()
    if value:
        return value
    value = str(item.get("good_nickname") or item.get("nickname") or "").strip()
    if value and not value.isdigit():
        try:
            return nickname_hash(value)
        except Exception:
            return value
    return value


def split_cargo_value(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",")]


def cargo_line_match(line: str) -> tuple[str, list[str], str] | None:
    match = re.match(r"^(\s*cargo\s*=\s*)(.*?)(\r?\n?)$", line, re.IGNORECASE)
    if not match:
        return None
    return match.group(1), split_cargo_value(match.group(2)), match.group(3)


def edit_offline_cargo_file(file_path: Path, item: dict[str, Any], quantity_delta: int) -> tuple[bool, str]:
    """Edit cargo = lines directly in an offline .fl file.

    Positive delta adds cargo, negative delta removes cargo.
    This is used only when the pilot is offline; online pilots are handled by FLHook.
    """
    quantity_delta = int(quantity_delta)
    if quantity_delta == 0:
        return True, "Без изменений."

    if not file_path.exists():
        return False, "Файл персонажа не найден."

    tokens = cargo_item_tokens(item)
    if not tokens:
        return False, "Не удалось определить cargo hash/nickname для файла персонажа."

    content = read_text(file_path)
    lines = content.splitlines(keepends=True)
    if not lines:
        lines = []

    found_indexes: list[tuple[int, str, list[str], str]] = []
    for index, line in enumerate(lines):
        parsed = cargo_line_match(line)
        if not parsed:
            continue
        prefix, parts, ending = parsed
        if not parts:
            continue
        if parts[0].strip().lower() in tokens:
            found_indexes.append((index, prefix, parts, ending))

    def make_line(prefix: str, parts: list[str], ending: str) -> str:
        if not ending:
            ending = "\n"
        return f"{prefix}{', '.join(parts)}{ending}"

    if quantity_delta > 0:
        if found_indexes:
            index, prefix, parts, ending = found_indexes[0]
            current = to_int(parts[1] if len(parts) > 1 else "0", 0)
            if len(parts) < 2:
                parts.append(str(quantity_delta))
            else:
                parts[1] = str(max(0, current) + quantity_delta)
            lines[index] = make_line(prefix, parts, ending)
        else:
            token = cargo_file_token(item)
            if not token:
                return False, "Не удалось определить cargo hash для записи в .fl."
            insert_at = max([idx for idx, line in enumerate(lines) if cargo_line_match(line)] or [-1]) + 1
            ending = "\n"
            if lines and lines[-1].endswith("\r\n"):
                ending = "\r\n"
            new_line = f"cargo = {token}, {quantity_delta}{ending}"
            if insert_at <= 0 or insert_at > len(lines):
                lines.append(new_line)
            else:
                lines.insert(insert_at, new_line)

        file_path.write_text("".join(lines), encoding="utf-8")
        return True, "Груз добавлен в offline .fl-файл персонажа."

    # Remove cargo.
    left = abs(quantity_delta)
    available = 0
    for _index, _prefix, parts, _ending in found_indexes:
        available += max(0, to_int(parts[1] if len(parts) > 1 else "1", 1))

    if available < left:
        return False, f"В трюме только {available} шт."

    remove_indexes: set[int] = set()
    for index, prefix, parts, ending in found_indexes:
        if left <= 0:
            break
        current = max(0, to_int(parts[1] if len(parts) > 1 else "1", 1))
        take = min(left, current)
        new_count = current - take
        if new_count > 0:
            if len(parts) < 2:
                parts.append(str(new_count))
            else:
                parts[1] = str(new_count)
            lines[index] = make_line(prefix, parts, ending)
        else:
            remove_indexes.add(index)
        left -= take

    if remove_indexes:
        lines = [line for index, line in enumerate(lines) if index not in remove_indexes]

    file_path.write_text("".join(lines), encoding="utf-8")
    return True, "Груз списан из offline .fl-файла персонажа."


def resolve_and_check_cargo(conn: sqlite3.Connection, item_token: str) -> tuple[dict[str, Any] | None, str]:
    item = resolve_item(conn, item_token)
    if not item:
        return None, "Предмет не найден в БД."

    if not is_cargo_good_for_hold(
        category=str(item.get("category") or ""),
        section=str(item.get("section") or ""),
        volume=float(item.get("volume") or 0),
    ):
        return None, cargo_hold_reject_reason()

    return item, ""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def row_value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def parse_positive_int(value: str, default: int = -1) -> int:
    amount = to_int(str(value).strip(), default)
    return amount if amount > 0 else -1


def character_file_key(character: dict[str, Any] | str | None) -> str:
    """Unique owner key for personal cabinet state.

    Account id is not enough: one account can contain several pilots.
    Warehouses/craft queues are isolated by account_id + character_file.
    """
    if isinstance(character, dict):
        value = str(character.get("file") or "").strip()
        if value:
            return value
        value = str(character.get("name") or "").strip()
        if value:
            return value.lower()
    elif character:
        return str(character).strip()

    return "unknown_character"


def character_name(character: dict[str, Any] | None) -> str:
    if isinstance(character, dict):
        return str(character.get("name") or character.get("file") or "Пилот").strip()
    return "Пилот"


def warehouses_table_is_per_character(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='warehouses'"
    ).fetchone()
    sql = str(row_value(row, "sql", "") or "")
    compact = re.sub(r"\s+", "", sql.lower()) if sql else ""
    return "character_file" in compact and "unique(account_id,character_file,location_hash,item_hash)" in compact


def migrate_warehouses_to_per_character(conn: sqlite3.Connection) -> None:
    """Rebuild old shared warehouse table into per-character table.

    Old rows are preserved with character_file='__legacy_shared__'.
    They are intentionally not shown in real characters' cabinets, preventing
    accidental access from another pilot on the same account.
    """
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='warehouses'"
    ).fetchone()

    if existing and warehouses_table_is_per_character(conn):
        return

    conn.execute("ALTER TABLE warehouses RENAME TO warehouses_legacy") if existing else None

    conn.executescript(
        """
        CREATE TABLE warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            character_file TEXT NOT NULL DEFAULT '',
            character_name TEXT,
            location_hash TEXT NOT NULL,
            location_type TEXT DEFAULT 'base',
            location_name TEXT,
            item_hash TEXT NOT NULL,
            item_nickname TEXT,
            item_display_name TEXT,
            category TEXT,
            volume REAL DEFAULT 0,
            mass REAL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(account_id, character_file, location_hash, item_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_warehouses_owner_location
            ON warehouses(account_id, character_file, location_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouses_item ON warehouses(item_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouses_display_name ON warehouses(item_display_name);
        """
    )

    if existing:
        legacy_columns = {row[1] for row in conn.execute("PRAGMA table_info(warehouses_legacy)").fetchall()}

        def col(name: str, fallback: str = "NULL") -> str:
            return name if name in legacy_columns else fallback

        legacy_sql = "'" + LEGACY_CHARACTER_FILE.replace("'", "''") + "'"

        if "character_file" in legacy_columns:
            character_file_expr = f"COALESCE(NULLIF(character_file, ''), {legacy_sql})"
        else:
            character_file_expr = legacy_sql

        if "character_name" in legacy_columns:
            character_name_expr = "COALESCE(NULLIF(character_name, ''), 'Legacy shared warehouse')"
        else:
            character_name_expr = "'Legacy shared warehouse'"

        conn.execute(
            f"""
            INSERT INTO warehouses
            (account_id, character_file, character_name, location_hash, location_type, location_name,
             item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
            SELECT
                account_id,
                {character_file_expr} AS character_file,
                {character_name_expr} AS character_name,
                location_hash,
                COALESCE({col('location_type', "'base'")}, 'base') AS location_type,
                {col('location_name', 'NULL')} AS location_name,
                item_hash,
                {col('item_nickname', 'NULL')} AS item_nickname,
                {col('item_display_name', 'NULL')} AS item_display_name,
                {col('category', 'NULL')} AS category,
                COALESCE({col('volume', '0')}, 0) AS volume,
                COALESCE({col('mass', '0')}, 0) AS mass,
                quantity,
                {col('created_at', 'NULL')} AS created_at,
                {col('updated_at', 'NULL')} AS updated_at
            FROM warehouses_legacy
            WHERE quantity > 0
            """
        )
        conn.execute("DROP TABLE warehouses_legacy")


def ensure_warehouse_schema(conn: sqlite3.Connection) -> None:
    global _WAREHOUSE_SCHEMA_READY

    # v76: this schema check used to run on every warehouse click. On Windows it
    # can be surprisingly slow because it runs table/index DDL and migrations.
    # Do it once per panel process; the DB is local to the panel.
    if _WAREHOUSE_SCHEMA_READY:
        return

    with _WAREHOUSE_SCHEMA_LOCK:
        if _WAREHOUSE_SCHEMA_READY:
            return

        migrate_warehouses_to_per_character(conn)

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS item_details (
                item_hash TEXT PRIMARY KEY,
                nickname TEXT,
                display_name TEXT,
                description TEXT,
                ids_name TEXT,
                ids_info TEXT,
                icon_source TEXT,
                icon_png TEXT,
                source_file TEXT,
                raw_json TEXT,
                updated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_item_details_nickname ON item_details(nickname);

            CREATE TABLE IF NOT EXISTS warehouse_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                account_id TEXT NOT NULL,
                character_file TEXT,
                character_name TEXT,
                location_hash TEXT NOT NULL,
                location_name TEXT,
                item_hash TEXT NOT NULL,
                item_display_name TEXT,
                quantity_delta INTEGER NOT NULL,
                operation TEXT NOT NULL,
                note TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_warehouse_log_account_character_location
                ON warehouse_log(account_id, character_file, location_hash);

            -- v77: global protection against negative warehouse quantities.
            CREATE TRIGGER IF NOT EXISTS trg_warehouses_no_negative_insert
            BEFORE INSERT ON warehouses
            WHEN NEW.quantity < 0
            BEGIN
                SELECT RAISE(ABORT, 'warehouse quantity cannot be negative');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_warehouses_no_negative_update
            BEFORE UPDATE OF quantity ON warehouses
            WHEN NEW.quantity < 0
            BEGIN
                SELECT RAISE(ABORT, 'warehouse quantity cannot be negative');
            END;
            CREATE INDEX IF NOT EXISTS idx_warehouse_log_created ON warehouse_log(created_at);
            """
        )

        conn.commit()
        _WAREHOUSE_SCHEMA_READY = True


def location_from_character(character: dict[str, Any]) -> dict[str, str]:
    base = character.get("base") or {}
    last_base = character.get("last_base") or {}

    token = str(base.get("code") or base.get("nickname") or "").strip()
    name = str(base.get("name") or "").strip()

    if not token or name in {"", "Неизвестно", "—"}:
        token = str(last_base.get("code") or last_base.get("nickname") or token or "unknown_base").strip()
        name = str(last_base.get("name") or name or "Неизвестная база").strip()

    if not name or name in {"Неизвестно", "—"}:
        name = "Неизвестная база"

    return {
        "token": token or "unknown_base",
        "name": name,
        "type": "base",
    }


def load_name_map_entry(conn: sqlite3.Connection, *tokens: str):
    expanded: list[str] = []

    for token in tokens:
        token = str(token or "").strip()
        if not token:
            continue
        expanded.append(token)

        if "_" in token and not token.lower().startswith("dsy_") and not token.isdigit():
            expanded.append("dsy_" + token)

    seen: set[str] = set()
    for token in expanded:
        key = token.lower()
        if not token or key in seen:
            continue
        seen.add(key)

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


def resolve_item(conn: sqlite3.Connection, item_token: str) -> dict[str, Any] | None:
    token = str(item_token or "").strip()
    if not token:
        return None

    item = conn.execute(
        """
        SELECT hash, nickname, good_nickname, equipment_nickname, display_name, category, section, volume, mass
        FROM items
        WHERE hash = ?
           OR nickname = ?
           OR good_nickname = ?
           OR equipment_nickname = ?
        LIMIT 1
        """,
        (token, token, token, token),
    ).fetchone()

    if item:
        item_hash = str(row_value(item, "hash", token))
        nickname = str(row_value(item, "nickname", token))
        good_nickname = str(row_value(item, "good_nickname", ""))
        equipment_nickname = str(row_value(item, "equipment_nickname", ""))
        category = str(row_value(item, "category", ""))
        section = str(row_value(item, "section", ""))
        volume = float(row_value(item, "volume", 0) or 0)

        mapped = load_name_map_entry(conn, token, item_hash, nickname, good_nickname, equipment_nickname)
        display_name = str(row_value(mapped, "display_name", "") or row_value(item, "display_name", "") or "Неизвестный предмет").strip()

        return {
            "hash": item_hash,
            "nickname": nickname,
            "display_name": display_name if display_name and "_" not in display_name else "Неизвестный предмет",
            "category": category or str(row_value(mapped, "category", "")),
            "section": section,
            "good_nickname": good_nickname,
            "equipment_nickname": equipment_nickname,
            "volume": volume,
            "mass": float(row_value(item, "mass", 0) or 0),
            "cargo_eligible": is_cargo_good_for_hold(category=category, section=section, volume=volume),
        }

    mapped = load_name_map_entry(conn, token)
    if mapped:
        return {
            "hash": str(row_value(mapped, "hash", token) or token),
            "nickname": str(row_value(mapped, "nickname", token) or token),
            "display_name": str(row_value(mapped, "display_name", "") or "Неизвестный предмет"),
            "category": str(row_value(mapped, "category", "")),
            "section": "",
            "good_nickname": str(row_value(mapped, "nickname", "") or ""),
            "equipment_nickname": "",
            "volume": 0.0,
            "mass": 0.0,
            "cargo_eligible": False,
        }

    return None


def load_warehouse(account_id: str, character_file: str, location_token: str) -> dict[str, Any]:
    conn = connect()
    ensure_warehouse_schema(conn)

    rows = conn.execute(
        """
        SELECT
            w.*,
            i.good_nickname AS db_good_nickname,
            i.equipment_nickname AS db_equipment_nickname,
            i.section AS db_section,
            i.category AS db_category,
            i.volume AS db_volume,
            d.description AS item_description,
            d.icon_png AS item_icon_png,
            d.raw_json AS item_raw_json
        FROM warehouses w
        LEFT JOIN items i
               ON i.hash = w.item_hash
               OR lower(i.nickname) = lower(w.item_nickname)
               OR lower(i.good_nickname) = lower(w.item_nickname)
               OR lower(i.equipment_nickname) = lower(w.item_nickname)
        LEFT JOIN item_details d
               ON d.item_hash = w.item_hash
               OR lower(d.nickname) = lower(w.item_nickname)
        WHERE w.account_id = ?
          AND w.character_file = ?
          AND w.location_hash = ?
          AND w.quantity > 0
        ORDER BY w.item_display_name COLLATE NOCASE, w.item_hash
        """,
        (account_id, character_file, location_token),
    ).fetchall()

    items = []
    total_quantity = 0
    total_volume = 0.0

    for row in rows:
        quantity = int(row_value(row, "quantity", 0) or 0)
        volume = float(row_value(row, "db_volume", row_value(row, "volume", 0)) or 0)
        category = str(row_value(row, "db_category", row_value(row, "category", "")) or "")
        section = str(row_value(row, "db_section", "") or "")
        cargo_eligible = is_cargo_good_for_hold(category=category, section=section, volume=volume)
        total_quantity += quantity
        total_volume += quantity * volume
        items.append({
            "id": row_value(row, "id"),
            "account_id": row_value(row, "account_id"),
            "character_file": row_value(row, "character_file", ""),
            "character_name": row_value(row, "character_name", ""),
            "location_hash": row_value(row, "location_hash"),
            "location_type": row_value(row, "location_type", "base"),
            "location_name": row_value(row, "location_name", ""),
            "item_hash": row_value(row, "item_hash"),
            "item_nickname": row_value(row, "item_nickname", ""),
            "item_display_name": row_value(row, "item_display_name", "") or "Неизвестный предмет",
            "category": category,
            "section": section,
            "good_nickname": row_value(row, "db_good_nickname", "") or "",
            "equipment_nickname": row_value(row, "db_equipment_nickname", "") or "",
            "volume": volume,
            "mass": float(row_value(row, "mass", 0) or 0),
            "cargo_eligible": cargo_eligible,
            "cargo_reject_reason": "" if cargo_eligible else cargo_hold_reject_reason(),
            "quantity": quantity,
            "total_volume": quantity * volume,
            "description": row_value(row, "item_description", "") or "",
            "icon_png": row_value(row, "item_icon_png", "") or "",
            "raw_json": row_value(row, "item_raw_json", "") or "",
        })

    conn.close()

    return {
        "items": items,
        "total_quantity": total_quantity,
        "total_volume": total_volume,
    }


def current_base_warehouse(account_id: str, character: dict[str, Any]) -> dict[str, Any]:
    location = location_from_character(character)
    char_file = character_file_key(character)
    data = load_warehouse(account_id, char_file, location["token"])
    return {
        "available": True,
        "account_id": account_id,
        "character_file": char_file,
        "character_name": character_name(character),
        "location": location,
        **data,
    }




def all_character_warehouses(account_id: str, character: dict[str, Any]) -> dict[str, Any]:
    """All personal warehouses for this pilot across bases/planets.

    This is DB-only. It does not check FLHook and does not touch .fl files.
    """
    char_file = character_file_key(character)
    current_location = location_from_character(character)

    conn = connect()
    ensure_warehouse_schema(conn)

    rows = conn.execute(
        """
        SELECT
            location_hash,
            COALESCE(NULLIF(location_name, ''), location_hash) AS location_name,
            COALESCE(NULLIF(location_type, ''), 'base') AS location_type,
            COUNT(*) AS item_rows,
            SUM(quantity) AS total_quantity,
            SUM(quantity * COALESCE(volume, 0)) AS total_volume
        FROM warehouses
        WHERE account_id = ?
          AND character_file = ?
          AND quantity > 0
        GROUP BY location_hash, location_name, location_type
        ORDER BY location_name COLLATE NOCASE, location_hash
        """,
        (account_id, char_file),
    ).fetchall()

    conn.close()

    locations: list[dict[str, Any]] = []
    for row in rows:
        location = {
            "token": str(row_value(row, "location_hash", "") or ""),
            "name": str(row_value(row, "location_name", "") or "Неизвестная база"),
            "type": str(row_value(row, "location_type", "base") or "base"),
        }
        data = load_warehouse(account_id, char_file, location["token"])
        locations.append({
            "location": location,
            "items": data.get("items") or [],
            "item_rows": int(row_value(row, "item_rows", 0) or 0),
            "total_quantity": int(row_value(row, "total_quantity", 0) or 0),
            "total_volume": float(row_value(row, "total_volume", 0) or 0),
            "is_current": location["token"] == current_location["token"],
        })

    return {
        "character_file": char_file,
        "current_location": current_location,
        "locations": locations,
    }

def log_operation(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    character: dict[str, Any],
    location: dict[str, str],
    item: dict[str, Any],
    quantity_delta: int,
    operation: str,
    note: str,
) -> None:
    conn.execute(
        """
        INSERT INTO warehouse_log
        (created_at, account_id, character_file, character_name, location_hash, location_name,
         item_hash, item_display_name, quantity_delta, operation, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            account_id,
            character_file_key(character),
            character_name(character),
            location["token"],
            location["name"],
            item["hash"],
            item["display_name"],
            quantity_delta,
            operation,
            note,
        ),
    )


def add_test_item(account_id: str, character: dict[str, Any], item_token: str, quantity: int) -> tuple[bool, str]:
    """Add item to this character personal SQLite warehouse."""
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    conn = connect()
    ensure_warehouse_schema(conn)
    location = location_from_character(character)
    char_file = character_file_key(character)
    char_name = character_name(character)
    item = resolve_item(conn, item_token)

    if not item:
        conn.close()
        return False, "Предмет не найден в БД."

    ts = now_iso()

    try:
        conn.execute(
            """
            INSERT INTO warehouses
            (account_id, character_file, character_name, location_hash, location_type, location_name,
             item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, character_file, location_hash, item_hash)
            DO UPDATE SET
                quantity = quantity + excluded.quantity,
                character_name = excluded.character_name,
                location_name = excluded.location_name,
                item_nickname = excluded.item_nickname,
                item_display_name = excluded.item_display_name,
                category = excluded.category,
                volume = excluded.volume,
                mass = excluded.mass,
                updated_at = excluded.updated_at
            """,
            (
                account_id,
                char_file,
                char_name,
                location["token"],
                location["type"],
                location["name"],
                item["hash"],
                item["nickname"],
                item["display_name"],
                item["category"],
                item["volume"],
                item["mass"],
                quantity,
                ts,
                ts,
            ),
        )
        log_operation(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            item=item,
            quantity_delta=quantity,
            operation="warehouse_add",
            note="Added to personal SQLite warehouse.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка склада: {exc}"

    conn.close()
    return True, f"{quantity} шт. «{item['display_name']}» добавлено в личный склад пилота «{char_name}» на базе «{location['name']}»."


def remove_test_item(account_id: str, character: dict[str, Any], item_token: str, quantity: int, source_location: dict[str, str] | None = None) -> tuple[bool, str]:
    """DB-only test remove/decrement from this character's warehouse."""
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    conn = connect()
    ensure_warehouse_schema(conn)
    location = source_location or location_from_character(character)
    char_file = character_file_key(character)
    item = resolve_item(conn, item_token)

    if not item:
        conn.close()
        return False, "Предмет не найден в БД."

    row = conn.execute(
        """
        SELECT quantity
        FROM warehouses
        WHERE account_id = ?
          AND character_file = ?
          AND location_hash = ?
          AND item_hash = ?
        LIMIT 1
        """,
        (account_id, char_file, location["token"], item["hash"]),
    ).fetchone()

    current = int(row_value(row, "quantity", 0) or 0)
    if current <= 0:
        conn.close()
        return False, "Такого предмета нет в личном складе этого пилота на этой базе."

    if quantity > current:
        conn.close()
        return False, f"На складе только {current} шт."

    new_quantity = current - quantity

    try:
        if new_quantity > 0:
            conn.execute(
                """
                UPDATE warehouses
                SET quantity = ?, updated_at = ?
                WHERE account_id = ?
                  AND character_file = ?
                  AND location_hash = ?
                  AND item_hash = ?
                """,
                (new_quantity, now_iso(), account_id, char_file, location["token"], item["hash"]),
            )
        else:
            conn.execute(
                """
                DELETE FROM warehouses
                WHERE account_id = ?
                  AND character_file = ?
                  AND location_hash = ?
                  AND item_hash = ?
                """,
                (account_id, char_file, location["token"], item["hash"]),
            )

        log_operation(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            item=item,
            quantity_delta=-quantity,
            operation="test_remove",
            note="DB-only prototype. Ship cargo was not changed.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка склада: {exc}"

    conn.close()
    return True, f"Тест: {quantity} шт. «{item['display_name']}» удалено из личного склада пилота «{character_name(character)}». Трюм корабля не изменялся."



def warehouse_item_from_row(row: Any) -> dict[str, Any]:
    """Build item dict directly from warehouses row.

    For pilot-to-pilot transfer we do not need expensive item/name lookups: the
    row already contains the stable item_hash and display data needed to decrement
    one warehouse and increment another.
    """
    return {
        "hash": str(row_value(row, "item_hash", "") or ""),
        "nickname": str(row_value(row, "item_nickname", "") or row_value(row, "item_hash", "") or ""),
        "display_name": str(row_value(row, "item_display_name", "") or row_value(row, "item_nickname", "") or "Неизвестный предмет"),
        "category": str(row_value(row, "category", "") or ""),
        "volume": float(row_value(row, "volume", 0) or 0),
        "mass": float(row_value(row, "mass", 0) or 0),
    }


def add_item_to_specific_warehouse(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    character: dict[str, Any],
    location: dict[str, str],
    item: dict[str, Any],
    quantity: int,
) -> None:
    char_file = character_file_key(character)
    char_name = character_name(character)
    ts = now_iso()

    conn.execute(
        """
        INSERT INTO warehouses
        (account_id, character_file, character_name, location_hash, location_type, location_name,
         item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, character_file, location_hash, item_hash)
        DO UPDATE SET
            quantity = quantity + excluded.quantity,
            character_name = excluded.character_name,
            location_name = excluded.location_name,
            item_nickname = excluded.item_nickname,
            item_display_name = excluded.item_display_name,
            category = excluded.category,
            volume = excluded.volume,
            mass = excluded.mass,
            updated_at = excluded.updated_at
        """,
        (
            account_id,
            char_file,
            char_name,
            location["token"],
            location["type"],
            location["name"],
            item["hash"],
            item["nickname"],
            item["display_name"],
            item["category"],
            item["volume"],
            item["mass"],
            quantity,
            ts,
            ts,
        ),
    )






def admin_add_item_to_warehouse(account_id: str, character: dict[str, Any], item_token: str, quantity: int, location: dict[str, str]) -> tuple[bool, str]:
    """Admin: create/add any item in any personal warehouse location."""
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    conn = connect()
    ensure_warehouse_schema(conn)

    item = resolve_item(conn, item_token)
    if not item:
        conn.close()
        return False, "Предмет не найден в БД. Укажи hash/nickname/good_nickname/equipment_nickname."

    try:
        add_item_to_specific_warehouse(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            item=item,
            quantity=quantity,
        )
        log_operation(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            item=item,
            quantity_delta=quantity,
            operation="admin_add",
            note="admin: item added to warehouse",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка admin add: {exc}"

    conn.close()
    return True, f"ADMIN: добавлено {quantity} шт. «{item['display_name']}» пилоту «{character_name(character)}» на склад «{location.get('name') or location.get('token')}»."


def admin_remove_item_from_warehouse(account_id: str, character: dict[str, Any], item_token: str, quantity: int, location: dict[str, str]) -> tuple[bool, str]:
    """Admin: delete/decrement any item from any personal warehouse location."""
    return remove_test_item(account_id, character, item_token, quantity, location)


def admin_move_item_between_warehouses(
    repo: Any,
    source_account_id: str,
    source_character: dict[str, Any],
    item_token: str,
    quantity: int,
    source_location: dict[str, str],
    target_character_name: str,
    target_location: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Admin: move item from any pilot/location to any pilot/location.

    This is DB-only warehouse movement. It does not touch .fl and does not call FLHook.
    """
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    target_match = repo.find_unique_character(str(target_character_name or "").strip())
    if target_match is None:
        return False, "Пилот-получатель не найден."
    if target_match == "ambiguous":
        return False, "Найдено несколько пилотов с таким никнеймом."

    target_account, target_character = target_match
    target_location = target_location or source_location

    source_char_file = character_file_key(source_character)
    target_char_file = character_file_key(target_character)
    ts = now_iso()

    conn = connect()
    ensure_warehouse_schema(conn)

    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT item_hash, item_nickname, item_display_name, category, volume, mass, quantity
            FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
            LIMIT 1
            """,
            (source_account_id, source_char_file, source_location["token"], str(item_token or "").strip()),
        ).fetchone()

        if not row:
            conn.rollback()
            conn.close()
            return False, "Такого предмета нет на исходном складе."

        current = int(row_value(row, "quantity", 0) or 0)
        if current <= 0:
            conn.rollback()
            conn.close()
            return False, "Такого предмета нет на исходном складе."

        if quantity > current:
            conn.rollback()
            conn.close()
            return False, f"На исходном складе только {current} шт. Нельзя переместить {quantity} шт."

        item = warehouse_item_from_row(row)

        updated = conn.execute(
            """
            UPDATE warehouses
            SET quantity = quantity - ?, updated_at = ?
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity >= ?
            """,
            (quantity, ts, source_account_id, source_char_file, source_location["token"], item["hash"], quantity),
        )

        if updated.rowcount != 1:
            conn.rollback()
            conn.close()
            return False, "Не удалось списать предмет с исходного склада."

        conn.execute(
            """
            DELETE FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity <= 0
            """,
            (source_account_id, source_char_file, source_location["token"], item["hash"]),
        )

        add_item_to_specific_warehouse(
            conn,
            account_id=target_account["id"],
            character=target_character,
            location=target_location,
            item=item,
            quantity=quantity,
        )

        log_operation(
            conn,
            account_id=source_account_id,
            character=source_character,
            location=source_location,
            item=item,
            quantity_delta=-quantity,
            operation="admin_move_out",
            note=f"admin: moved to {character_name(target_character)} / {target_location.get('name') or target_location.get('token')}",
        )
        log_operation(
            conn,
            account_id=target_account["id"],
            character=target_character,
            location=target_location,
            item=item,
            quantity_delta=quantity,
            operation="admin_move_in",
            note=f"admin: moved from {character_name(source_character)} / {source_location.get('name') or source_location.get('token')}",
        )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка admin move: {exc}"

    conn.close()
    return True, f"ADMIN: перемещено {quantity} шт. «{item['display_name']}» от «{character_name(source_character)}» к «{character_name(target_character)}»."


def warehouse_to_hold_via_flhook(repo: Any, account_id: str, character: dict[str, Any], item_token: str, quantity: int) -> tuple[bool, str]:
    """Move SQLite warehouse cargo to pilot hold.

    Online pilot: FLHook addcargo + savechar.
    Offline pilot: direct cargo = edit in the .fl save file.
    Only normal cargo/commodity is allowed; equipment is intentionally blocked.
    """

    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    char_name = character_name(character)
    char_file = character_file_key(character)
    char_path = Path(getattr(repo, "accounts_dir", "")) / str(account_id) / char_file

    conn = connect()
    ensure_warehouse_schema(conn)
    location = location_from_character(character)

    try:
        item, error = resolve_and_check_cargo(conn, item_token)
        if not item:
            conn.close()
            return False, error

        row = conn.execute(
            """
            SELECT
                w.quantity,
                w.item_nickname,
                w.category AS warehouse_category,
                w.volume AS warehouse_volume,
                i.good_nickname,
                i.equipment_nickname,
                i.category AS item_category,
                i.section AS item_section,
                i.volume AS item_volume
            FROM warehouses w
            LEFT JOIN items i
                   ON i.hash = w.item_hash
                   OR lower(i.nickname) = lower(w.item_nickname)
                   OR lower(i.good_nickname) = lower(w.item_nickname)
                   OR lower(i.equipment_nickname) = lower(w.item_nickname)
            WHERE w.account_id = ?
              AND w.character_file = ?
              AND w.location_hash = ?
              AND w.item_hash = ?
            LIMIT 1
            """,
            (account_id, char_file, location["token"], item["hash"]),
        ).fetchone()

        current = int(row_value(row, "quantity", 0) or 0)
        if current <= 0:
            conn.close()
            return False, "Такого предмета нет в личном складе пилота на этой базе."

        if quantity > current:
            conn.close()
            return False, f"На складе только {current} шт."

        cargo_category = str(row_value(row, "item_category", row_value(row, "warehouse_category", item.get("category", ""))) or "")
        cargo_section = str(row_value(row, "item_section", item.get("section", "")) or "")
        cargo_volume = float(row_value(row, "item_volume", row_value(row, "warehouse_volume", item.get("volume", 0))) or 0)

        if not is_cargo_good_for_hold(category=cargo_category, section=cargo_section, volume=cargo_volume):
            conn.close()
            return False, cargo_hold_reject_reason()

        online = False
        try:
            online = bool(getattr(repo, "flhook", None) and repo.flhook.enabled and repo.flhook_online(char_name))
        except Exception:
            online = False

        mode = "FLHook" if online else "offline .fl"

        if online:
            good = (
                str(row_value(row, "good_nickname", "") or "").strip()
                or str(row_value(row, "item_nickname", "") or "").strip()
                or str(item.get("good_nickname") or item.get("nickname") or item.get("hash") or "").strip()
            )

            if not good:
                conn.close()
                return False, "Не удалось определить good nickname для FLHook addcargo."

            try:
                remaining = repo.flhook.remaining_hold_size(char_name)
                required = int(quantity * cargo_volume) if cargo_volume > 0 else 0
                if remaining is not None and required > 0 and required > remaining:
                    conn.close()
                    return False, f"В трюме недостаточно места. Нужно {required}, свободно {remaining}."
            except Exception:
                pass

            try:
                repo.flhook.add_cargo(char_name, good, quantity, 0)
                try:
                    repo.flhook.save_char(char_name)
                except Exception:
                    pass
            except Exception as exc:
                conn.close()
                return False, f"FLHook не смог добавить груз в трюм: {exc}"
        else:
            ok, message = edit_offline_cargo_file(char_path, item, quantity)
            if not ok:
                conn.close()
                return False, message

        new_quantity = current - quantity
        try:
            if new_quantity > 0:
                conn.execute(
                    """
                    UPDATE warehouses
                    SET quantity = ?, updated_at = ?
                    WHERE account_id = ?
                      AND character_file = ?
                      AND location_hash = ?
                      AND item_hash = ?
                    """,
                    (new_quantity, now_iso(), account_id, char_file, location["token"], item["hash"]),
                )
            else:
                conn.execute(
                    """
                    DELETE FROM warehouses
                    WHERE account_id = ?
                      AND character_file = ?
                      AND location_hash = ?
                      AND item_hash = ?
                    """,
                    (account_id, char_file, location["token"], item["hash"]),
                )

            log_operation(
                conn,
                account_id=account_id,
                character=character,
                location=location,
                item=item,
                quantity_delta=-quantity,
                operation="to_hold",
                note=f"{mode}: warehouse -> hold",
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            conn.close()
            return False, f"Груз добавлен в трюм, но склад SQLite не обновился: {exc}"

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return True, f"{quantity} шт. «{item['display_name']}» перенесено из склада в трюм корабля ({mode})."



def hold_to_warehouse_smart(repo: Any, account_id: str, character: dict[str, Any], item_token: str, quantity: int) -> tuple[bool, str]:
    """Move cargo from pilot hold to personal SQLite warehouse.

    Online pilot: FLHook removecargo by cargo id/archid.
    Offline pilot: direct cargo = edit in the .fl save file.
    Only normal cargo/commodity is accepted.
    """
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    char_name = character_name(character)
    char_file = character_file_key(character)
    char_path = Path(getattr(repo, "accounts_dir", "")) / str(account_id) / char_file

    conn = connect()
    ensure_warehouse_schema(conn)

    try:
        item, error = resolve_and_check_cargo(conn, item_token)
        conn.close()
        if not item:
            return False, error
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return False, f"Ошибка БД предметов: {exc}"

    online = False
    try:
        online = bool(getattr(repo, "flhook", None) and repo.flhook.enabled and repo.flhook_online(char_name))
    except Exception:
        online = False

    mode = "FLHook" if online else "offline .fl"

    if online:
        archid = str(item.get("hash") or item_token).strip()
        try:
            repo.flhook.remove_cargo_by_archid(char_name, archid, quantity)
            try:
                repo.flhook.save_char(char_name)
            except Exception:
                pass
        except Exception as exc:
            return False, f"FLHook не смог списать груз из трюма: {exc}"
    else:
        ok, message = edit_offline_cargo_file(char_path, item, -quantity)
        if not ok:
            return False, message

    ok, text = add_test_item(account_id, character, item["hash"], quantity)
    if not ok:
        # Best-effort rollback to avoid cargo loss.
        if online:
            try:
                good = str(item.get("good_nickname") or item.get("nickname") or item.get("hash") or "").strip()
                if good:
                    repo.flhook.add_cargo(char_name, good, quantity, 0)
                    repo.flhook.save_char(char_name)
            except Exception:
                pass
        else:
            try:
                edit_offline_cargo_file(char_path, item, quantity)
            except Exception:
                pass
        return False, f"Груз снят с трюма, но склад не обновился: {text}"

    return True, f"{quantity} шт. «{item['display_name']}» перенесено из трюма корабля в склад базы ({mode})."




PILOT_TRANSFER_POLICY = "warehouse_to_warehouse_only"


def pilot_transfer_policy_text() -> str:
    return "Передача другому пилоту выполняется только склад → склад. .fl-файлы, FLHook и корабль получателя не затрагиваются."





def get_warehouse_history(account_id: str, character_file: str, location_token: str = "", limit: int = 80) -> list[dict[str, Any]]:
    """Return warehouse operation history for one pilot.

    In the "Склад базы" tab we show history for current pilot and, when
    available, current base/location. This keeps it close to the visible stock.
    """
    conn = connect()
    ensure_warehouse_schema(conn)

    params: list[Any] = [account_id, character_file]
    location_filter = ""
    if str(location_token or "").strip():
        location_filter = "AND location_hash = ?"
        params.append(str(location_token).strip())

    params.append(max(1, int(limit or 80)))

    rows = conn.execute(
        f"""
        SELECT
            created_at,
            account_id,
            character_file,
            character_name,
            location_hash,
            location_name,
            item_hash,
            item_display_name,
            quantity_delta,
            operation,
            note
        FROM warehouse_log
        WHERE account_id = ?
          AND character_file = ?
          {location_filter}
        ORDER BY id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    conn.close()

    history: list[dict[str, Any]] = []
    for row in rows:
        history.append({
            "created_at": row_value(row, "created_at", ""),
            "account_id": row_value(row, "account_id", ""),
            "character_file": row_value(row, "character_file", ""),
            "character_name": row_value(row, "character_name", ""),
            "location_hash": row_value(row, "location_hash", ""),
            "location_name": row_value(row, "location_name", ""),
            "item_hash": row_value(row, "item_hash", ""),
            "item_display_name": row_value(row, "item_display_name", ""),
            "quantity_delta": int(row_value(row, "quantity_delta", 0) or 0),
            "operation": row_value(row, "operation", ""),
            "note": row_value(row, "note", ""),
        })

    return history

def transfer_test_item(repo: Any, sender_account_id: str, sender_character: dict[str, Any], item_token: str, target_name: str, quantity: int, source_location: dict[str, str] | None = None) -> tuple[bool, str]:
    """Fast and safe internal pilot-to-pilot transfer.

    HARD POLICY:
      sender SQLite warehouse -> receiver SQLite warehouse only.

    Safety:
      - quantity is checked before transfer;
      - UPDATE is atomic and additionally guarded with WHERE quantity >= ?;
      - DB triggers block any negative quantity if another code path is wrong.
    """
    target_name = str(target_name or "").strip()
    item_token = str(item_token or "").strip()

    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    if not item_token:
        return False, "Предмет не выбран."

    if not target_name:
        return False, "Укажи никнейм пилота-получателя."

    target_match = repo.find_unique_character(target_name)
    if target_match is None:
        return False, "Пилот-получатель не найден."
    if target_match == "ambiguous":
        return False, "Найдено несколько пилотов с таким никнеймом. Нужна более точная идентификация."

    target_account, target_character = target_match

    sender_char_file = character_file_key(sender_character)
    target_char_file = character_file_key(target_character)

    if sender_account_id == target_account["id"] and sender_char_file == target_char_file:
        return False, "Нельзя передать предмет самому себе."

    location = source_location or location_from_character(sender_character)
    target_char_name = character_name(target_character)
    sender_char_name = character_name(sender_character)
    ts = now_iso()

    conn = connect()
    ensure_warehouse_schema(conn)

    try:
        # Take write lock before reading quantity, so two simultaneous transfers
        # cannot both see the same old value and overspend the warehouse row.
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            """
            SELECT item_hash, item_nickname, item_display_name, category, volume, mass, quantity
            FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
            LIMIT 1
            """,
            (sender_account_id, sender_char_file, location["token"], item_token),
        ).fetchone()

        if not row:
            conn.rollback()
            conn.close()
            return False, "Такого предмета нет в личном складе отправителя на этой базе."

        current = int(row_value(row, "quantity", 0) or 0)
        if current <= 0:
            conn.rollback()
            conn.close()
            return False, "Такого предмета нет в личном складе отправителя на этой базе."

        if quantity > current:
            conn.rollback()
            conn.close()
            return False, f"На складе только {current} шт. Нельзя передать {quantity} шт."

        item = warehouse_item_from_row(row)
        if not item.get("hash"):
            conn.rollback()
            conn.close()
            return False, "Не удалось определить предмет склада."

        # Atomic guarded decrement. Even if another request somehow slips in,
        # SQLite will not allow quantity to go below zero.
        updated = conn.execute(
            """
            UPDATE warehouses
            SET quantity = quantity - ?, updated_at = ?
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity >= ?
            """,
            (quantity, ts, sender_account_id, sender_char_file, location["token"], item["hash"], quantity),
        )

        if updated.rowcount != 1:
            latest_row = conn.execute(
                """
                SELECT quantity
                FROM warehouses
                WHERE account_id = ?
                  AND character_file = ?
                  AND location_hash = ?
                  AND item_hash = ?
                LIMIT 1
                """,
                (sender_account_id, sender_char_file, location["token"], item["hash"]),
            ).fetchone()
            latest = int(row_value(latest_row, "quantity", 0) or 0)
            conn.rollback()
            conn.close()
            return False, f"На складе только {latest} шт. Нельзя передать {quantity} шт."

        conn.execute(
            """
            DELETE FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity <= 0
            """,
            (sender_account_id, sender_char_file, location["token"], item["hash"]),
        )

        conn.execute(
            """
            INSERT INTO warehouses
            (account_id, character_file, character_name, location_hash, location_type, location_name,
             item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, character_file, location_hash, item_hash)
            DO UPDATE SET
                quantity = quantity + excluded.quantity,
                character_name = excluded.character_name,
                location_name = excluded.location_name,
                item_nickname = excluded.item_nickname,
                item_display_name = excluded.item_display_name,
                category = excluded.category,
                volume = excluded.volume,
                mass = excluded.mass,
                updated_at = excluded.updated_at
            """,
            (
                target_account["id"],
                target_char_file,
                target_char_name,
                location["token"],
                location["type"],
                location["name"],
                item["hash"],
                item["nickname"],
                item["display_name"],
                item["category"],
                item["volume"],
                item["mass"],
                quantity,
                ts,
                ts,
            ),
        )

        conn.execute(
            """
            INSERT INTO warehouse_log
            (created_at, account_id, character_file, character_name, location_hash, location_name,
             item_hash, item_display_name, quantity_delta, operation, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                sender_account_id,
                sender_char_file,
                sender_char_name,
                location["token"],
                location["name"],
                item["hash"],
                item["display_name"],
                -quantity,
                "transfer_out",
                f"{PILOT_TRANSFER_POLICY}: to pilot {target_char_name}.",
            ),
        )

        conn.execute(
            """
            INSERT INTO warehouse_log
            (created_at, account_id, character_file, character_name, location_hash, location_name,
             item_hash, item_display_name, quantity_delta, operation, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                target_account["id"],
                target_char_file,
                target_char_name,
                location["token"],
                location["name"],
                item["hash"],
                item["display_name"],
                quantity,
                "transfer_in",
                f"{PILOT_TRANSFER_POLICY}: from pilot {sender_char_name}.",
            ),
        )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка передачи: {exc}"

    conn.close()
    return True, f"Передано склад → склад: {quantity} шт. «{item['display_name']}» на личный склад пилота «{target_char_name}» на базе «{location['name']}». .fl-файл и корабль получателя не затрагивались."

