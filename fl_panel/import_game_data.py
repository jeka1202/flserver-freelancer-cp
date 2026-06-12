from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from .config import DATA_FILES
from .db import connect, init_db
from .fl_hash import nickname_hash
from .fl_ini_parser import first, iter_ini_sections, to_float, to_int
from .ioncross_db import load_name_lookup, sync_ioncross_names


EQUIP_FILES = {
    "engine_equip.ini",
    "event_equip.ini",
    "light_equip.ini",
    "misc_equip.ini",
    "prop_equip.ini",
    "select_equip.ini",
    "st_equip.ini",
    "weapon_equip.ini",
}

GOOD_FILES = {
    "goods.ini",
    "engine_good.ini",
    "event_good.ini",
    "misc_good.ini",
    "st_good.ini",
    "weapon_good.ini",
}

IONCROSS_LINE_RE = re.compile(r"^\s*([^=]+?)\s*=\s*([^,\n\r]+)\s*(?:,\s*(.*?))?\s*$")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def find_data_dir(root: Path) -> Path:
    root = root.resolve()

    if (root / "DATA").exists():
        return root / "DATA"

    if root.name.upper() == "DATA":
        return root

    raise SystemExit(f"Не найдена папка DATA рядом с: {root}")


def find_ioncross_dir(root: Path, data_dir: Path) -> Path | None:
    root = root.resolve()
    candidates = []

    if root.name.upper() == "IONCROSS":
        candidates.append(root)

    candidates.extend([
        root / "IONCROSS",
        data_dir.parent / "IONCROSS",
        Path(__file__).resolve().parent.parent / "IONCROSS",
    ])

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def ioncross_category_from_filename(path: Path) -> str:
    stem = path.stem
    return stem.removeprefix("GAMEDATA_")


