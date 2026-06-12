from __future__ import annotations

import argparse
import json
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fl_panel.config import ACCOUNTS_DIR, IONCROSS_DIR, ROOT
from fl_panel.db import connect
from fl_panel.repository import Repository
from fl_panel.warehouse import (
    ensure_warehouse_schema,
    location_from_character,
    resolve_item,
    character_file_key,
    character_name,
    now_iso,
)

try:
    from fl_panel.craft import RECIPE_CANDIDATES, sync_craft_recipes
except Exception:
    RECIPE_CANDIDATES = [
        ROOT / "craft" / "recipes.json",
        ROOT / "Craft" / "recipes.json",
        ROOT / "craft_system" / "recipes.json",
        ROOT / "recipes.json",
        Path(__file__).resolve().parent / "fl_panel" / "data" / "craft_recipes.json",
    ]

    def sync_craft_recipes(*args, **kwargs):
        return {"recipes_total": 0}


def norm(value: Any) -> str:
    return str(value or "").strip()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        return json.loads(path.read_text(encoding="cp1251"))


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
        return [x for x in raw if isinstance(x, dict)]

    return []


def normalize_item_tokens(raw: Any) -> list[str]:
    tokens: list[str] = []

    if isinstance(raw, dict):
        tokens.extend(str(token).strip() for token in raw.keys())
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                token = (
                    item.get("item")
                    or item.get("hash")
                    or item.get("nickname")
                    or item.get("code")
                    or item.get("id")
                )
                if token:
                    tokens.append(str(token).strip())
            elif isinstance(item, (list, tuple)) and item:
                tokens.append(str(item[0]).strip())
            elif isinstance(item, str):
                tokens.append(item.strip())

    return [token for token in tokens if token]


def recipe_items(recipe: dict[str, Any], side: str) -> list[str]:
    keys = {
        "inputs": ["inputs", "input", "requires", "requirements", "cost", "ingredients", "resources"],
        "outputs": ["outputs", "output", "result", "results", "produce", "products"],
    }[side]

    for key in keys:
        if key in recipe:
            return normalize_item_tokens(recipe.get(key))

    return []


def collect_tokens_from_recipe_file(path: Path) -> OrderedDict[str, list[str]]:
    raw = load_json(path)
    tokens: OrderedDict[str, list[str]] = OrderedDict()

    def add(token: str, source: str) -> None:
        token = norm(token)
        if not token:
            return
        tokens.setdefault(token, [])
        if source not in tokens[token]:
            tokens[token].append(source)

    if isinstance(raw, dict):
        for token in raw.get("base_resources", []) or []:
            add(token, "base_resource")

    for recipe in normalize_recipe_list(raw):
        code = norm(recipe.get("code") or recipe.get("id") or recipe.get("name") or "recipe")
        for token in recipe_items(recipe, "inputs"):
            add(token, f"input:{code}")
        for token in recipe_items(recipe, "outputs"):
            add(token, f"output:{code}")

    return tokens


def collect_recipe_tokens(conn: sqlite3.Connection, recipe_path: Path | None = None) -> OrderedDict[str, list[str]]:
    tokens: OrderedDict[str, list[str]] = OrderedDict()

    def merge(src: OrderedDict[str, list[str]]) -> None:
        for token, sources in src.items():
            tokens.setdefault(token, [])
            for source in sources:
                if source not in tokens[token]:
                    tokens[token].append(source)

    if recipe_path:
        if not recipe_path.exists():
            raise SystemExit(f"recipes json not found: {recipe_path}")
        merge(collect_tokens_from_recipe_file(recipe_path))
    else:
        for candidate in RECIPE_CANDIDATES:
            if candidate.exists() and candidate.is_file():
                merge(collect_tokens_from_recipe_file(candidate))

    # Fallback/additional source: already imported craft tables.
    for table in ("craft_recipe_inputs", "craft_recipe_outputs"):
        exists = conn.execute(
            "select name from sqlite_master where type='table' and name=?",
            (table,),
        ).fetchone()
        if not exists:
            continue

        rows = conn.execute(f"select recipe_code, item_hash from {table}").fetchall()
        for row in rows:
            token = norm(row["item_hash"])
            recipe_code = norm(row["recipe_code"])
            if token:
                tokens.setdefault(token, [])
                source = f"db:{table}:{recipe_code}"
                if source not in tokens[token]:
                    tokens[token].append(source)

    return tokens


