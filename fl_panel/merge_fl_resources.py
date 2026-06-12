from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import DB_PATH, connect, table_exists


DEFAULT_RESOURCES_DB = Path(__file__).resolve().parent / "data" / "fl_resources.db"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean(value: Any) -> str:
    return str(value or "").strip()


def lower(value: Any) -> str:
    return clean(value).lower()


def row_get(row: Any, key: str, default: Any = "") -> Any:
    try:
        return row[key]
    except Exception:
        return default


def connect_plain(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def looks_system_name(value: str) -> bool:
    text = clean(value)
    if not text:
        return True

    # System nicknames usually look like ge_s_cm_03_ammo / commodity_polymers.
    if "_" in text and " " not in text:
        return True

    if re.fullmatch(r"[a-z0-9_./\\-]+", text):
        return True

    if text.startswith("[") and text.endswith("]"):
        return True

    return False


def looks_good_resource_name(value: str) -> bool:
    text = clean(value)
    if not text:
        return False
    if len(text) > 160:
        return False
    if text.startswith("[") and text.endswith("]"):
        return False
    if looks_system_name(text):
        return False
    return True


def is_technical_description(value: str) -> bool:
    text = clean(value)
    if not text:
        return True

    technical_prefixes = (
        "ids_name:",
        "ids_info:",
        "volume:",
        "mass:",
        "price:",
        "hit points:",
        "hit_pts:",
    )

    lines = [line.strip().lower() for line in text.splitlines() if line.strip()]
    if not lines:
        return True

    return all(any(line.startswith(prefix) for prefix in technical_prefixes) for line in lines)


def should_update_name(current_name: str, nickname: str, new_name: str, overwrite: bool) -> bool:
    if not looks_good_resource_name(new_name):
        return False

    current_name = clean(current_name)
    nickname = clean(nickname)

    if overwrite:
        return current_name != clean(new_name)

    if not current_name:
        return True

    if current_name.lower() == nickname.lower():
        return True

    if looks_system_name(current_name):
        return True

    return False


def should_update_description(current_description: str, new_description: str, overwrite: bool) -> bool:
    new_description = clean(new_description)
    if not new_description:
        return False

    if overwrite:
        return clean(current_description) != new_description

    return is_technical_description(current_description)


def ensure_merge_schema(main_conn: sqlite3.Connection) -> None:
    main_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS resource_merge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            resources_db TEXT,
            dry_run INTEGER DEFAULT 0,
            overwrite_names INTEGER DEFAULT 0,
            overwrite_descriptions INTEGER DEFAULT 0,
            resource_rows INTEGER DEFAULT 0,
            matched_rows INTEGER DEFAULT 0,
            item_details_created INTEGER DEFAULT 0,
            name_updates INTEGER DEFAULT 0,
            description_updates INTEGER DEFAULT 0,
            ids_updates INTEGER DEFAULT 0,
            no_match_rows INTEGER DEFAULT 0,
            error_rows INTEGER DEFAULT 0,
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_resource_merge_log_created
            ON resource_merge_log(created_at);
        """
    )
    main_conn.commit()


def main_item_details_by_nickname(main_conn: sqlite3.Connection, nickname: str) -> list[sqlite3.Row]:
    if not table_exists(main_conn, "item_details"):
        return []

    return main_conn.execute(
        """
        SELECT *
        FROM item_details
        WHERE lower(nickname) = lower(?)
        """,
        (nickname,),
    ).fetchall()


def main_items_by_nickname(main_conn: sqlite3.Connection, nickname: str) -> list[sqlite3.Row]:
    if not table_exists(main_conn, "items"):
        return []

    return main_conn.execute(
        """
        SELECT *
        FROM items
        WHERE lower(nickname) = lower(?)
           OR lower(good_nickname) = lower(?)
           OR lower(equipment_nickname) = lower(?)
        """,
        (nickname, nickname, nickname),
    ).fetchall()


def ensure_item_detail_from_item(main_conn: sqlite3.Connection, item_row: sqlite3.Row, res_row: sqlite3.Row) -> str:
    item_hash = clean(row_get(item_row, "hash"))
    nickname = clean(row_get(item_row, "nickname") or row_get(item_row, "good_nickname") or row_get(item_row, "equipment_nickname") or row_get(res_row, "nickname"))

    if not item_hash:
        item_hash = nickname

    main_conn.execute(
        """
        INSERT INTO item_details
        (item_hash, nickname, display_name, description, ids_name, ids_info, source_file, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_hash)
        DO NOTHING
        """,
        (
            item_hash,
            nickname,
            clean(row_get(res_row, "display_name")),
            clean(row_get(res_row, "description")),
            clean(row_get(res_row, "ids_name")),
            clean(row_get(res_row, "ids_info")),
            f"merge:{clean(row_get(res_row, 'source_file'))}",
            now_iso(),
        ),
    )

    return item_hash


def update_name_maps(main_conn: sqlite3.Connection, item_hash: str, nickname: str, display_name: str, dry_run: bool) -> None:
    if dry_run:
        return

    if table_exists(main_conn, "items"):
        main_conn.execute(
            """
            UPDATE items
            SET display_name = ?
            WHERE hash = ?
               OR lower(nickname) = lower(?)
               OR lower(good_nickname) = lower(?)
               OR lower(equipment_nickname) = lower(?)
            """,
            (display_name, item_hash, nickname, nickname, nickname),
        )

    if table_exists(main_conn, "name_map"):
        main_conn.execute(
            """
            UPDATE name_map
            SET display_name = ?
            WHERE hash = ?
               OR lower(nickname) = lower(?)
               OR lower(token) = lower(?)
            """,
            (display_name, item_hash, nickname, nickname),
        )


def merge_resources(
    resources_db: Path,
    main_db: Path = DB_PATH,
    *,
    dry_run: bool = False,
    overwrite_names: bool = False,
    overwrite_descriptions: bool = False,
    limit: int = 0,
) -> dict[str, Any]:
    resources_db = Path(resources_db)
    main_db = Path(main_db)

    if not resources_db.exists():
        raise FileNotFoundError(f"resources DB not found: {resources_db}")

    res_conn = connect_plain(resources_db)
    main_conn = connect(main_db)
    ensure_merge_schema(main_conn)

    stats = {
        "resources_db": str(resources_db),
        "main_db": str(main_db),
        "dry_run": dry_run,
        "overwrite_names": overwrite_names,
        "overwrite_descriptions": overwrite_descriptions,
        "resource_rows": 0,
        "matched_rows": 0,
        "item_details_created": 0,
        "name_updates": 0,
        "description_updates": 0,
        "ids_updates": 0,
        "no_match_rows": 0,
        "error_rows": 0,
        "errors": [],
    }

    if not table_exists(res_conn, "resource_items"):
        res_conn.close()
        main_conn.close()
        raise RuntimeError("В resource DB нет таблицы resource_items.")

    query = """
        SELECT *
        FROM resource_items
        WHERE coalesce(nickname, '') <> ''
          AND (
              coalesce(display_name, '') <> ''
              OR coalesce(description, '') <> ''
              OR coalesce(ids_name, '') <> ''
              OR coalesce(ids_info, '') <> ''
          )
        ORDER BY nickname COLLATE NOCASE
    """

    if limit and limit > 0:
        query += f" LIMIT {int(limit)}"

    rows = res_conn.execute(query).fetchall()
    stats["resource_rows"] = len(rows)

    try:
        for res_row in rows:
            try:
                nickname = clean(row_get(res_row, "nickname"))
                if not nickname:
                    continue

                details = main_item_details_by_nickname(main_conn, nickname)
                created_now = 0

                if not details:
                    item_rows = main_items_by_nickname(main_conn, nickname)
                    for item_row in item_rows:
                        item_hash = ensure_item_detail_from_item(main_conn, item_row, res_row)
                        created_now += 1
                    if created_now:
                        stats["item_details_created"] += created_now
                        details = main_item_details_by_nickname(main_conn, nickname)

                if not details:
                    stats["no_match_rows"] += 1
                    continue

                new_name = clean(row_get(res_row, "display_name"))
                new_desc = clean(row_get(res_row, "description"))
                new_ids_name = clean(row_get(res_row, "ids_name"))
                new_ids_info = clean(row_get(res_row, "ids_info"))

                for detail in details:
                    item_hash = clean(row_get(detail, "item_hash"))
                    current_name = clean(row_get(detail, "display_name"))
                    current_desc = clean(row_get(detail, "description"))
                    current_ids_name = clean(row_get(detail, "ids_name"))
                    current_ids_info = clean(row_get(detail, "ids_info"))

                    set_parts: list[str] = []
                    params: list[Any] = []

                    name_update = should_update_name(current_name, nickname, new_name, overwrite_names)
                    desc_update = should_update_description(current_desc, new_desc, overwrite_descriptions)
                    ids_update = False

                    if name_update:
                        set_parts.append("display_name = ?")
                        params.append(new_name)

                    if desc_update:
                        set_parts.append("description = ?")
                        params.append(new_desc)

                    if new_ids_name and not current_ids_name:
                        set_parts.append("ids_name = ?")
                        params.append(new_ids_name)
                        ids_update = True

                    if new_ids_info and not current_ids_info:
                        set_parts.append("ids_info = ?")
                        params.append(new_ids_info)
                        ids_update = True

                    if not set_parts:
                        stats["matched_rows"] += 1
                        continue

                    set_parts.append("updated_at = ?")
                    params.append(now_iso())
                    params.append(item_hash)

                    if not dry_run:
                        main_conn.execute(
                            f"UPDATE item_details SET {', '.join(set_parts)} WHERE item_hash = ?",
                            params,
                        )

                    if name_update:
                        stats["name_updates"] += 1
                        update_name_maps(main_conn, item_hash, nickname, new_name, dry_run)

                    if desc_update:
                        stats["description_updates"] += 1

                    if ids_update:
                        stats["ids_updates"] += 1

                    stats["matched_rows"] += 1

            except Exception as row_exc:
                stats["error_rows"] += 1
                if len(stats["errors"]) < 20:
                    stats["errors"].append(f"{clean(row_get(res_row, 'nickname'))}: {row_exc}")

        if not dry_run:
            main_conn.execute(
                """
                INSERT INTO resource_merge_log
                (created_at, resources_db, dry_run, overwrite_names, overwrite_descriptions,
                 resource_rows, matched_rows, item_details_created, name_updates,
                 description_updates, ids_updates, no_match_rows, error_rows, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    str(resources_db),
                    0,
                    1 if overwrite_names else 0,
                    1 if overwrite_descriptions else 0,
                    stats["resource_rows"],
                    stats["matched_rows"],
                    stats["item_details_created"],
                    stats["name_updates"],
                    stats["description_updates"],
                    stats["ids_updates"],
                    stats["no_match_rows"],
                    stats["error_rows"],
                    "merge_fl_resources.py",
                ),
            )
            main_conn.commit()
        else:
            main_conn.rollback()

    except Exception:
        main_conn.rollback()
        raise
    finally:
        res_conn.close()
        main_conn.close()

    return stats


