from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import connect
from .fl_ini_parser import iter_ini_sections
from .config import ROOT


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_schema(conn: sqlite3.Connection) -> None:
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
        """
    )


def clean_value(value: Any) -> str:
    return str(value or "").strip()


def first(values: list[str] | str | None) -> str:
    if isinstance(values, list):
        return clean_value(values[0]) if values else ""
    return clean_value(values)


def load_name_map(conn: sqlite3.Connection, token: str) -> dict[str, str]:
    token = clean_value(token)
    if not token:
        return {}

    row = conn.execute(
        """
        SELECT hash, nickname, display_name, category
        FROM name_map
        WHERE token = ? OR lower(token) = lower(?)
        LIMIT 1
        """,
        (token, token),
    ).fetchone()

    if not row:
        return {}

    return {
        "hash": clean_value(row["hash"]),
        "nickname": clean_value(row["nickname"]),
        "display_name": clean_value(row["display_name"]),
        "category": clean_value(row["category"]),
    }


def find_item_by_token(conn: sqlite3.Connection, token: str) -> dict[str, str]:
    token = clean_value(token)
    if not token:
        return {}

    row = conn.execute(
        """
        SELECT hash, nickname, good_nickname, equipment_nickname, display_name, category
        FROM items
        WHERE hash = ?
           OR nickname = ?
           OR good_nickname = ?
           OR equipment_nickname = ?
        LIMIT 1
        """,
        (token, token, token, token),
    ).fetchone()

    if row:
        return {
            "hash": clean_value(row["hash"]),
            "nickname": clean_value(row["nickname"] or row["good_nickname"] or row["equipment_nickname"]),
            "display_name": clean_value(row["display_name"]),
            "category": clean_value(row["category"]),
        }

    return load_name_map(conn, token)


def collect_ini_details(conn: sqlite3.Connection, data_root: Path) -> int:
    updates = 0
    candidates = [p for p in data_root.rglob("*.ini") if p.is_file()]
    skip_dirs = {"Missions", "Scripts", "Audio"}

    for path in candidates:
        if any(part in skip_dirs for part in path.parts):
            continue

        try:
            rel_path = str(path.relative_to(data_root))
        except ValueError:
            rel_path = str(path)

        try:
            sections = iter_ini_sections(path)
        except Exception:
            continue

        for section, values in sections:
            nickname = first(values.get("nickname"))
            if not nickname:
                continue

            ids_name = first(values.get("ids_name"))
            ids_info = first(values.get("ids_info"))
            icon = first(values.get("icon")) or first(values.get("loot_appearance")) or first(values.get("DA_archetype"))

            interesting_keys = {
                "ids_name", "ids_info", "nickname", "volume", "mass", "hit_pts",
                "price", "item_icon", "icon", "loot_appearance", "DA_archetype",
                "material_library", "category", "units_per_container",
                "hp_type", "requires_ammo", "ammo_limit", "hold_size",
            }

            raw = {k: v for k, v in values.items() if k in interesting_keys}

            item = find_item_by_token(conn, nickname)
            item_hash = item.get("hash") or nickname
            display_name = item.get("display_name") or nickname

            description_parts = []
            if ids_name:
                description_parts.append(f"ids_name: {ids_name}")
            if ids_info:
                description_parts.append(f"ids_info: {ids_info}")
            if first(values.get("volume")):
                description_parts.append(f"volume: {first(values.get('volume'))}")
            if first(values.get("mass")):
                description_parts.append(f"mass: {first(values.get('mass'))}")
            if first(values.get("price")):
                description_parts.append(f"price: {first(values.get('price'))}")
            if first(values.get("hit_pts")):
                description_parts.append(f"hit points: {first(values.get('hit_pts'))}")

            description = "\\n".join(description_parts)

            conn.execute(
                """
                INSERT INTO item_details
                (item_hash, nickname, display_name, description, ids_name, ids_info, icon_source, source_file, raw_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_hash)
                DO UPDATE SET
                    nickname = excluded.nickname,
                    display_name = excluded.display_name,
                    description = COALESCE(NULLIF(excluded.description, ''), item_details.description),
                    ids_name = COALESCE(NULLIF(excluded.ids_name, ''), item_details.ids_name),
                    ids_info = COALESCE(NULLIF(excluded.ids_info, ''), item_details.ids_info),
                    icon_source = COALESCE(NULLIF(excluded.icon_source, ''), item_details.icon_source),
                    source_file = excluded.source_file,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item_hash,
                    nickname,
                    display_name,
                    description,
                    ids_name,
                    ids_info,
                    icon,
                    rel_path,
                    json.dumps(raw, ensure_ascii=False),
                    now_iso(),
                ),
            )
            updates += 1

    return updates


