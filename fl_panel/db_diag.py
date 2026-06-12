from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("fl_panel/data/flpanel.db")


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("DB:", DB)
    print()

    for table in [
        "items",
        "ships",
        "locations",
        "ioncross_entries",
        "name_map",
        "ioncross_aliases",
        "warehouses",
        "craft_recipes",
        "craft_jobs",
    ]:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            print(f"{table}: missing")
            continue
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count}")

    print()
    print("warehouses columns:")
    for row in conn.execute("PRAGMA table_info(warehouses)").fetchall():
        print(" ", row["name"], row["type"])

    conn.close()


if __name__ == "__main__":
    main()
