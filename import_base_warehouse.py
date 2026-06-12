from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_warehouse_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
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
            UNIQUE(account_id, location_hash, item_hash)
        );
        """
    )


def row_value(row, key, default=""):
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        return default


def resolve_item(conn: sqlite3.Connection, token: str) -> dict:
    token = str(token or "").strip()

    item = conn.execute(
        """
        SELECT hash, nickname, good_nickname, equipment_nickname, display_name, category, volume, mass
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
        return {
            "hash": row_value(item, "hash", token),
            "nickname": row_value(item, "nickname", token),
            "display_name": row_value(item, "display_name", "") or row_value(item, "nickname", token),
            "category": row_value(item, "category", "craft"),
            "volume": float(row_value(item, "volume", 0) or 0),
            "mass": float(row_value(item, "mass", 0) or 0),
        }

    mapped = conn.execute(
        """
        SELECT hash, nickname, display_name, category
        FROM name_map
        WHERE token = ? OR lower(token) = lower(?)
        LIMIT 1
        """,
        (token, token),
    ).fetchone()

    if mapped:
        return {
            "hash": row_value(mapped, "hash", token) or token,
            "nickname": row_value(mapped, "nickname", token) or token,
            "display_name": row_value(mapped, "display_name", "") or token,
            "category": row_value(mapped, "category", "craft"),
            "volume": 0.0,
            "mass": 0.0,
        }

    return {
        "hash": token,
        "nickname": token,
        "display_name": token,
        "category": "unknown",
        "volume": 0.0,
        "mass": 0.0,
    }


def import_warehouse(db_path: Path, json_path: Path, account_id: str | None, location_hash: str | None, location_name: str | None) -> None:
    data = json.loads(json_path.read_text(encoding="utf-8"))

    account_id = account_id or data.get("account_id")
    location_hash = location_hash or data.get("location_hash")
    location_name = location_name or data.get("location_name")
    location_type = data.get("location_type") or "base"

    if not account_id or str(account_id).startswith("CHANGE_ME"):
        raise SystemExit("Укажи --account-id")
    if not location_hash or str(location_hash).startswith("CHANGE_ME"):
        raise SystemExit("Укажи --location-hash")
    if not location_name or str(location_name).startswith("CHANGE_ME"):
        raise SystemExit("Укажи --location-name")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_warehouse_schema(conn)

    ts = now_iso()
    count = 0

    try:
        for entry in data.get("items", []):
            token = str(entry.get("item") or entry.get("item_hash") or "").strip()
            quantity = int(entry.get("quantity") or 0)

            if not token or quantity <= 0:
                continue

            item = resolve_item(conn, token)

            conn.execute(
                """
                INSERT INTO warehouses
                (account_id, location_hash, location_type, location_name, item_hash, item_nickname,
                 item_display_name, category, volume, mass, quantity, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, location_hash, item_hash)
                DO UPDATE SET
                    quantity = excluded.quantity,
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
                    location_hash,
                    location_type,
                    location_name,
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
            count += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"OK: imported {count} warehouse items")
    print(f"account_id={account_id}")
    print(f"location_hash={location_hash}")
    print(f"location_name={location_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import base warehouse seed into flpanel SQLite DB")
    parser.add_argument("--db", default="fl_panel/data/flpanel.db", help="Путь к flpanel.db")
    parser.add_argument("--json", default="base_warehouse_full.json", help="Путь к JSON склада")
    parser.add_argument("--account-id", default="", help="ID аккаунта, например 23-xxxx")
    parser.add_argument("--location-hash", default="", help="Код/ник базы из панели")
    parser.add_argument("--location-name", default="", help="Название базы для отображения")
    args = parser.parse_args()

    import_warehouse(
        Path(args.db),
        Path(args.json),
        args.account_id or None,
        args.location_hash or None,
        args.location_name or None,
    )


if __name__ == "__main__":
    main()
