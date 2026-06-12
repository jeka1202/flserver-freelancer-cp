from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ROOT
from .db import connect
from .fl_ini_parser import to_int
from .warehouse import (
    ensure_warehouse_schema,
    location_from_character,
    now_iso,
    resolve_item,
    row_value,
    character_file_key,
    character_name,
)


RECIPE_CANDIDATES = [
    ROOT / "craft" / "recipes.json",
    ROOT / "Craft" / "recipes.json",
    ROOT / "craft_system" / "recipes.json",
    ROOT / "recipes.json",
    Path(__file__).resolve().parent / "data" / "craft_recipes.json",
]


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value))


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-zа-я0-9_ -]+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[\s-]+", "_", value)
    return value or "recipe"


def parse_positive_int(value: str, default: int = -1) -> int:
    amount = to_int(str(value).strip(), default)
    return amount if amount > 0 else -1


def ensure_craft_schema(conn: sqlite3.Connection) -> None:
    ensure_warehouse_schema(conn)
    conn.executescript(
        """
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

        CREATE INDEX IF NOT EXISTS idx_craft_jobs_owner_location
            ON craft_jobs(account_id, character_file, location_hash);
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

        CREATE INDEX IF NOT EXISTS idx_craft_log_owner_location
            ON craft_log(account_id, character_file, location_hash);
        CREATE INDEX IF NOT EXISTS idx_craft_log_created ON craft_log(created_at);
        """
    )

    # Old craft_jobs already has character_file in v9, but old indexes were account+location only.
    # Queries below always filter by character_file, so different pilots never share queues.
    conn.commit()


def add_warehouse_delta(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    character_file: str,
    character_name_value: str,
    location: dict[str, str],
    item: dict[str, Any],
    delta: int,
) -> None:
    """Change this exact character's warehouse quantity."""
    if delta == 0:
        return

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
        (account_id, character_file, location["token"], item["hash"]),
    ).fetchone()

    current = int(row_value(row, "quantity", 0) or 0)
    new_quantity = current + delta

    if new_quantity < 0:
        raise ValueError(f"Недостаточно предмета «{item['display_name']}»: есть {current}, нужно {-delta}.")

    if new_quantity == 0:
        conn.execute(
            """
            DELETE FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
            """,
            (account_id, character_file, location["token"], item["hash"]),
        )
        return

    ts = now_iso()
    conn.execute(
        """
        INSERT INTO warehouses
        (account_id, character_file, character_name, location_hash, location_type, location_name,
         item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, character_file, location_hash, item_hash)
        DO UPDATE SET
            quantity = excluded.quantity,
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
            character_file,
            character_name_value,
            location["token"],
            location["type"],
            location["name"],
            item["hash"],
            item["nickname"],
            item["display_name"],
            item.get("category", ""),
            float(item.get("volume", 0) or 0),
            float(item.get("mass", 0) or 0),
            new_quantity,
            ts,
            ts,
        ),
    )


def warehouse_quantity(conn: sqlite3.Connection, account_id: str, character_file: str, location_token: str, item_hash: str) -> int:
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
        (account_id, character_file, location_token, item_hash),
    ).fetchone()
    return int(row_value(row, "quantity", 0) or 0)


def log_craft(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    character: dict[str, Any],
    location: dict[str, str],
    recipe_code: str,
    recipe_name: str,
    operation: str,
    note: str,
) -> None:
    conn.execute(
        """
        INSERT INTO craft_log
        (created_at, account_id, character_file, character_name, location_hash, location_name,
         recipe_code, recipe_name, operation, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            account_id,
            character_file_key(character),
            character_name(character),
            location["token"],
            location["name"],
            recipe_code,
            recipe_name,
            operation,
            note,
        ),
    )


def normalize_recipe_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("recipes", "items", "crafts", "data"):
            if isinstance(raw.get(key), list):
                return raw[key]
        result = []
        for code, recipe in raw.items():
            if isinstance(recipe, dict):
                recipe = dict(recipe)
                recipe.setdefault("code", code)
                result.append(recipe)
        return result

    if isinstance(raw, list):
        return raw

    return []


