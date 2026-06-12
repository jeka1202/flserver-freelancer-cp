from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


DB_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DB_DIR / "flpanel.db"

_MIGRATED_DB_PATHS: set[str] = set()
_DB_MIGRATION_LOCK = threading.Lock()


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_key = str(db_path.resolve())
    first_connect = db_key not in _MIGRATED_DB_PATHS

    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # PRAGMA journal_mode and migrations are expensive on Windows if done on
    # every small warehouse operation. Do them once per process/database path.
    if first_connect:
        with _DB_MIGRATION_LOCK:
            if db_key not in _MIGRATED_DB_PATHS:
                conn.execute("PRAGMA journal_mode = WAL")
                migrate_db(conn)
                _MIGRATED_DB_PATHS.add(db_key)

    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not table_exists(conn, table_name):
        return False
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, declaration: str) -> None:
    if table_exists(conn, table_name) and not column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}")


def migrate_db(conn: sqlite3.Connection) -> None:
    """Safe migrations for already-created flpanel.db files."""
    add_column_if_missing(conn, "items", "display_name", "TEXT")
    add_column_if_missing(conn, "ships", "display_name", "TEXT")
    add_column_if_missing(conn, "locations", "display_name", "TEXT")
    add_column_if_missing(conn, "warehouses", "character_file", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "warehouses", "character_name", "TEXT")
    add_column_if_missing(conn, "warehouses", "location_type", "TEXT DEFAULT 'base'")
    add_column_if_missing(conn, "warehouses", "location_name", "TEXT")
    add_column_if_missing(conn, "warehouses", "item_nickname", "TEXT")
    add_column_if_missing(conn, "warehouses", "item_display_name", "TEXT")
    add_column_if_missing(conn, "warehouses", "category", "TEXT")
    add_column_if_missing(conn, "warehouses", "volume", "REAL DEFAULT 0")
    add_column_if_missing(conn, "warehouses", "mass", "REAL DEFAULT 0")
    add_column_if_missing(conn, "warehouses", "created_at", "TEXT")
    add_column_if_missing(conn, "warehouses", "updated_at", "TEXT")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            hash TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            good_nickname TEXT,
            equipment_nickname TEXT,
            category TEXT,
            section TEXT,
            display_name TEXT,
            volume REAL DEFAULT 0,
            mass REAL DEFAULT 0,
            units_per_container INTEGER DEFAULT 1,
            source_good_file TEXT,
            source_equip_file TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_items_nickname ON items(nickname);
        CREATE INDEX IF NOT EXISTS idx_items_good ON items(good_nickname);
        CREATE INDEX IF NOT EXISTS idx_items_equipment ON items(equipment_nickname);
        CREATE INDEX IF NOT EXISTS idx_items_display_name ON items(display_name);

        CREATE TABLE IF NOT EXISTS ships (
            hash TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            display_name TEXT,
            ship_type TEXT,
            hold_size INTEGER DEFAULT 0,
            nanobot_limit INTEGER DEFAULT 0,
            shield_battery_limit INTEGER DEFAULT 0,
            mass REAL DEFAULT 0,
            source_file TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_ships_nickname ON ships(nickname);
        CREATE INDEX IF NOT EXISTS idx_ships_display_name ON ships(display_name);

        CREATE TABLE IF NOT EXISTS locations (
            hash TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            location_type TEXT,
            system_nickname TEXT,
            display_name TEXT,
            source_file TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_locations_nickname ON locations(nickname);
        CREATE INDEX IF NOT EXISTS idx_locations_display_name ON locations(display_name);

        CREATE TABLE IF NOT EXISTS warehouses (
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

        CREATE INDEX IF NOT EXISTS idx_warehouses_owner_location ON warehouses(account_id, character_file, location_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouses_item ON warehouses(item_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouses_display_name ON warehouses(item_display_name);

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

        CREATE INDEX IF NOT EXISTS idx_warehouse_log_account_location ON warehouse_log(account_id, location_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouse_log_created ON warehouse_log(created_at);


        CREATE TABLE IF NOT EXISTS craft_sources (
            source_file TEXT PRIMARY KEY,
            path TEXT,
            size INTEGER DEFAULT 0,
            mtime_ns INTEGER DEFAULT 0,
            rows_count INTEGER DEFAULT 0,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS craft_recipes (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            duration_seconds INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            source_file TEXT,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_craft_recipes_name ON craft_recipes(name);
        CREATE INDEX IF NOT EXISTS idx_craft_recipes_enabled ON craft_recipes(enabled);

        CREATE TABLE IF NOT EXISTS craft_recipe_inputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_code TEXT NOT NULL,
            item_hash TEXT NOT NULL,
            item_nickname TEXT,
            item_display_name TEXT,
            quantity INTEGER NOT NULL,
            UNIQUE(recipe_code, item_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_craft_recipe_inputs_recipe ON craft_recipe_inputs(recipe_code);

        CREATE TABLE IF NOT EXISTS craft_recipe_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_code TEXT NOT NULL,
            item_hash TEXT NOT NULL,
            item_nickname TEXT,
            item_display_name TEXT,
            quantity INTEGER NOT NULL,
            UNIQUE(recipe_code, item_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_craft_recipe_outputs_recipe ON craft_recipe_outputs(recipe_code);

        CREATE TABLE IF NOT EXISTS craft_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            character_file TEXT,
            character_name TEXT,
            location_hash TEXT NOT NULL,
            location_name TEXT,
            recipe_code TEXT NOT NULL,
            recipe_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            started_at TEXT NOT NULL,
            finish_at TEXT NOT NULL,
            claimed_at TEXT,
            cancelled_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_craft_jobs_owner_location ON craft_jobs(account_id, character_file, location_hash);
        CREATE INDEX IF NOT EXISTS idx_craft_jobs_status ON craft_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_craft_jobs_finish ON craft_jobs(finish_at);

        CREATE TABLE IF NOT EXISTS craft_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            account_id TEXT NOT NULL,
            character_file TEXT,
            character_name TEXT,
            location_hash TEXT NOT NULL,
            location_name TEXT,
            recipe_code TEXT,
            recipe_name TEXT,
            operation TEXT NOT NULL,
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_craft_log_owner_location ON craft_log(account_id, character_file, location_hash);
        CREATE INDEX IF NOT EXISTS idx_craft_log_created ON craft_log(created_at);

        CREATE TABLE IF NOT EXISTS name_map (
            token TEXT PRIMARY KEY,
            hash TEXT,
            nickname TEXT,
            display_name TEXT NOT NULL,
            category TEXT,
            source_file TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_name_map_hash ON name_map(hash);
        CREATE INDEX IF NOT EXISTS idx_name_map_nickname ON name_map(nickname);
        CREATE INDEX IF NOT EXISTS idx_name_map_display_name ON name_map(display_name);

        CREATE TABLE IF NOT EXISTS ioncross_sources (
            source_file TEXT PRIMARY KEY,
            path TEXT,
            size INTEGER DEFAULT 0,
            mtime_ns INTEGER DEFAULT 0,
            sha256 TEXT,
            rows_count INTEGER DEFAULT 0,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ioncross_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            hash TEXT,
            nickname TEXT NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_ioncross_entries_hash ON ioncross_entries(hash);
        CREATE INDEX IF NOT EXISTS idx_ioncross_entries_nickname ON ioncross_entries(nickname);
        CREATE INDEX IF NOT EXISTS idx_ioncross_entries_display_name ON ioncross_entries(display_name);
        CREATE INDEX IF NOT EXISTS idx_ioncross_entries_source ON ioncross_entries(source_file);

        CREATE TABLE IF NOT EXISTS ioncross_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_token TEXT NOT NULL,
            target_token TEXT NOT NULL,
            hash TEXT,
            nickname TEXT,
            display_name TEXT,
            category TEXT,
            alias_type TEXT,
            source_file TEXT,
            note TEXT,
            UNIQUE(alias_token, target_token, alias_type)
        );

        CREATE INDEX IF NOT EXISTS idx_ioncross_aliases_alias ON ioncross_aliases(alias_token);
        CREATE INDEX IF NOT EXISTS idx_ioncross_aliases_target ON ioncross_aliases(target_token);

        """
    )
    migrate_db(conn)
    conn.commit()