def find_character(
    repo: Repository,
    account_id: str,
    character_file: str = "",
    character_name_arg: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    account_id = account_id.lower().strip()
    account = repo.by_id.get(account_id)

    if not account:
        raise SystemExit(f"account not found: {account_id}")

    characters = account.get("characters", [])

    if character_file:
        wanted = character_file.lower().strip()
        for char in characters:
            if norm(char.get("file")).lower() == wanted:
                return account, char
        raise SystemExit(f"character file not found in {account_id}: {character_file}")

    if character_name_arg:
        wanted = character_name_arg.lower().strip()
        for char in characters:
            if norm(char.get("name")).lower() == wanted:
                return account, char
        raise SystemExit(f"character name not found in {account_id}: {character_name_arg}")

    if len(characters) == 1:
        return account, characters[0]

    print(f"account {account_id} has {len(characters)} characters:")
    for char in characters:
        print(f"  file={char.get('file')}  name={char.get('name')}")
    raise SystemExit("specify --character-file or --character-name")


def insert_personal_warehouse(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    character: dict[str, Any],
    location: dict[str, str],
    tokens: OrderedDict[str, list[str]],
    quantity: int,
    clear: bool,
    dry_run: bool,
) -> tuple[int, list[str]]:
    ensure_warehouse_schema(conn)

    char_file = character_file_key(character)
    char_name = character_name(character)
    ts = now_iso()
    unresolved: list[str] = []
    inserted = 0

    if clear and not dry_run:
        conn.execute(
            """
            delete from warehouses
            where account_id = ?
              and character_file = ?
              and location_hash = ?
            """,
            (account_id, char_file, location["token"]),
        )

    for token in tokens.keys():
        item = resolve_item(conn, token)
        if not item:
            unresolved.append(token)
            continue

        inserted += 1

        if dry_run:
            continue

        conn.execute(
            """
            insert into warehouses
            (account_id, character_file, character_name, location_hash, location_type, location_name,
             item_hash, item_nickname, item_display_name, category, volume, mass, quantity, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(account_id, character_file, location_hash, item_hash)
            do update set
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
                char_file,
                char_name,
                location["token"],
                location.get("type") or "base",
                location["name"],
                item["hash"],
                item["nickname"],
                item["display_name"],
                item.get("category", ""),
                float(item.get("volume", 0) or 0),
                float(item.get("mass", 0) or 0),
                quantity,
                ts,
                ts,
            ),
        )

    return inserted, unresolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create/fill personal per-character warehouse for crafting resources."
    )
    parser.add_argument("--accounts", default=str(ACCOUNTS_DIR), help="path to Accts/MultiPlayer")
    parser.add_argument("--ioncross", default=str(IONCROSS_DIR), help="path to IONCROSS")
    parser.add_argument("--db", default="fl_panel/data/flpanel.db", help="path to flpanel.db")
    parser.add_argument("--recipes", default="", help="optional path to craft_recipes.json")

    parser.add_argument("--account-id", required=True, help="account id, for example 23-47952d60")
    parser.add_argument("--character-file", default="", help="character .fl file, for example 08-729a3c08.fl")
    parser.add_argument("--character-name", default="", help="character name, for example jeka1202")

    parser.add_argument("--location-hash", default="", help="override base/location token")
    parser.add_argument("--location-name", default="", help="override base/location display name")

    parser.add_argument("--quantity", type=int, default=1_000_000, help="quantity for every craft item")
    parser.add_argument("--clear", action="store_true", help="clear this character warehouse at this location before fill")
    parser.add_argument("--dry-run", action="store_true", help="show what would be imported without DB writes")

    args = parser.parse_args()

    accounts_dir = Path(args.accounts)
    ioncross_dir = Path(args.ioncross)
    db_path = Path(args.db)
    recipe_path = Path(args.recipes) if args.recipes else None

    if args.quantity <= 0:
        raise SystemExit("--quantity must be positive")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        sync_craft_recipes(conn=conn)
    except Exception as exc:
        print(f"warning: craft recipe db sync failed: {exc}")

    repo = Repository(accounts_dir, ioncross_dir)
    account, character = find_character(
        repo,
        args.account_id,
        args.character_file,
        args.character_name,
    )

    location = location_from_character(character)
    if args.location_hash:
        location["token"] = args.location_hash
    if args.location_name:
        location["name"] = args.location_name
    if not location.get("type"):
        location["type"] = "base"

    tokens = collect_recipe_tokens(conn, recipe_path)
    if not tokens:
        raise SystemExit("no craft items found. Check craft_recipes.json")

    print("target")
    print("------")
    print(f"account_id:      {account['id']}")
    print(f"character_file:  {character_file_key(character)}")
    print(f"character_name:  {character_name(character)}")
    print(f"location_hash:   {location['token']}")
    print(f"location_name:   {location['name']}")
    print(f"quantity/item:   {args.quantity}")
    print(f"craft items:     {len(tokens)}")
    print(f"clear first:     {bool(args.clear)}")
    print(f"dry run:         {bool(args.dry_run)}")
    print()

    try:
        inserted, unresolved = insert_personal_warehouse(
            conn,
            account_id=account["id"],
            character=character,
            location=location,
            tokens=tokens,
            quantity=args.quantity,
            clear=args.clear,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("result")
    print("------")
    print(f"resolved/imported: {inserted}")
    print(f"unresolved:        {len(unresolved)}")

    if unresolved:
        print()
        print("unresolved items:")
        for token in unresolved[:50]:
            print(f"  {token}")
        if len(unresolved) > 50:
            print(f"  ... and {len(unresolved) - 50} more")

    if args.dry_run:
        print()
        print("dry-run only: database was not changed.")
    else:
        print()
        print("done.")


if __name__ == "__main__":
    main()