def normalize_item_list(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []

    if isinstance(raw, dict):
        return [{"item": token, "quantity": qty} for token, qty in raw.items()]

    if isinstance(raw, list):
        result = []
        for entry in raw:
            if isinstance(entry, dict):
                result.append(entry)
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                result.append({"item": entry[0], "quantity": entry[1]})
        return result

    return []


def recipe_duration(recipe: dict[str, Any]) -> int:
    for key in ("duration_seconds", "duration", "time_seconds", "time", "craft_time", "seconds"):
        if key in recipe:
            return max(0, to_int(str(recipe.get(key)), 0))

    minutes = recipe.get("minutes")
    if minutes is not None:
        return max(0, to_int(str(minutes), 0) * 60)

    return 0


def recipe_items(recipe: dict[str, Any], side: str) -> list[dict[str, Any]]:
    keys = {
        "inputs": ["inputs", "input", "requires", "requirements", "cost", "ingredients", "resources"],
        "outputs": ["outputs", "output", "result", "results", "produce", "products"],
    }[side]

    for key in keys:
        if key in recipe:
            return normalize_item_list(recipe.get(key))

    return []


def import_recipe_file(conn: sqlite3.Connection, path: Path, *, force: bool = False) -> dict[str, Any]:
    stat = path.stat()
    source_file = path.name

    existing = conn.execute(
        """
        SELECT size, mtime_ns
        FROM craft_sources
        WHERE source_file = ?
        """,
        (source_file,),
    ).fetchone()

    if (
        not force
        and existing
        and int(row_value(existing, "size", 0) or 0) == int(stat.st_size)
        and int(row_value(existing, "mtime_ns", 0) or 0) == int(stat.st_mtime_ns)
    ):
        return {"source_file": source_file, "changed": False, "recipes": 0, "errors": []}

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        raw = json.loads(path.read_text(encoding="cp1251"))
    recipes = normalize_recipe_list(raw)

    conn.execute("DELETE FROM craft_recipe_inputs WHERE recipe_code IN (SELECT code FROM craft_recipes WHERE source_file = ?)", (source_file,))
    conn.execute("DELETE FROM craft_recipe_outputs WHERE recipe_code IN (SELECT code FROM craft_recipes WHERE source_file = ?)", (source_file,))
    conn.execute("DELETE FROM craft_recipes WHERE source_file = ?", (source_file,))

    imported = 0
    errors: list[str] = []

    for index, recipe in enumerate(recipes, 1):
        if not isinstance(recipe, dict):
            continue

        name = str(recipe.get("name") or recipe.get("title") or recipe.get("display_name") or "").strip()
        code = str(recipe.get("code") or recipe.get("id") or recipe.get("nickname") or slugify(name or f"recipe_{index}")).strip()
        if not name:
            name = code

        inputs_raw = recipe_items(recipe, "inputs")
        outputs_raw = recipe_items(recipe, "outputs")

        if not inputs_raw or not outputs_raw:
            errors.append(f"{code}: нет inputs/outputs")
            continue

        input_items = []
        output_items = []

        for raw_item in inputs_raw:
            token = str(raw_item.get("item") or raw_item.get("hash") or raw_item.get("nickname") or raw_item.get("code") or raw_item.get("id") or "").strip()
            quantity = parse_positive_int(str(raw_item.get("quantity", raw_item.get("qty", raw_item.get("count", 1)))))
            item = resolve_item(conn, token)
            if not item:
                errors.append(f"{code}: предмет входа не найден: {token}")
                continue
            input_items.append((item, quantity))

        for raw_item in outputs_raw:
            token = str(raw_item.get("item") or raw_item.get("hash") or raw_item.get("nickname") or raw_item.get("code") or raw_item.get("id") or "").strip()
            quantity = parse_positive_int(str(raw_item.get("quantity", raw_item.get("qty", raw_item.get("count", 1)))))
            item = resolve_item(conn, token)
            if not item:
                errors.append(f"{code}: предмет выхода не найден: {token}")
                continue
            output_items.append((item, quantity))

        if not input_items or not output_items:
            continue

        conn.execute(
            """
            INSERT OR REPLACE INTO craft_recipes
            (code, name, description, category, duration_seconds, enabled, source_file, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                name,
                str(recipe.get("description") or recipe.get("desc") or ""),
                str(recipe.get("category") or ""),
                recipe_duration(recipe),
                1 if recipe.get("enabled", True) else 0,
                source_file,
                now_iso(),
            ),
        )

        for item, quantity in input_items:
            conn.execute(
                """
                INSERT OR REPLACE INTO craft_recipe_inputs
                (recipe_code, item_hash, item_nickname, item_display_name, quantity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, item["hash"], item["nickname"], item["display_name"], quantity),
            )

        for item, quantity in output_items:
            conn.execute(
                """
                INSERT OR REPLACE INTO craft_recipe_outputs
                (recipe_code, item_hash, item_nickname, item_display_name, quantity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, item["hash"], item["nickname"], item["display_name"], quantity),
            )

        imported += 1

    conn.execute(
        """
        INSERT OR REPLACE INTO craft_sources
        (source_file, path, size, mtime_ns, rows_count, imported_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_file, str(path), int(stat.st_size), int(stat.st_mtime_ns), imported, now_iso()),
    )

    return {"source_file": source_file, "changed": True, "recipes": imported, "errors": errors}


def sync_craft_recipes(*, force: bool = False, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    own_conn = conn is None
    conn = conn or connect()
    ensure_craft_schema(conn)

    stats = {
        "files_total": 0,
        "files_changed": 0,
        "recipes_imported": 0,
        "recipes_total": 0,
        "errors": [],
        "paths": [],
    }

    try:
        for path in RECIPE_CANDIDATES:
            if not path.exists() or not path.is_file():
                continue

            stats["files_total"] += 1
            stats["paths"].append(str(path))
            result = import_recipe_file(conn, path, force=force)
            if result["changed"]:
                stats["files_changed"] += 1
            stats["recipes_imported"] += int(result["recipes"] or 0)
            stats["errors"].extend(result["errors"])

        stats["recipes_total"] = conn.execute("SELECT COUNT(*) FROM craft_recipes WHERE enabled = 1").fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

    return stats


def ensure_craft_recipes_available(conn: sqlite3.Connection) -> None:
    """Fast guard for UI/runtime.

    Full recipe sync is done at panel startup. On regular /cabinet renders and craft
    actions we only check that recipes exist. If DB is empty, then we sync once.
    """

    ensure_craft_schema(conn)
    row = conn.execute("SELECT COUNT(*) FROM craft_recipes WHERE enabled = 1").fetchone()
    if int(row[0] or 0) <= 0:
        sync_craft_recipes(conn=conn)


def complete_due_jobs(conn: sqlite3.Connection, account_id: str, character_file: str, location_token: str) -> int:
    now = now_iso()
    cursor = conn.execute(
        """
        UPDATE craft_jobs
        SET status = 'done'
        WHERE account_id = ?
          AND character_file = ?
          AND location_hash = ?
          AND status = 'active'
          AND finish_at <= ?
        """,
        (account_id, character_file, location_token, now),
    )
    return max(cursor.rowcount or 0, 0)


def load_recipe(conn: sqlite3.Connection, recipe_code: str) -> dict[str, Any] | None:
    recipe = conn.execute(
        """
        SELECT *
        FROM craft_recipes
        WHERE code = ?
          AND enabled = 1
        LIMIT 1
        """,
        (recipe_code,),
    ).fetchone()

    if not recipe:
        return None

    inputs = conn.execute(
        """
        SELECT *
        FROM craft_recipe_inputs
        WHERE recipe_code = ?
        ORDER BY item_display_name COLLATE NOCASE
        """,
        (recipe_code,),
    ).fetchall()

    outputs = conn.execute(
        """
        SELECT *
        FROM craft_recipe_outputs
        WHERE recipe_code = ?
        ORDER BY item_display_name COLLATE NOCASE
        """,
        (recipe_code,),
    ).fetchall()

    return {
        "recipe": recipe,
        "inputs": inputs,
        "outputs": outputs,
    }


def recipe_rows_for_ui(conn: sqlite3.Connection, account_id: str, character_file: str, location_token: str) -> list[dict[str, Any]]:
    """Load all recipes for UI with bulk SQL queries.

    Old implementation did per-recipe queries and per-ingredient warehouse checks.
    With 60+ recipes this created hundreds of SQLite calls on every /cabinet render.
    """

    recipes = conn.execute(
        """
        SELECT *
        FROM craft_recipes
        WHERE enabled = 1
        ORDER BY category COLLATE NOCASE, name COLLATE NOCASE
        """
    ).fetchall()

    if not recipes:
        return []

    codes = [recipe["code"] for recipe in recipes]
    placeholders = ",".join("?" for _ in codes)

    input_rows = conn.execute(
        f"""
        SELECT *
        FROM craft_recipe_inputs
        WHERE recipe_code IN ({placeholders})
        ORDER BY recipe_code, item_display_name COLLATE NOCASE
        """,
        codes,
    ).fetchall()

    output_rows = conn.execute(
        f"""
        SELECT *
        FROM craft_recipe_outputs
        WHERE recipe_code IN ({placeholders})
        ORDER BY recipe_code, item_display_name COLLATE NOCASE
        """,
        codes,
    ).fetchall()

    warehouse_rows = conn.execute(
        """
        SELECT item_hash, quantity
        FROM warehouses
        WHERE account_id = ?
          AND character_file = ?
          AND location_hash = ?
          AND quantity > 0
        """,
        (account_id, character_file, location_token),
    ).fetchall()

    have_by_hash = {
        str(row["item_hash"]): int(row["quantity"] or 0)
        for row in warehouse_rows
    }

    inputs_by_recipe: dict[str, list[Any]] = {}
    outputs_by_recipe: dict[str, list[Any]] = {}

    for row in input_rows:
        inputs_by_recipe.setdefault(str(row["recipe_code"]), []).append(row)

    for row in output_rows:
        outputs_by_recipe.setdefault(str(row["recipe_code"]), []).append(row)

    result = []

    for recipe in recipes:
        code = str(recipe["code"])
        inputs = inputs_by_recipe.get(code, [])
        outputs = outputs_by_recipe.get(code, [])

        can_make = True
        requirements = []
        output_text = []

        for item in inputs:
            item_hash = str(item["item_hash"])
            have = have_by_hash.get(item_hash, 0)
            need = int(item["quantity"] or 0)
            if have < need:
                can_make = False
            requirements.append({
                "name": item["item_display_name"],
                "need": need,
                "have": have,
                "ok": have >= need,
            })

        for item in outputs:
            output_text.append({
                "name": item["item_display_name"],
                "quantity": int(item["quantity"] or 0),
            })

        result.append({
            "code": recipe["code"],
            "name": recipe["name"],
            "description": recipe["description"] or "",
            "category": recipe["category"] or "",
            "duration_seconds": int(recipe["duration_seconds"] or 0),
            "requirements": requirements,
            "outputs": output_text,
            "can_make": can_make,
        })

    return result


def load_jobs(conn: sqlite3.Connection, account_id: str, character_file: str, location_token: str) -> list[dict[str, Any]]:
    complete_due_jobs(conn, account_id, character_file, location_token)

    rows = conn.execute(
        """
        SELECT *
        FROM craft_jobs
        WHERE account_id = ?
          AND character_file = ?
          AND location_hash = ?
          AND status IN ('active', 'done')
        ORDER BY finish_at, id
        """,
        (account_id, character_file, location_token),
    ).fetchall()

    now = datetime.now()
    jobs = []

    for row in rows:
        start_dt = parse_dt(row["started_at"])
        finish_dt = parse_dt(row["finish_at"])
        total_seconds = max(1, int((finish_dt - start_dt).total_seconds()))
        seconds_left = max(0, int((finish_dt - now).total_seconds()))
        ready = row["status"] == "done" or seconds_left <= 0
        elapsed = total_seconds - seconds_left
        progress_pct = 100.0 if ready else max(0.0, min(100.0, (elapsed / total_seconds) * 100.0))

        jobs.append({
            "id": int(row["id"]),
            "recipe_code": row["recipe_code"],
            "recipe_name": row["recipe_name"],
            "quantity": int(row["quantity"] or 1),
            "status": row["status"],
            "started_at": row["started_at"],
            "finish_at": row["finish_at"],
            "total_seconds": total_seconds,
            "seconds_left": seconds_left,
            "progress_pct": round(progress_pct, 2),
            "ready": ready,
        })

    conn.commit()
    return jobs


def current_craft_context(account_id: str, character: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    ensure_craft_recipes_available(conn)

    location = location_from_character(character)
    char_file = character_file_key(character)
    recipes = recipe_rows_for_ui(conn, account_id, char_file, location["token"])
    jobs = load_jobs(conn, account_id, char_file, location["token"])

    stats = {
        "available": True,
        "account_id": account_id,
        "character_file": char_file,
        "character_name": character_name(character),
        "location": location,
        "recipes": recipes,
        "jobs": jobs,
        "recipes_total": len(recipes),
        "jobs_total": len(jobs),
    }

    conn.close()
    return stats


def start_craft_job(account_id: str, character: dict[str, Any], recipe_code: str, quantity: int) -> tuple[bool, str]:
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    conn = connect()
    ensure_craft_recipes_available(conn)

    location = location_from_character(character)
    char_file = character_file_key(character)
    char_name = character_name(character)
    data = load_recipe(conn, recipe_code)
    if not data:
        conn.close()
        return False, "Рецепт не найден."

    recipe = data["recipe"]
    inputs = data["inputs"]
    if not inputs:
        conn.close()
        return False, "У рецепта нет входных ресурсов."

    try:
        for item_row in inputs:
            item = resolve_item(conn, item_row["item_hash"])
            if not item:
                raise ValueError(f"Предмет рецепта не найден: {item_row['item_display_name']}")
            add_warehouse_delta(
                conn,
                account_id=account_id,
                character_file=char_file,
                character_name_value=char_name,
                location=location,
                item=item,
                delta=-(int(item_row["quantity"] or 0) * quantity),
            )

        started = datetime.now()
        duration = int(recipe["duration_seconds"] or 0) * quantity
        finish = started + timedelta(seconds=duration)

        conn.execute(
            """
            INSERT INTO craft_jobs
            (account_id, character_file, character_name, location_hash, location_name,
             recipe_code, recipe_name, quantity, status, started_at, finish_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                account_id,
                char_file,
                char_name,
                location["token"],
                location["name"],
                recipe["code"],
                recipe["name"],
                quantity,
                started.isoformat(timespec="seconds"),
                finish.isoformat(timespec="seconds"),
            ),
        )

        log_craft(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            recipe_code=recipe["code"],
            recipe_name=recipe["name"],
            operation="start",
            note=f"Started x{quantity}. Inputs consumed from this character warehouse only.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Крафт не запущен: {exc}"

    conn.close()
    return True, f"Крафт запущен для пилота «{char_name}»: «{recipe['name']}» ×{quantity}. Ресурсы списаны только с его личного склада базы."


def claim_craft_job(account_id: str, character: dict[str, Any], job_id: int) -> tuple[bool, str]:
    if job_id <= 0:
        return False, "Неверный ID задания."

    conn = connect()
    ensure_craft_schema(conn)
    location = location_from_character(character)
    char_file = character_file_key(character)
    char_name = character_name(character)
    complete_due_jobs(conn, account_id, char_file, location["token"])

    job = conn.execute(
        """
        SELECT *
        FROM craft_jobs
        WHERE id = ?
          AND account_id = ?
          AND character_file = ?
          AND location_hash = ?
        LIMIT 1
        """,
        (job_id, account_id, char_file, location["token"]),
    ).fetchone()

    if not job:
        conn.close()
        return False, "Задание крафта не найдено."

    if job["status"] != "done":
        conn.close()
        return False, "Крафт ещё не готов."

    outputs = conn.execute(
        """
        SELECT *
        FROM craft_recipe_outputs
        WHERE recipe_code = ?
        """,
        (job["recipe_code"],),
    ).fetchall()

    try:
        for item_row in outputs:
            item = resolve_item(conn, item_row["item_hash"])
            if not item:
                raise ValueError(f"Предмет выхода не найден: {item_row['item_display_name']}")
            add_warehouse_delta(
                conn,
                account_id=account_id,
                character_file=char_file,
                character_name_value=char_name,
                location=location,
                item=item,
                delta=int(item_row["quantity"] or 0) * int(job["quantity"] or 1),
            )

        conn.execute(
            """
            UPDATE craft_jobs
            SET status = 'claimed', claimed_at = ?
            WHERE id = ?
              AND account_id = ?
              AND character_file = ?
            """,
            (now_iso(), job_id, account_id, char_file),
        )

        log_craft(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            recipe_code=job["recipe_code"],
            recipe_name=job["recipe_name"],
            operation="claim",
            note=f"Claimed job #{job_id}. Outputs added to this character warehouse.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Не удалось забрать крафт: {exc}"

    conn.close()
    return True, f"Готовый крафт «{job['recipe_name']}» добавлен в личный склад пилота «{char_name}»."


def cancel_craft_job(account_id: str, character: dict[str, Any], job_id: int) -> tuple[bool, str]:
    if job_id <= 0:
        return False, "Неверный ID задания."

    conn = connect()
    ensure_craft_schema(conn)
    location = location_from_character(character)
    char_file = character_file_key(character)
    char_name = character_name(character)
    complete_due_jobs(conn, account_id, char_file, location["token"])

    job = conn.execute(
        """
        SELECT *
        FROM craft_jobs
        WHERE id = ?
          AND account_id = ?
          AND character_file = ?
          AND location_hash = ?
        LIMIT 1
        """,
        (job_id, account_id, char_file, location["token"]),
    ).fetchone()

    if not job:
        conn.close()
        return False, "Задание крафта не найдено."

    if job["status"] == "done":
        conn.close()
        return False, "Готовое задание нельзя отменить. Его нужно забрать."

    if job["status"] != "active":
        conn.close()
        return False, "Это задание уже не активно."

    inputs = conn.execute(
        """
        SELECT *
        FROM craft_recipe_inputs
        WHERE recipe_code = ?
        """,
        (job["recipe_code"],),
    ).fetchall()

    try:
        for item_row in inputs:
            item = resolve_item(conn, item_row["item_hash"])
            if not item:
                raise ValueError(f"Предмет входа не найден: {item_row['item_display_name']}")
            add_warehouse_delta(
                conn,
                account_id=account_id,
                character_file=char_file,
                character_name_value=char_name,
                location=location,
                item=item,
                delta=int(item_row["quantity"] or 0) * int(job["quantity"] or 1),
            )

        conn.execute(
            """
            UPDATE craft_jobs
            SET status = 'cancelled', cancelled_at = ?
            WHERE id = ?
              AND account_id = ?
              AND character_file = ?
            """,
            (now_iso(), job_id, account_id, char_file),
        )

        log_craft(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            recipe_code=job["recipe_code"],
            recipe_name=job["recipe_name"],
            operation="cancel",
            note=f"Cancelled job #{job_id}. Inputs refunded to this character warehouse.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Не удалось отменить крафт: {exc}"

    conn.close()
    return True, f"Крафт «{job['recipe_name']}» отменён. Ресурсы возвращены в личный склад пилота «{char_name}»."
