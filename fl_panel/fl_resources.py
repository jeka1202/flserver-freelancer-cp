from __future__ import annotations

import argparse
import ctypes
import html
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .fl_ini_parser import iter_ini_sections


RESOURCE_DB_PATH = Path(__file__).resolve().parent / "data" / "fl_resources.db"

LOAD_LIBRARY_AS_DATAFILE = 0x00000002
LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020
LOAD_LIBRARY_FLAGS = LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_value(value: Any) -> str:
    return str(value or "").strip()


def first(values: list[str] | str | None) -> str:
    if isinstance(values, list):
        return clean_value(values[0]) if values else ""
    return clean_value(values)


def parse_int(value: Any) -> int:
    text = clean_value(value)
    if not text:
        return 0
    try:
        return int(text, 0)
    except Exception:
        pass
    try:
        return int(float(text))
    except Exception:
        return 0


def parse_float(value: Any) -> float:
    text = clean_value(value).replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def numeric_text(value: Any) -> str:
    """Keep game numeric values as text.

    Some mods contain very large integers. SQLite INTEGER is signed 64-bit,
    so for resource-cache DB we store raw numeric-ish values as TEXT.
    """

    return clean_value(value)


def connect_resource_db(db_path: Path = RESOURCE_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_resource_schema(conn)
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def column_decl(conn: sqlite3.Connection, table_name: str, column_name: str) -> str:
    if not table_exists(conn, table_name):
        return ""
    for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall():
        if str(row[1]).lower() == column_name.lower():
            return str(row[2] or "")
    return ""


def reset_old_resource_schema_if_needed(conn: sqlite3.Connection) -> None:
    """v44 migration.

    v42/v43 created resource_strings.ids as INTEGER PRIMARY KEY.
    Some Freelancer/mod ids can be larger than SQLite INTEGER range.
    This DB is only a rebuildable cache, so the safest migration is to drop
    cache tables with the old numeric-id schema and rebuild them as TEXT ids.
    """

    need_reset = False

    if table_exists(conn, "resource_strings"):
        ids_decl = column_decl(conn, "resource_strings", "ids").upper()
        if "INT" in ids_decl:
            need_reset = True

    if table_exists(conn, "resource_items"):
        ids_name_decl = column_decl(conn, "resource_items", "ids_name").upper()
        ids_info_decl = column_decl(conn, "resource_items", "ids_info").upper()
        price_decl = column_decl(conn, "resource_items", "price").upper()
        hit_pts_decl = column_decl(conn, "resource_items", "hit_pts").upper()
        if "INT" in ids_name_decl or "INT" in ids_info_decl or "INT" in price_decl or "INT" in hit_pts_decl:
            need_reset = True

    if table_exists(conn, "resource_strings"):
        resource_id_decl = column_decl(conn, "resource_strings", "resource_id").upper()
        if "INT" in resource_id_decl:
            # Not usually huge, but keeping all source ids as TEXT avoids another edge case.
            need_reset = True

    if need_reset:
        conn.executescript(
            """
            DROP TABLE IF EXISTS resource_strings;
            DROP TABLE IF EXISTS resource_items;
            DROP TABLE IF EXISTS resource_sync_log;
            """
        )
        conn.commit()


def ensure_resource_schema(conn: sqlite3.Connection) -> None:
    reset_old_resource_schema_if_needed(conn)

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS resource_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS resource_dlls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_order INTEGER,
            dll_path TEXT NOT NULL,
            dll_name TEXT NOT NULL,
            source TEXT,
            exists_flag INTEGER DEFAULT 1,
            imported_at TEXT,
            UNIQUE(dll_path)
        );

        CREATE TABLE IF NOT EXISTS resource_strings (
            ids TEXT PRIMARY KEY,
            text TEXT,
            clean_text TEXT,
            dll_path TEXT,
            resource_id TEXT DEFAULT '',
            source TEXT,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_resource_strings_clean_text ON resource_strings(clean_text);

        CREATE TABLE IF NOT EXISTS resource_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            source_file TEXT,
            section TEXT,
            item_type TEXT,
            category TEXT,
            ids_name TEXT DEFAULT '',
            ids_info TEXT DEFAULT '',
            display_name TEXT,
            description TEXT,
            price TEXT DEFAULT '',
            volume REAL DEFAULT 0,
            mass REAL DEFAULT 0,
            hit_pts TEXT DEFAULT '',
            icon TEXT,
            raw_json TEXT,
            updated_at TEXT,
            UNIQUE(nickname, source_file, section)
        );

        CREATE INDEX IF NOT EXISTS idx_resource_items_nickname ON resource_items(nickname);
        CREATE INDEX IF NOT EXISTS idx_resource_items_display_name ON resource_items(display_name);
        CREATE INDEX IF NOT EXISTS idx_resource_items_ids_name ON resource_items(ids_name);
        CREATE INDEX IF NOT EXISTS idx_resource_items_ids_info ON resource_items(ids_info);

        CREATE TABLE IF NOT EXISTS resource_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            exe_dir TEXT,
            data_dir TEXT,
            db_path TEXT,
            items_total INTEGER DEFAULT 0,
            ids_name_resolved INTEGER DEFAULT 0,
            ids_info_resolved INTEGER DEFAULT 0,
            errors_json TEXT
        );
        """
    )

    conn.execute(
        """
        INSERT INTO resource_meta(key, value)
        VALUES ('schema_version', 'v44_text_ids')
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """
    )
    conn.commit()


def normalize_dll_name(value: str) -> str:
    value = clean_value(value).strip('"').strip("'")
    value = value.replace("/", "\\")
    return value


def find_freelancer_ini(exe_dir: Path) -> Path | None:
    exe_dir = Path(exe_dir)
    candidates = [
        exe_dir / "freelancer.ini",
        exe_dir / "Freelancer.ini",
        exe_dir.parent / "EXE" / "freelancer.ini",
        exe_dir.parent / "EXE" / "Freelancer.ini",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for item in exe_dir.glob("*.ini"):
        if item.name.lower() == "freelancer.ini":
            return item
    return None


def resolve_dll_path(exe_dir: Path, token: str) -> Path | None:
    token = normalize_dll_name(token)
    if not token:
        return None

    raw = Path(token)
    candidates: list[Path] = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(
            [
                exe_dir / token,
                exe_dir / raw.name,
                exe_dir.parent / token,
                exe_dir.parent / "EXE" / token,
                exe_dir.parent / "DLLS" / raw.name,
                exe_dir.parent / "DATA" / raw.name,
            ]
        )

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        except Exception:
            continue

    wanted = raw.name.lower()
    for candidate in exe_dir.glob("*.dll"):
        if candidate.name.lower() == wanted:
            return candidate.resolve()

    return None


def discover_resource_dlls(exe_dir: Path) -> tuple[list[Path], list[Path], Path | None]:
    exe_dir = Path(exe_dir)
    freelancer_ini = find_freelancer_ini(exe_dir)

    ordered: list[Path] = []
    seen: set[str] = set()

    if freelancer_ini and freelancer_ini.exists():
        try:
            for section, values in iter_ini_sections(freelancer_ini):
                if section.lower() != "resources":
                    continue
                for token in values.get("dll", []):
                    path = resolve_dll_path(exe_dir, token)
                    if path:
                        key = str(path).lower()
                        if key not in seen:
                            ordered.append(path)
                            seen.add(key)
        except Exception:
            pass

    extra: list[Path] = []
    for dll in exe_dir.glob("*.dll"):
        try:
            resolved = dll.resolve()
        except Exception:
            resolved = dll
        key = str(resolved).lower()
        if key not in seen:
            extra.append(resolved)
            seen.add(key)

    return ordered, sorted(extra, key=lambda p: p.name.lower()), freelancer_ini


def clean_resource_text(text: str) -> str:
    text = clean_value(text)
    if not text:
        return ""

    text = text.replace("\\n", "\n").replace("\\r", "\n")
    text = html.unescape(text)

    text = re.sub(r"(?i)<\s*para\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*text\s*>\s*<\s*text[^>]*>", " ", text)
    text = re.sub(
        r"(?i)<\s*/?\s*(rdl|push|pop|text|justify|left|right|center|font|color|bold|italic|underline|list|li|table|tr|td)[^>]*>",
        "",
        text,
    )
    text = re.sub(r"<[^>]+>", "", text)

    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)

    return "\n".join(lines).strip()


class ResourceResolver:
    def __init__(self, exe_dir: Path):
        self.exe_dir = Path(exe_dir)
        self.ordered_dlls, self.extra_dlls, self.freelancer_ini = discover_resource_dlls(self.exe_dir)
        self.all_dlls = self.ordered_dlls + [p for p in self.extra_dlls if p not in self.ordered_dlls]
        self.handles: dict[Path, int] = {}
        self.cache: dict[tuple[str, int], str] = {}

        self.is_windows = os.name == "nt" and getattr(ctypes, "windll", None) is not None
        self.kernel32 = ctypes.windll.kernel32 if self.is_windows else None
        self.user32 = ctypes.windll.user32 if self.is_windows else None

        if self.is_windows:
            self.kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
            self.kernel32.LoadLibraryExW.restype = ctypes.c_void_p
            self.kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
            self.kernel32.FreeLibrary.restype = ctypes.c_int

            # LoadStringW is in user32.dll, not kernel32.dll.
            self.user32.LoadStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_int]
            self.user32.LoadStringW.restype = ctypes.c_int

    def close(self) -> None:
        if not self.is_windows:
            return
        for handle in self.handles.values():
            try:
                if handle:
                    self.kernel32.FreeLibrary(ctypes.c_void_p(handle))
            except Exception:
                pass
        self.handles.clear()

    def load_handle(self, dll_path: Path) -> int:
        if not self.is_windows:
            return 0

        dll_path = Path(dll_path)
        if dll_path in self.handles:
            return self.handles[dll_path]

        handle = self.kernel32.LoadLibraryExW(str(dll_path), None, LOAD_LIBRARY_FLAGS)
        if not handle:
            handle = self.kernel32.LoadLibraryExW(str(dll_path), None, LOAD_LIBRARY_AS_DATAFILE)

        self.handles[dll_path] = int(handle or 0)
        return int(handle or 0)

    def load_string(self, dll_path: Path, string_id: int) -> str:
        string_id = int(string_id or 0)
        if string_id <= 0:
            return ""

        cache_key = (str(dll_path).lower(), string_id)
        if cache_key in self.cache:
            return self.cache[cache_key]

        result = ""

        if self.is_windows:
            handle = self.load_handle(dll_path)
            if handle:
                size = 65535
                buffer = ctypes.create_unicode_buffer(size)
                try:
                    length = self.user32.LoadStringW(ctypes.c_void_p(handle), string_id, buffer, size)
                    if length > 0:
                        result = buffer.value[:length]
                except Exception:
                    result = ""

        self.cache[cache_key] = result
        return result

    def candidate_pairs(self, ids_value: int) -> list[tuple[Path, int, str]]:
        ids_value = int(ids_value or 0)
        if ids_value <= 0:
            return []

        high = ids_value // 65536
        low = ids_value % 65536

        pairs: list[tuple[Path, int, str]] = []
        seen: set[tuple[str, int]] = set()

        def add(dll_path: Path, string_id: int, source: str) -> None:
            if not dll_path or string_id <= 0:
                return
            key = (str(dll_path).lower(), int(string_id))
            if key in seen:
                return
            seen.add(key)
            pairs.append((dll_path, int(string_id), source))

        # Freelancer usually uses high word as DLL index, low word as string id.
        # Try 0-based, 1-based and nearby variants because mods/tools differ.
        for index in (high, high - 1, high + 1):
            if 0 <= index < len(self.ordered_dlls):
                add(self.ordered_dlls[index], low, f"ordered[{index}]:low")
            if 0 <= index < len(self.all_dlls):
                add(self.all_dlls[index], low, f"all[{index}]:low")

        for dll_path in self.all_dlls:
            add(dll_path, low, "all:low")

        if ids_value != low and ids_value <= 0xFFFFFFFF:
            for dll_path in self.all_dlls:
                add(dll_path, ids_value, "all:full")

        return pairs

    def resolve(self, ids_value: Any) -> dict[str, Any]:
        ids_int = parse_int(ids_value)
        if ids_int <= 0:
            return {"ids": ids_int, "text": "", "clean_text": "", "dll_path": "", "res_id": 0, "source": ""}

        for dll_path, res_id, source in self.candidate_pairs(ids_int):
            raw = self.load_string(dll_path, res_id)
            clean = clean_resource_text(raw)
            if clean:
                return {
                    "ids": ids_int,
                    "text": raw,
                    "clean_text": clean,
                    "dll_path": str(dll_path),
                    "res_id": res_id,
                    "source": source,
                }

        return {"ids": ids_int, "text": "", "clean_text": "", "dll_path": "", "res_id": 0, "source": ""}


def infer_item_type(path: Path, section: str, values: dict[str, list[str]]) -> str:
    rel = str(path).replace("/", "\\").lower()
    section_l = section.lower()
    if "goods" in rel or section_l == "good":
        return "good"
    if "market" in rel:
        return "market"
    if "shiparch" in rel or "solararch" in rel:
        return "arch"
    if "equipment" in rel:
        return "equipment"
    return section_l or "unknown"


def infer_category(path: Path, section: str, values: dict[str, list[str]]) -> str:
    category = first(values.get("category"))
    if category:
        return category
    rel = str(path).replace("/", "\\").lower()
    if "goods" in rel:
        return "commodity"
    if "weapons" in rel:
        return "weapon"
    if "st_equip" in rel:
        return "equipment"
    if "misc_equip" in rel:
        return "equipment"
    return section.lower()


def collect_resource_items(data_dir: Path | None) -> list[dict[str, Any]]:
    if not data_dir:
        return []

    data_dir = Path(data_dir)
    if not data_dir.exists():
        return []

    skip_dirs = {"missions", "scripts", "audio", "movies"}
    interesting_keys = {
        "ids_name",
        "ids_info",
        "nickname",
        "volume",
        "mass",
        "hit_pts",
        "price",
        "item_icon",
        "icon",
        "loot_appearance",
        "da_archetype",
        "material_library",
        "category",
        "units_per_container",
        "hp_type",
        "requires_ammo",
        "ammo_limit",
        "hold_size",
    }

    result: list[dict[str, Any]] = []

    for path in data_dir.rglob("*.ini"):
        if any(part.lower() in skip_dirs for part in path.parts):
            continue

        try:
            rel_path = str(path.relative_to(data_dir))
        except ValueError:
            rel_path = str(path)

        try:
            sections = iter_ini_sections(path)
        except Exception:
            continue

        for section, values in sections:
            nickname = first(values.get("nickname"))
            ids_name = parse_int(first(values.get("ids_name")))
            ids_info = parse_int(first(values.get("ids_info")))

            if not nickname and not ids_name and not ids_info:
                continue

            icon = (
                first(values.get("icon"))
                or first(values.get("item_icon"))
                or first(values.get("loot_appearance"))
                or first(values.get("da_archetype"))
            )

            raw = {k: v for k, v in values.items() if k in interesting_keys}
            result.append(
                {
                    "nickname": nickname or f"{rel_path}:{section}:{ids_name}:{ids_info}",
                    "source_file": rel_path,
                    "section": section,
                    "item_type": infer_item_type(path, section, values),
                    "category": infer_category(path, section, values),
                    "ids_name": ids_name,
                    "ids_info": ids_info,
                    "price": numeric_text(first(values.get("price"))),
                    "volume": parse_float(first(values.get("volume"))),
                    "mass": parse_float(first(values.get("mass"))),
                    "hit_pts": numeric_text(first(values.get("hit_pts"))),
                    "icon": icon,
                    "raw_json": json.dumps(raw, ensure_ascii=False),
                }
            )

    return result


def update_resource_cache(conn: sqlite3.Connection, result: dict[str, Any]) -> None:
    ids_value = int(result.get("ids") or 0)
    if ids_value <= 0:
        return

    ids_key = str(ids_value)

    conn.execute(
        """
        INSERT INTO resource_strings
        (ids, text, clean_text, dll_path, resource_id, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ids)
        DO UPDATE SET
            text = excluded.text,
            clean_text = excluded.clean_text,
            dll_path = excluded.dll_path,
            resource_id = excluded.resource_id,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            ids_key,
            clean_value(result.get("text")),
            clean_value(result.get("clean_text")),
            clean_value(result.get("dll_path")),
            str(int(result.get("res_id") or 0)) if int(result.get("res_id") or 0) > 0 else "",
            clean_value(result.get("source")),
            now_iso(),
        ),
    )