def parse_ioncross_file(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    category = ioncross_category_from_filename(path)

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue

        # GAMEDATA_mapinfo.txt contains lines like: visit = 552, 65.
        # These are map markers, not human-readable item names.
        if path.name.lower() == "gamedata_mapinfo.txt":
            continue

        match = IONCROSS_LINE_RE.match(line)
        if not match:
            continue

        code = match.group(1).strip()
        nickname = match.group(2).strip()
        display_name = (match.group(3) or "").strip() or nickname

        if not code or not nickname:
            continue

        entries.append({
            "hash": code,
            "nickname": nickname,
            "display_name": display_name,
            "category": category,
            "source_file": path.name,
        })

    return entries


def load_ioncross_names(ioncross_dir: Path | None) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    """Load hash/nickname -> display name maps from IONCROSS/GAMEDATA_*.txt."""
    by_token: dict[str, dict[str, str]] = {}
    entries: list[dict[str, str]] = []

    if not ioncross_dir:
        return by_token, entries

    files = []
    for filename in DATA_FILES.values():
        path = ioncross_dir / filename
        if path.exists():
            files.append(path)

    # Also accept extra GAMEDATA_*.txt files if they exist.
    known = {path.name.lower() for path in files}
    for path in sorted(ioncross_dir.glob("GAMEDATA_*.txt")):
        if path.name.lower() not in known:
            files.append(path)

    for path in files:
        for entry in parse_ioncross_file(path):
            entries.append(entry)
            tokens = {
                entry["hash"],
                entry["nickname"],
                entry["hash"].lower(),
                entry["nickname"].lower(),
            }
            for token in tokens:
                by_token[token] = entry

    return by_token, entries


def display_name_for(names: dict[str, dict[str, str]], *tokens: str) -> str:
    for token in tokens:
        token = str(token or "").strip()
        if not token:
            continue
        entry = names.get(token) or names.get(token.lower())
        if entry and entry.get("display_name"):
            return entry["display_name"]
    return ""


def import_name_map(conn, entries: list[dict[str, str]]) -> int:
    conn.execute("DELETE FROM name_map")
    count = 0

    for entry in entries:
        tokens = {entry["hash"], entry["nickname"], entry["nickname"].lower()}
        for token in tokens:
            conn.execute(
                """
                INSERT OR REPLACE INTO name_map
                (token, hash, nickname, display_name, category, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    entry["hash"],
                    entry["nickname"],
                    entry["display_name"],
                    entry["category"],
                    entry["source_file"],
                ),
            )
            count += 1

    conn.commit()
    return count


def import_ships(conn, data_dir: Path, names: dict[str, dict[str, str]]) -> int:
    path = data_dir / "SHIPS" / "shiparch.ini"
    if not path.exists():
        print(f"WARNING: нет файла {path}")
        return 0

    count = 0
    for section, values in iter_ini_sections(path):
        if section.lower() != "ship":
            continue

        nickname = first(values, "nickname")
        if not nickname:
            continue

        ship_hash = nickname_hash(nickname)
        display_name = display_name_for(names, ship_hash, nickname) or nickname

        conn.execute(
            """
            INSERT OR REPLACE INTO ships
            (hash, nickname, display_name, ship_type, hold_size, nanobot_limit, shield_battery_limit, mass, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ship_hash,
                nickname,
                display_name,
                first(values, "type"),
                to_int(first(values, "hold_size")),
                to_int(first(values, "nanobot_limit")),
                to_int(first(values, "shield_battery_limit")),
                to_float(first(values, "mass")),
                str(path.relative_to(data_dir)),
            ),
        )
        count += 1

    conn.commit()
    return count


def import_items(conn, data_dir: Path, names: dict[str, dict[str, str]]) -> int:
    equipment_dir = data_dir / "EQUIPMENT"
    if not equipment_dir.exists():
        print(f"WARNING: нет папки {equipment_dir}")
        return 0

    equip_by_nickname: dict[str, dict[str, Any]] = {}

    for filename in EQUIP_FILES:
        path = equipment_dir / filename
        if not path.exists():
            continue

        for section, values in iter_ini_sections(path):
            nickname = first(values, "nickname")
            if not nickname:
                continue

            equip_by_nickname[nickname] = {
                "equipment_nickname": nickname,
                "section": section,
                "volume": to_float(first(values, "volume")),
                "mass": to_float(first(values, "mass")),
                "units_per_container": to_int(first(values, "units_per_container"), 1),
                "source_equip_file": str(path.relative_to(data_dir)),
            }

    good_count = 0

    for filename in GOOD_FILES:
        path = equipment_dir / filename
        if not path.exists():
            continue

        for section, values in iter_ini_sections(path):
            if section.lower() != "good":
                continue

            good_nickname = first(values, "nickname")
            equipment_nickname = first(values, "equipment") or good_nickname
            category = first(values, "category")
            if not good_nickname:
                continue

            equip = equip_by_nickname.get(equipment_nickname, {})
            item_hash = nickname_hash(equipment_nickname)
            good_hash = nickname_hash(good_nickname)
            display_name = (
                display_name_for(names, item_hash, good_hash, equipment_nickname, good_nickname)
                or equipment_nickname
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO items
                (hash, nickname, good_nickname, equipment_nickname, category, section,
                 display_name, volume, mass, units_per_container, source_good_file, source_equip_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_hash,
                    equipment_nickname,
                    good_nickname,
                    equipment_nickname,
                    category,
                    equip.get("section", ""),
                    display_name,
                    float(equip.get("volume", 0.0)),
                    float(equip.get("mass", 0.0)),
                    int(equip.get("units_per_container", 1) or 1),
                    str(path.relative_to(data_dir)),
                    equip.get("source_equip_file", ""),
                ),
            )
            good_count += 1

    conn.commit()
    return good_count


def import_locations(conn, data_dir: Path, names: dict[str, dict[str, str]]) -> int:
    universe = data_dir / "UNIVERSE"
    if not universe.exists():
        return 0

    count = 0

    for path in universe.rglob("*.ini"):
        current_system = ""

        for section, values in iter_ini_sections(path):
            lower = section.lower()

            if lower == "system":
                current_system = first(values, "nickname")
                if current_system:
                    system_hash = nickname_hash(current_system)
                    display_name = display_name_for(names, system_hash, current_system) or current_system
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO locations
                        (hash, nickname, location_type, system_nickname, display_name, source_file)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            system_hash,
                            current_system,
                            "system",
                            current_system,
                            display_name,
                            str(path.relative_to(data_dir)),
                        ),
                    )
                    count += 1

            if lower in {"base", "object"}:
                nickname = first(values, "nickname")
                archetype = first(values, "archetype")
                base = first(values, "base")
                if not nickname:
                    continue

                location_type = "base" if lower == "base" or base else "object"
                loc_hash = nickname_hash(nickname)
                display_name = display_name_for(names, loc_hash, nickname, base, archetype) or base or archetype or nickname

                conn.execute(
                    """
                    INSERT OR REPLACE INTO locations
                    (hash, nickname, location_type, system_nickname, display_name, source_file)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        loc_hash,
                        nickname,
                        location_type,
                        current_system,
                        display_name,
                        str(path.relative_to(data_dir)),
                    ),
                )
                count += 1

    conn.commit()
    return count


def apply_ioncross_names(conn, entries: list[dict[str, str]]) -> int:
    """Update display names for rows already imported before this patch."""
    updates = 0

    for entry in entries:
        tokens = {entry["hash"], entry["nickname"], entry["nickname"].lower()}
        for token in tokens:
            for table in ("items", "ships", "locations"):
                if table == "items":
                    cursor = conn.execute(
                        """
                        UPDATE items
                        SET display_name = ?
                        WHERE hash = ?
                           OR lower(nickname) = ?
                           OR lower(good_nickname) = ?
                           OR lower(equipment_nickname) = ?
                        """,
                        (entry["display_name"], token, token.lower(), token.lower(), token.lower()),
                    )
                else:
                    cursor = conn.execute(
                        f"""
                        UPDATE {table}
                        SET display_name = ?
                        WHERE hash = ? OR lower(nickname) = ?
                        """,
                        (entry["display_name"], token, token.lower()),
                    )
                updates += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    conn.commit()
    return updates


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Freelancer DATA to flpanel SQLite DB")
    parser.add_argument("--root", default=".", help="Корень проекта или путь к папке DATA")
    parser.add_argument("--ioncross", default="", help="Путь к папке IONCROSS, если нужен нестандартный")
    parser.add_argument("--db", default="", help="Путь к SQLite DB, если нужен нестандартный")
    args = parser.parse_args()

    root = Path(args.root)
    data_dir = find_data_dir(root)
    ioncross_dir = Path(args.ioncross).resolve() if args.ioncross else find_ioncross_dir(root, data_dir)

    conn = connect(Path(args.db) if args.db else None) if args.db else connect()
    init_db(conn)

    print(f"DATA: {data_dir}")
    print(f"IONCROSS: {ioncross_dir if ioncross_dir else 'не найдено'}")

    print("Syncing IONCROSS DB...")
    sync_stats = sync_ioncross_names(ioncross_dir, root=root, force=True, conn=conn)
    names = load_name_lookup(conn)
    name_entries = []
    name_rows = int(sync_stats.get("token_rows", 0))

    print("Importing ships...")
    ships = import_ships(conn, data_dir, names)

    print("Importing items...")
    items = import_items(conn, data_dir, names)

    print("Importing locations...")
    locations = import_locations(conn, data_dir, names)

    print("Applying IONCROSS display names...")
    from .ioncross_db import apply_ioncross_display_names, refresh_technical_ship_names, make_dsy_ship_aliases
    aliases_added = make_dsy_ship_aliases(conn)
    name_updates = apply_ioncross_display_names(conn)
    name_updates += refresh_technical_ship_names(conn)

    print("OK")
    print(f"ships={ships}")
    print(f"items={items}")
    print(f"locations={locations}")
    print(f"ioncross_names={sync_stats.get('entries_imported', 0)}")
    print(f"name_map_rows={name_rows}")
    print(f"name_updates={name_updates}")
    print("DB:", conn.execute("PRAGMA database_list").fetchone()[2])


if __name__ == "__main__":
    main()