def convert_tga_icons(conn: sqlite3.Connection, data_root: Path, output_dir: Path) -> dict[str, int]:
    stats = {"converted": 0, "matched": 0, "skipped": 0}

    try:
        from PIL import Image
    except Exception:
        print("Pillow not installed. TGA conversion skipped. Install pillow if needed: py -m pip install pillow")
        return stats

    output_dir.mkdir(parents=True, exist_ok=True)
    tga_files = [p for p in data_root.rglob("*.tga") if p.is_file()]

    for path in tga_files:
        try:
            rel = path.relative_to(data_root)
            out_name = "_".join(rel.with_suffix(".png").parts)
            out_path = output_dir / out_name

            if not out_path.exists() or out_path.stat().st_mtime_ns < path.stat().st_mtime_ns:
                with Image.open(path) as img:
                    img.save(out_path)
                stats["converted"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            stats["skipped"] += 1
            continue

    # Very rough matching: if icon_source or nickname stem appears in generated png path.
    rows = conn.execute("SELECT item_hash, nickname, icon_source FROM item_details").fetchall()
    pngs = list(output_dir.glob("*.png"))

    for row in rows:
        item_hash = clean_value(row["item_hash"])
        nickname = clean_value(row["nickname"]).lower()
        icon_source = clean_value(row["icon_source"]).replace("\\\\", "/").lower()
        if not item_hash:
            continue

        match = None
        for png in pngs:
            hay = png.name.lower()
            if icon_source and Path(icon_source).stem.lower() in hay:
                match = png
                break
            if nickname and nickname in hay:
                match = png
                break

        if match:
            web_path = "generated_icons/" + match.name
            conn.execute("UPDATE item_details SET icon_png = ?, updated_at = ? WHERE item_hash = ?", (web_path, now_iso(), item_hash))
            stats["matched"] += 1

    return stats



def normalize_stem(value: str) -> str:
    value = clean_value(value).replace("\\", "/")
    value = Path(value).name
    if "." in value:
        value = Path(value).stem
    return value.strip().lower()


def candidate_stems(*values: str) -> set[str]:
    result: set[str] = set()
    for value in values:
        stem = normalize_stem(value)
        if not stem:
            continue
        result.add(stem)
        if stem.startswith("commodity_"):
            result.add("commod_" + stem[len("commodity_"):])
        if stem.startswith("commod_"):
            result.add("commodity_" + stem[len("commod_"):])
        result.add(stem.replace("-", "_").replace(" ", "_"))
        result.add(stem.replace("_", ""))
    return {x for x in result if x}


def scan_3db_texture_names(data_root: Path) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    models_dir = data_root / "EQUIPMENT" / "MODELS"
    if not models_dir.exists():
        models_dir = data_root

    for file in models_dir.rglob("*.3db"):
        try:
            text = file.read_bytes().decode("latin1", errors="ignore")
        except Exception:
            continue

        tgas = re.findall(r"[\w./\\ -]+\.tga", text, flags=re.I)
        stems = {normalize_stem(tga) for tga in tgas if normalize_stem(tga)}
        if stems:
            mapping.setdefault(file.stem.lower(), set()).update(stems)

    return mapping


def scan_png_icons(conn: sqlite3.Connection, img_dir: Path, data_root: Path | None = None, debug: bool = False) -> dict[str, int]:
    """Link ready PNG files to item_details.icon_png.

    v20 matching is intentionally broad because Freelancer stores icon names in
    several places: goods nickname, equipment nickname, DA_archetype .3db,
    embedded .tga names, and sometimes short icon names.
    """
    stats = {"png_files": 0, "matched": 0, "details_created": 0, "unmatched": 0}

    if not img_dir.exists():
        print(f"[WARN] img folder not found: {img_dir}")
        return stats

    png_files = sorted([p for p in img_dir.glob("*.png") if p.is_file()])
    stats["png_files"] = len(png_files)

    if not png_files:
        print(f"[WARN] no png files in: {img_dir}")
        return stats

    data_root = data_root or ROOT
    model_to_tga = scan_3db_texture_names(data_root) if data_root and data_root.exists() else {}

    png_by_stem: dict[str, Path] = {}
    png_stems: list[str] = []

    for png in png_files:
        stem = normalize_stem(png.name)
        png_stems.append(stem)
        png_by_stem.setdefault(stem, png)
        for alt in candidate_stems(stem):
            png_by_stem.setdefault(alt, png)

    def web_rel(path: Path) -> str:
        try:
            return path.relative_to(ROOT / "fl_panel" / "static").as_posix()
        except ValueError:
            return "img/items/" + path.name

    def add_detail_candidates(stems: set[str], detail_rows) -> None:
        for detail in detail_rows:
            for key in ("nickname", "display_name", "icon_source", "source_file"):
                value = clean_value(detail[key])
                stems.update(candidate_stems(value))

            raw_json = clean_value(detail["raw_json"])
            if raw_json:
                try:
                    raw = json.loads(raw_json)
                    if isinstance(raw, dict):
                        for value in raw.values():
                            if isinstance(value, list):
                                for one in value:
                                    stems.update(candidate_stems(clean_value(one)))
                            else:
                                stems.update(candidate_stems(clean_value(value)))
                except Exception:
                    pass

    def expand_model_candidates(stems: set[str]) -> None:
        for stem in list(stems):
            if stem in model_to_tga:
                stems.update(model_to_tga[stem])

    def fuzzy_match(stems: set[str]) -> Path | None:
        # Direct first.
        for stem in stems:
            if stem in png_by_stem:
                return png_by_stem[stem]

        # Then soft contains matching. Keep it conservative to avoid matching
        # tiny generic tokens like "li", "gun", "hp".
        filtered = [s for s in stems if len(s) >= 5]
        for stem in filtered:
            for png_stem in png_stems:
                if stem == png_stem:
                    return png_by_stem[png_stem]
                if len(stem) >= 7 and (stem in png_stem or png_stem in stem):
                    return png_by_stem[png_stem]
        return None

    item_rows = conn.execute(
        """
        SELECT
            hash,
            nickname,
            good_nickname,
            equipment_nickname,
            display_name,
            category
        FROM items
        """
    ).fetchall()

    matched_hashes: set[str] = set()
    debug_unmatched: list[tuple[str, str, list[str]]] = []
    debug_matched: list[tuple[str, str, str]] = []

    for row in item_rows:
        item_hash = clean_value(row["hash"])
        nickname = clean_value(row["nickname"])
        good_nickname = clean_value(row["good_nickname"])
        equipment_nickname = clean_value(row["equipment_nickname"])
        display_name = clean_value(row["display_name"])

        stems = candidate_stems(item_hash, nickname, good_nickname, equipment_nickname, display_name)

        detail_rows = conn.execute(
            """
            SELECT item_hash, nickname, display_name, icon_source, source_file, raw_json
            FROM item_details
            WHERE item_hash = ?
               OR lower(nickname) = lower(?)
               OR lower(nickname) = lower(?)
               OR lower(nickname) = lower(?)
               OR lower(display_name) = lower(?)
            """,
            (item_hash, nickname, good_nickname, equipment_nickname, display_name),
        ).fetchall()

        add_detail_candidates(stems, detail_rows)
        expand_model_candidates(stems)

        match = fuzzy_match(stems)

        if not match:
            stats["unmatched"] += 1
            if debug and len(debug_unmatched) < 30:
                debug_unmatched.append((item_hash, display_name or nickname or good_nickname or equipment_nickname, sorted(list(stems))[:12]))
            continue

        rel = web_rel(match)
        existing = conn.execute("SELECT item_hash FROM item_details WHERE item_hash = ?", (item_hash,)).fetchone()
        if not existing:
            stats["details_created"] += 1

        conn.execute(
            """
            INSERT INTO item_details
            (item_hash, nickname, display_name, icon_png, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_hash)
            DO UPDATE SET
                nickname = COALESCE(NULLIF(item_details.nickname, ''), excluded.nickname),
                display_name = COALESCE(NULLIF(item_details.display_name, ''), excluded.display_name),
                icon_png = excluded.icon_png,
                updated_at = excluded.updated_at
            """,
            (
                item_hash,
                nickname or good_nickname or equipment_nickname,
                display_name or nickname or good_nickname or equipment_nickname or item_hash,
                rel,
                now_iso(),
            ),
        )
        stats["matched"] += 1
        matched_hashes.add(item_hash)
        if debug and len(debug_matched) < 30:
            debug_matched.append((item_hash, display_name or nickname or good_nickname or equipment_nickname, rel))

    # Second pass: link item_details records that do not correspond to an items row.
    # This helps for custom/server-only items that came only from DATA scanning.
    extra_rows = conn.execute(
        """
        SELECT item_hash, nickname, display_name, icon_source, source_file, raw_json
        FROM item_details
        WHERE COALESCE(icon_png, '') = ''
        """
    ).fetchall()

    for detail in extra_rows:
        item_hash = clean_value(detail["item_hash"])
        if not item_hash or item_hash in matched_hashes:
            continue

        stems = candidate_stems(
            item_hash,
            clean_value(detail["nickname"]),
            clean_value(detail["display_name"]),
            clean_value(detail["icon_source"]),
            clean_value(detail["source_file"]),
        )
        add_detail_candidates(stems, [detail])
        expand_model_candidates(stems)

        match = fuzzy_match(stems)
        if not match:
            continue

        conn.execute(
            """
            UPDATE item_details
            SET icon_png = ?, updated_at = ?
            WHERE item_hash = ?
            """,
            (web_rel(match), now_iso(), item_hash),
        )

    if debug:
        print()
        print("ICON MATCH DEBUG")
        print("----------------")
        print("matched samples:")
        for item_hash, name, rel in debug_matched:
            print(f"  {item_hash} | {name} -> {rel}")

        print()
        print("unmatched samples:")
        for item_hash, name, stems in debug_unmatched:
            print(f"  {item_hash} | {name} | candidates={stems}")

        print()
        print("first png files:")
        for png in png_files[:30]:
            print(f"  {png.name}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import DATA item descriptions and try to convert TGA icons to PNG.")
    parser.add_argument("--data", required=True, help="Path to Freelancer DATA folder")
    parser.add_argument("--no-icons", action="store_true", help="Skip TGA to PNG conversion")
    parser.add_argument("--img", default="fl_panel/static/img/items", help="Folder with ready PNG item icons")
    parser.add_argument("--debug-icons", action="store_true", help="Print icon matching debug samples")
    args = parser.parse_args()

    data_root = Path(args.data)
    if not data_root.exists():
        raise SystemExit(f"DATA path not found: {data_root}")

    conn = connect()
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    updates = collect_ini_details(conn, data_root)

    icon_stats = {"converted": 0, "matched": 0, "skipped": 0}
    if not args.no_icons:
        icon_stats = convert_tga_icons(conn, data_root, ROOT / "fl_panel" / "static" / "generated_icons")

    png_stats = scan_png_icons(conn, Path(args.img), data_root, debug=args.debug_icons)

    conn.commit()
    conn.close()

    print("OK")
    print(f"item_details updated: {updates}")
    print(f"icons converted from tga: {icon_stats['converted']}")
    print(f"generated icons matched: {icon_stats['matched']}")
    print(f"generated icons skipped: {icon_stats['skipped']}")
    print(f"ready png files: {png_stats['png_files']}")
    print(f"ready png matched to items: {png_stats['matched']}")
    print(f"item_details created for png: {png_stats['details_created']}")
    print(f"items without png match: {png_stats['unmatched']}")


if __name__ == "__main__":
    main()