def should_update_name(text: str) -> bool:
    text = clean_value(text)
    if not text:
        return False
    if text.startswith("[") and text.endswith("]"):
        return False
    if len(text) > 160:
        return False
    return True


def write_meta(conn: sqlite3.Connection, **values: Any) -> None:
    for key, value in values.items():
        conn.execute(
            """
            INSERT INTO resource_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (str(key), str(value)),
        )


def store_dlls(conn: sqlite3.Connection, resolver: ResourceResolver) -> None:
    conn.execute("DELETE FROM resource_dlls")
    now = now_iso()

    for index, path in enumerate(resolver.ordered_dlls):
        conn.execute(
            """
            INSERT OR REPLACE INTO resource_dlls
            (load_order, dll_path, dll_name, source, exists_flag, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (index, str(path), path.name, "freelancer.ini", 1 if path.exists() else 0, now),
        )

    offset = len(resolver.ordered_dlls)
    for index, path in enumerate(resolver.extra_dlls):
        conn.execute(
            """
            INSERT OR REPLACE INTO resource_dlls
            (load_order, dll_path, dll_name, source, exists_flag, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (offset + index, str(path), path.name, "exe_scan", 1 if path.exists() else 0, now),
        )


def sync_fl_resources(
    exe_dir: Path,
    data_dir: Path | None = None,
    db_path: Path = RESOURCE_DB_PATH,
    *,
    limit: int = 0,
) -> dict[str, Any]:
    started = now_iso()
    conn = connect_resource_db(db_path)
    resolver = ResourceResolver(Path(exe_dir))

    stats: dict[str, Any] = {
        "exe_dir": str(Path(exe_dir)),
        "data_dir": str(Path(data_dir)) if data_dir else "",
        "db_path": str(Path(db_path)),
        "freelancer_ini": str(resolver.freelancer_ini) if resolver.freelancer_ini else "",
        "ordered_dlls": len(resolver.ordered_dlls),
        "extra_dlls": len(resolver.extra_dlls),
        "windows_api": resolver.is_windows,
        "items_total": 0,
        "ids_name_resolved": 0,
        "ids_info_resolved": 0,
        "errors": [],
    }

    log_id = None

    try:
        cur = conn.execute(
            """
            INSERT INTO resource_sync_log
            (started_at, exe_dir, data_dir, db_path, errors_json)
            VALUES (?, ?, ?, ?, '[]')
            """,
            (started, stats["exe_dir"], stats["data_dir"], stats["db_path"]),
        )
        log_id = int(cur.lastrowid)

        write_meta(
            conn,
            last_sync_started=started,
            exe_dir=stats["exe_dir"],
            data_dir=stats["data_dir"],
            freelancer_ini=stats["freelancer_ini"],
            windows_api=str(stats["windows_api"]),
        )
        store_dlls(conn, resolver)

        items = collect_resource_items(data_dir)
        if limit and limit > 0:
            items = items[:limit]

        stats["items_total"] = len(items)

        now = now_iso()

        for item in items:
            ids_name = int(item.get("ids_name") or 0)
            ids_info = int(item.get("ids_info") or 0)
            display_name = ""
            description = ""

            if ids_name > 0:
                name_result = resolver.resolve(ids_name)
                update_resource_cache(conn, name_result)
                name_text = clean_value(name_result.get("clean_text"))
                if should_update_name(name_text):
                    display_name = name_text
                    stats["ids_name_resolved"] += 1

            if ids_info > 0:
                info_result = resolver.resolve(ids_info)
                update_resource_cache(conn, info_result)
                info_text = clean_value(info_result.get("clean_text"))
                if info_text:
                    description = info_text
                    stats["ids_info_resolved"] += 1

            try:
                conn.execute(
                    """
                    INSERT INTO resource_items
                (nickname, source_file, section, item_type, category, ids_name, ids_info,
                 display_name, description, price, volume, mass, hit_pts, icon, raw_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(nickname, source_file, section)
                DO UPDATE SET
                    item_type = excluded.item_type,
                    category = excluded.category,
                    ids_name = excluded.ids_name,
                    ids_info = excluded.ids_info,
                    display_name = COALESCE(NULLIF(excluded.display_name, ''), resource_items.display_name),
                    description = COALESCE(NULLIF(excluded.description, ''), resource_items.description),
                    price = excluded.price,
                    volume = excluded.volume,
                    mass = excluded.mass,
                    hit_pts = excluded.hit_pts,
                    icon = excluded.icon,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_value(item.get("nickname")),
                    clean_value(item.get("source_file")),
                    clean_value(item.get("section")),
                    clean_value(item.get("item_type")),
                    clean_value(item.get("category")),
                    str(ids_name) if ids_name > 0 else "",
                    str(ids_info) if ids_info > 0 else "",
                    display_name,
                    description,
                    numeric_text(item.get("price")),
                    float(item.get("volume") or 0),
                    float(item.get("mass") or 0),
                    numeric_text(item.get("hit_pts")),
                    clean_value(item.get("icon")),
                    clean_value(item.get("raw_json")),
                    now,
                ),
            )
            except Exception as row_exc:
                stats["errors"].append(
                    f"row skipped {clean_value(item.get('source_file'))} :: {clean_value(item.get('nickname'))}: {row_exc}"
                )
                continue

        finished = now_iso()
        if log_id is not None:
            conn.execute(
                """
                UPDATE resource_sync_log
                SET finished_at = ?,
                    items_total = ?,
                    ids_name_resolved = ?,
                    ids_info_resolved = ?,
                    errors_json = ?
                WHERE id = ?
                """,
                (
                    finished,
                    stats["items_total"],
                    stats["ids_name_resolved"],
                    stats["ids_info_resolved"],
                    json.dumps(stats["errors"], ensure_ascii=False),
                    log_id,
                ),
            )

        write_meta(
            conn,
            last_sync_finished=finished,
            items_total=stats["items_total"],
            ids_name_resolved=stats["ids_name_resolved"],
            ids_info_resolved=stats["ids_info_resolved"],
        )
        conn.commit()

    except Exception as exc:
        conn.rollback()
        stats["errors"].append(str(exc))
        try:
            if log_id is not None:
                conn.execute(
                    "UPDATE resource_sync_log SET finished_at=?, errors_json=? WHERE id=?",
                    (now_iso(), json.dumps(stats["errors"], ensure_ascii=False), log_id),
                )
                conn.commit()
        except Exception:
            pass

    finally:
        resolver.close()
        conn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Freelancer EXE/DATA resource importer")
    parser.add_argument("--exe", required=True, type=Path, help="Путь к папке Freelancer\\EXE")
    parser.add_argument("--data", default="", type=Path, help="Путь к папке Freelancer\\DATA")
    parser.add_argument("--db", default=str(RESOURCE_DB_PATH), type=Path, help="Отдельная БД ресурсов, по умолчанию fl_panel/data/fl_resources.db")
    parser.add_argument("--limit", default=0, type=int, help="Ограничить количество item records для теста")
    args = parser.parse_args()

    stats = sync_fl_resources(args.exe, args.data if str(args.data) else None, args.db, limit=args.limit)

    print("Standalone Freelancer resource DB sync")
    for key, value in stats.items():
        if key == "errors":
            continue
        print(f"{key}: {value}")
    if stats.get("errors"):
        print("ERRORS:")
        for error in stats["errors"]:
            print(f"- {error}")


if __name__ == "__main__":
    main()
