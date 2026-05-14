from __future__ import annotations

import configparser
import re
from pathlib import Path

from .config import BANK_KEY, BANK_SECTION
from .utils import first, intish, parse_fl, read_text


def bank_ini_path(account_path: Path) -> Path:
    return account_path / "bank.ini"


def read_bank_balance(account_path: Path) -> int:
    path = bank_ini_path(account_path)
    if not path.exists():
        return 0
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section(BANK_SECTION):
        return 0
    for key in (BANK_KEY, "money", "cash", "credits"):
        if parser.has_option(BANK_SECTION, key):
            return max(0, intish(parser.get(BANK_SECTION, key), 0))
    return 0


def write_bank_balance(account_path: Path, balance: int) -> None:
    path = bank_ini_path(account_path)
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")
    if not parser.has_section(BANK_SECTION):
        parser.add_section(BANK_SECTION)
    parser.set(BANK_SECTION, BANK_KEY, str(max(0, balance)))
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def read_character_money(file_path: Path) -> int:
    return intish(first(parse_fl(file_path), "money"))


def write_character_money(file_path: Path, new_money: int) -> None:
    content = read_text(file_path)
    lines = content.splitlines(keepends=True)
    replaced = False
    for index, line in enumerate(lines):
        if re.match(r"^\s*money\s*=", line):
            ending = "\n" if line.endswith("\n") else ""
            if line.endswith("\r\n"):
                ending = "\r\n"
            lines[index] = f"money = {max(0, new_money)}{ending}"
            replaced = True
            break
    if not replaced:
        lines.append(f"money = {max(0, new_money)}\n")
    file_path.write_text("".join(lines), encoding="utf-8")
