from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cargo_service import analyze_cargo
from .fl_ini_parser import first, iter_ini_sections


def parse_character(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    data: dict[str, list[str]] = {}

    for section, values in iter_ini_sections(path):
        for key, value_list in values.items():
            data.setdefault(key, []).extend(value_list)

    return data


def ascii_bar(value: float, limit: float, width: int = 28) -> str:
    if limit <= 0:
        return "[" + "?" * width + "]"
    ratio = max(0.0, min(1.0, value / limit))
    filled = int(round(ratio * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def item_display_name(row: dict) -> str:
    return str(row.get("display_name") or row.get("name") or "Неизвестный предмет")


def print_group(title: str, rows: list[dict], show_volume: bool = True, debug: bool = False) -> None:
    if not rows:
        return

    print()
    print(title)
    print("-" * len(title))

    for row in rows:
        name = item_display_name(row)
        if show_volume:
            line = (
                f"{row['count']:>6}  "
                f"vol={row['volume']:<6g} "
                f"total={row['total_volume']:<8g} "
                f"{name}"
            )
        else:
            line = f"{row['count']:>6}  {name}"

        if debug:
            line += f"  [{row.get('hash', '')} / {row.get('nickname', '')} / {row.get('good_nickname', '')}]"

        print(line)


def print_summary(summary: dict, debug: bool = False) -> None:
    if not summary.get("available"):
        print("Cargo DB unavailable:", summary.get("error", "unknown error"))
        for note in summary.get("notes", []):
            print("*", note)
        return

    ship = summary["ship"]
    ship_name = summary.get("ship_display_name") or (ship["display_name"] if ship and "display_name" in ship.keys() else "Неизвестный корабль")

    print(f"SHIP: {ship_name}")
    if ship and debug:
        print(f"DEBUG: nickname={ship['nickname']} hash={ship['hash']} type={ship['ship_type']} mass={ship['mass']}")

    print()
    print("CAPACITY")
    print("--------")
    print(f"Hold:             {summary['hold_used']:g} / {summary['hold_size']}  free={summary['hold_free']}  {summary['hold_pct']}%")
    print(f"                  {ascii_bar(summary['hold_used'], summary['hold_size'])}")

    print(
        f"Nanobots:         {summary['nanobots']} / {summary['effective_nanobot_limit']}  "
        f"free={summary['nanobot_free']}  "
        f"{summary['nanobot_pct']}%"
    )
    if debug:
        print(f"                  ship_limit={summary['ship_nanobot_limit']}")
    print(f"                  {ascii_bar(summary['nanobots'], summary['effective_nanobot_limit'])}")

    print(
        f"Shield batteries: {summary['shield_batteries']} / {summary['effective_shield_battery_limit']}  "
        f"free={summary['shield_battery_free']}  "
        f"{summary['shield_battery_pct']}%"
    )
    if debug:
        print(f"                  ship_limit={summary['ship_shield_battery_limit']}")
    print(f"                  {ascii_bar(summary['shield_batteries'], summary['effective_shield_battery_limit'])}")

    print(f"Ammo count:       {summary['ammo_count']}")
    print(f"Zero equipment:   {summary['zero_equipment_count']}")
    print(f"Cargo mass:       {summary['total_mass']:g}")

    if summary.get("notes"):
        print()
        print("NOTES")
        print("-----")
        for note in summary["notes"]:
            print("* " + note)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Freelancer character cargo and hold usage")
    parser.add_argument("character_file", help="Путь к .fl персонажа")
    parser.add_argument("--json", action="store_true", help="Вывести полный результат в JSON")
    parser.add_argument("--debug", action="store_true", help="Показать технические hash/nickname")
    parser.add_argument("--all", action="store_true", help="Показать даже пустые группы")
    parser.add_argument("--strict-limits", action="store_true", help="Считать nanobot/battery limit из shiparch жёстким лимитом")
    args = parser.parse_args()

    data = parse_character(Path(args.character_file))
    summary = analyze_cargo(first(data, "ship_archetype"), data.get("cargo", []), strict_limits=args.strict_limits)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return

    print_summary(summary, debug=args.debug)

    groups = summary.get("groups", {})
    titles = {
        "hold": "HOLD CARGO",
        "nanobot": "NANOBOTS",
        "shield_battery": "SHIELD BATTERIES",
        "ammo": "AMMO / MUNITIONS",
        "equipment": "EQUIPMENT / ZERO-VOLUME",
        "unknown": "UNKNOWN",
    }

    for key, title in titles.items():
        rows = groups.get(key, [])
        if rows or args.all:
            print_group(title, rows, show_volume=(key == "hold"), debug=args.debug)

    print()
    print("DONE")


if __name__ == "__main__":
    main()
