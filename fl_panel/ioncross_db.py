from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DATA_FILES, IONCROSS_DIR, ROOT
from .db import connect, init_db


IONCROSS_LINE_RE = re.compile(r"^\s*([^=]+?)\s*=\s*([^,\n\r]+)\s*(?:,\s*(.*?))?\s*$")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ioncross_category_from_filename(path: Path) -> str:
    return path.stem.removeprefix("GAMEDATA_")


def parse_ioncross_file(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    category = ioncross_category_from_filename(path)

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue

        # GAMEDATA_mapinfo.txt contains lines like "visit = 552, 65";
        # this is not a readable object dictionary.
        if path.name.lower() == "gamedata_mapinfo.txt":
            continue

        match = IONCROSS_LINE_RE.match(line)
        if not match:
            continue

        hash_code = match.group(1).strip()
        nickname = match.group(2).strip()
        display_name = (match.group(3) or "").strip() or nickname

        if not hash_code or not nickname:
            continue

        entries.append({
            "hash": hash_code,
            "nickname": nickname,
            "display_name": display_name,
            "category": category,
            "source_file": path.name,
        })

    return entries


def find_ioncross_dir(root: Path | None = None, explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []

    if explicit:
        candidates.append(explicit)

    root = (root or ROOT).resolve()

    if root.name.upper() == "IONCROSS":
        candidates.append(root)

    candidates.extend([
        root / "IONCROSS",
        IONCROSS_DIR,
        Path(__file__).resolve().parent.parent / "IONCROSS",
    ])

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

    return None


def iter_ioncross_files(ioncross_dir: Path) -> list[Path]:
    files: list[Path] = []

    for filename in DATA_FILES.values():
        path = ioncross_dir / filename
        if path.exists() and path.is_file():
            files.append(path)

    known = {path.name.lower() for path in files}
    for path in sorted(ioncross_dir.glob("GAMEDATA_*.txt")):
        if path.is_file() and path.name.lower() not in known:
            files.append(path)

    return files


def make_file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "source_file": path.name,
        "path": str(path),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": file_sha256(path),
    }


def upsert_name_tokens(conn: sqlite3.Connection, entry: dict[str, str]) -> int:
    tokens = {
        entry["hash"],
        entry["hash"].lower(),
        entry["nickname"],
        entry["nickname"].lower(),
    }

    count = 0
    for token in tokens:
        if not token:
            continue
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

    return count


def import_one_ioncross_file(conn: sqlite3.Connection, path: Path, signature: dict[str, Any]) -> dict[str, int]:
    entries = parse_ioncross_file(path)

    conn.execute("DELETE FROM ioncross_entries WHERE source_file = ?", (path.name,))
    conn.execute("DELETE FROM name_map WHERE source_file = ?", (path.name,))

    token_rows = 0
    for entry in entries:
        conn.execute(
            """
            INSERT INTO ioncross_entries
            (source_file, hash, nickname, display_name, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry["source_file"],
                entry["hash"],
                entry["nickname"],
                entry["display_name"],
                entry["category"],
            ),
        )
        token_rows += upsert_name_tokens(conn, entry)

    conn.execute(
        """
        INSERT OR REPLACE INTO ioncross_sources
        (source_file, path, size, mtime_ns, sha256, rows_count, imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path.name,
            str(path),
            signature["size"],
            signature["mtime_ns"],
            signature["sha256"],
            len(entries),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    return {
        "entries": len(entries),
        "tokens": token_rows,
    }


def load_name_lookup(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = conn.execute(
        """
        SELECT token, hash, nickname, display_name, category, source_file
        FROM name_map
        """
    ).fetchall()

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        entry = {
            "hash": row["hash"] or "",
            "nickname": row["nickname"] or "",
            "display_name": row["display_name"] or "",
            "category": row["category"] or "",
            "source_file": row["source_file"] or "",
        }
        token = str(row["token"] or "")
        if token:
            result[token] = entry
            result[token.lower()] = entry

    return result


def display_name_for(names: dict[str, dict[str, str]], *tokens: str) -> str:
    for token in tokens:
        token = str(token or "").strip()
        if not token:
            continue
        entry = names.get(token) or names.get(token.lower())
        if entry and entry.get("display_name"):
            return entry["display_name"]
    return ""


def apply_ioncross_display_names(conn: sqlite3.Connection) -> int:
    """Refresh display_name fields in imported DATA tables from name_map."""
    rows = conn.execute(
        """
        SELECT DISTINCT hash, nickname, display_name
        FROM name_map
        WHERE display_name IS NOT NULL AND display_name != ''
        """
    ).fetchall()

    updates = 0
    for row in rows:
        hash_code = str(row["hash"] or "")
        nickname = str(row["nickname"] or "")
        display_name = str(row["display_name"] or "")
        nickname_lower = nickname.lower()

        if not display_name:
            continue

        cursor = conn.execute(
            """
            UPDATE items
            SET display_name = ?
            WHERE hash = ?
               OR lower(nickname) = ?
               OR lower(good_nickname) = ?
               OR lower(equipment_nickname) = ?
            """,
            (display_name, hash_code, nickname_lower, nickname_lower, nickname_lower),
        )
        updates += max(cursor.rowcount or 0, 0)

        cursor = conn.execute(
            """
            UPDATE ships
            SET display_name = ?
            WHERE hash = ? OR lower(nickname) = ?
            """,
            (display_name, hash_code, nickname_lower),
        )
        updates += max(cursor.rowcount or 0, 0)

        cursor = conn.execute(
            """
            UPDATE locations
            SET display_name = ?
            WHERE hash = ? OR lower(nickname) = ?
            """,
            (display_name, hash_code, nickname_lower),
        )
        updates += max(cursor.rowcount or 0, 0)

    return updates





def make_dsy_ship_aliases(conn: sqlite3.Connection) -> int:
    """Map saved ship nickname like ku_gunboat to IONCROSS dsy_ku_gunboat.

    In .fl account files many ships are stored without the Discovery dsy_ prefix,
    while IONCROSS GAMEDATA ships often contain the same nickname with dsy_.
    This function stores that relation in ioncross_aliases and name_map, so UI
    and cargo services can resolve human names without showing technical ids.
    """
    conn.execute("DELETE FROM ioncross_aliases WHERE alias_type = 'ship_dsy_prefix'")

    rows = conn.execute(
        """
        SELECT token, hash, nickname, display_name, category, source_file
        FROM name_map
        WHERE lower(nickname) LIKE 'dsy_%'
           OR lower(token) LIKE 'dsy_%'
        """
    ).fetchall()

    aliases_added = 0

    for row in rows:
        target_nickname = str(row["nickname"] or row["token"] or "").strip()
        if not target_nickname:
            continue

        target_lower = target_nickname.lower()
        if not target_lower.startswith("dsy_"):
            token = str(row["token"] or "").strip()
            if token.lower().startswith("dsy_"):
                target_nickname = token
                target_lower = token.lower()
            else:
                continue

        alias_nickname = target_nickname[4:]
        display_name = str(row["display_name"] or "").strip()
        hash_code = str(row["hash"] or "").strip()
        category = str(row["category"] or "").strip()
        source_file = str(row["source_file"] or "").strip()

        if not alias_nickname or not display_name:
            continue

        # This table is the explicit mark in DB that alias_nickname maps to dsy_*.
        conn.execute(
            """
            INSERT OR REPLACE INTO ioncross_aliases
            (alias_token, target_token, hash, nickname, display_name, category, alias_type, source_file, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alias_nickname,
                target_nickname,
                hash_code,
                target_nickname,
                display_name,
                category,
                "ship_dsy_prefix",
                source_file,
                "Ship nickname in account file has no dsy_ prefix; IONCROSS uses dsy_ prefix.",
            ),
        )

        # Add alias token to name_map so regular lookup by ku_gunboat works.
        # Keep nickname as original IONCROSS nickname with dsy_ so technical mapping is not lost.
        for token in {alias_nickname, alias_nickname.lower()}:
            conn.execute(
                """
                INSERT OR REPLACE INTO name_map
                (token, hash, nickname, display_name, category, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    hash_code,
                    target_nickname,
                    display_name,
                    category or "ship_alias",
                    source_file,
                ),
            )
            aliases_added += 1

    return aliases_added



def refresh_technical_ship_names(conn: sqlite3.Connection) -> int:
    """For any ship still displayed as a technical nickname, try name_map again."""
    rows = conn.execute(
        """
        SELECT hash, nickname, display_name
        FROM ships
        """
    ).fetchall()

    updates = 0
    for row in rows:
        current = str(row["display_name"] or "")
        nickname = str(row["nickname"] or "")
        hash_code = str(row["hash"] or "")

        if current and "_" not in current and not current.isdigit():
            continue

        mapped = conn.execute(
            """
            SELECT display_name
            FROM name_map
            WHERE token = ?
               OR lower(token) = lower(?)
               OR lower(token) = lower(?)
               OR token = ?
               OR lower(nickname) = lower(?)
               OR lower(nickname) = lower(?)
               OR hash = ?
            LIMIT 1
            """,
            (hash_code, nickname, "dsy_" + nickname, nickname, nickname, "dsy_" + nickname, hash_code),
        ).fetchone()

        if not mapped:
            continue

        display_name = str(mapped["display_name"] or "").strip()
        if not display_name or "_" in display_name or display_name.isdigit():
            continue

        cursor = conn.execute(
            "UPDATE ships SET display_name = ? WHERE hash = ? OR lower(nickname) = lower(?)",
            (display_name, hash_code, nickname),
        )
        updates += max(cursor.rowcount or 0, 0)

    return updates


def sync_ioncross_names(
    ioncross_dir: Path | str | None = None,
    *,
    root: Path | str | None = None,
    force: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Sync IONCROSS/GAMEDATA_*.txt into SQLite tables.

    The sync is incremental: unchanged files are skipped by size, mtime and sha256.
    """
    own_conn = conn is None
    conn = conn or connect()
    init_db(conn)

    resolved_dir = find_ioncross_dir(
        Path(root) if root else ROOT,
        Path(ioncross_dir) if ioncross_dir else None,
    )

    stats: dict[str, Any] = {
        "ioncross_dir": str(resolved_dir) if resolved_dir else "",
        "found": bool(resolved_dir),
        "files_total": 0,
        "files_changed": 0,
        "files_skipped": 0,
        "files_removed": 0,
        "entries_imported": 0,
        "entries_total": 0,
        "name_map_total": 0,
        "token_rows": 0,
        "display_updates": 0,
        "aliases_added": 0,
    }

    if not resolved_dir:
        if own_conn:
            conn.close()
        return stats

    files = iter_ioncross_files(resolved_dir)
    stats["files_total"] = len(files)
    seen_sources = {path.name for path in files}

    try:
        for path in files:
            signature = make_file_signature(path)
            existing = conn.execute(
                """
                SELECT size, mtime_ns, sha256
                FROM ioncross_sources
                WHERE source_file = ?
                """,
                (path.name,),
            ).fetchone()

            unchanged = (
                existing is not None
                and int(existing["size"] or 0) == signature["size"]
                and int(existing["mtime_ns"] or 0) == signature["mtime_ns"]
                and str(existing["sha256"] or "") == signature["sha256"]
            )

            if unchanged and not force:
                stats["files_skipped"] += 1
                continue

            imported = import_one_ioncross_file(conn, path, signature)
            stats["files_changed"] += 1
            stats["entries_imported"] += imported["entries"]
            stats["token_rows"] += imported["tokens"]

        stale_rows = conn.execute(
            "SELECT source_file FROM ioncross_sources"
        ).fetchall()

        for row in stale_rows:
            source_file = row["source_file"]
            if source_file in seen_sources:
                continue
            conn.execute("DELETE FROM ioncross_entries WHERE source_file = ?", (source_file,))
            conn.execute("DELETE FROM name_map WHERE source_file = ?", (source_file,))
            conn.execute("DELETE FROM ioncross_sources WHERE source_file = ?", (source_file,))
            stats["files_removed"] += 1

        # Always refresh alias table; it is cheap and fixes old DBs after upgrades.
        stats["aliases_added"] = make_dsy_ship_aliases(conn)

        if force or stats["files_changed"] or stats["files_removed"] or stats["aliases_added"]:
            stats["display_updates"] = apply_ioncross_display_names(conn)
            stats["display_updates"] += refresh_technical_ship_names(conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

    if conn:
        try:
            stats["entries_total"] = conn.execute("SELECT COUNT(*) FROM ioncross_entries").fetchone()[0]
            stats["name_map_total"] = conn.execute("SELECT COUNT(*) FROM name_map").fetchone()[0]
            stats["aliases_total"] = conn.execute("SELECT COUNT(*) FROM ioncross_aliases").fetchone()[0]
        except Exception:
            pass

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync IONCROSS/GAMEDATA_*.txt to flpanel SQLite DB")
    parser.add_argument("--ioncross", default="", help="Путь к папке IONCROSS")
    parser.add_argument("--root", default=".", help="Корень проекта")
    parser.add_argument("--force", action="store_true", help="Переимпортировать даже неизменённые файлы")
    args = parser.parse_args()

    stats = sync_ioncross_names(
        Path(args.ioncross) if args.ioncross else None,
        root=Path(args.root),
        force=args.force,
    )

    print("IONCROSS DB sync")
    for key, value in stats.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