def print_stats(stats: dict[str, Any]) -> None:
    print("FL resources merge")
    for key, value in stats.items():
        if key == "errors":
            continue
        print(f"{key}: {value}")
    if stats.get("errors"):
        print("ERRORS:")
        for error in stats["errors"]:
            print(f"- {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge standalone fl_resources.db into main flpanel.db")
    parser.add_argument("--resources", required=True, type=Path, help="Путь к отдельной fl_resources.db")
    parser.add_argument("--main", default=str(DB_PATH), type=Path, help="Путь к основной flpanel.db")
    parser.add_argument("--dry-run", action="store_true", help="Только показать статистику, не писать в основную БД")
    parser.add_argument("--overwrite-names", action="store_true", help="Перезаписывать уже человеческие названия")
    parser.add_argument("--overwrite-descriptions", action="store_true", help="Перезаписывать уже существующие описания")
    parser.add_argument("--limit", default=0, type=int, help="Ограничить количество строк для теста")
    args = parser.parse_args()

    stats = merge_resources(
        args.resources,
        args.main,
        dry_run=args.dry_run,
        overwrite_names=args.overwrite_names,
        overwrite_descriptions=args.overwrite_descriptions,
        limit=args.limit,
    )
    print_stats(stats)


if __name__ == "__main__":
    main()
