from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

LOGICAL_BITS = 30
PHYSICAL_BITS = 32
FL_HASH_POLYNOMIAL = 0xA001 << (LOGICAL_BITS - 16)


def make_crc_table(polynomial: int) -> list[int]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            if value & 1:
                value = (value >> 1) ^ polynomial
            else:
                value >>= 1
            value &= 0xFFFFFFFF
        table.append(value)
    return table


CRC_TABLE = make_crc_table(FL_HASH_POLYNOMIAL)


def raw_fl_hash(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value >> 8) ^ CRC_TABLE[(value ^ byte) & 0xFF]
    return ((value >> 24) | ((value >> 8) & 0x0000FF00) | ((value << 8) & 0x00FF0000) | (value << 24)) & 0xFFFFFFFF


def nickname_hash(nickname: str) -> str:
    value = (raw_fl_hash(nickname.lower().encode()) >> (PHYSICAL_BITS - LOGICAL_BITS)) | 0x80000000
    return str(value)


def decode_fl_text(value: str) -> str:
    compact = value.strip().replace(" ", "")
    if len(compact) >= 4 and len(compact) % 4 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact).decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return value.strip()
    return value.strip()


def decode_account_password(raw: bytes) -> str:
    if len(raw) >= 2 and set(raw[1::2]) == {0x2E}:
        return "".join(chr(byte ^ 0x6E) for byte in raw[::2]).strip("\x00\r\n")
    text = raw.decode("utf-8", errors="ignore").strip()
    return decode_fl_text(text) if text else ""


def account_password_candidates(path: Path) -> set[str]:
    name_path = path / "name"
    if not name_path.exists():
        return set()
    raw = name_path.read_bytes()
    candidates = {decode_account_password(raw)}
    for encoding in ("utf-8", "latin-1"):
        candidates.add(raw.decode(encoding, errors="ignore").strip())
    text = read_text(name_path).strip()
    if text:
        candidates.add(text)
        candidates.add(decode_fl_text(text))
    return {candidate for candidate in candidates if candidate}


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def parse_fl(path: Path) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#", "[")) or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        data.setdefault(key, []).append(value)
    return data


def first(data: dict[str, list[str]], key: str, default: str = "") -> str:
    values = data.get(key) or []
    return values[0] if values else default


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")]


def intish(value: str, default: int = 0) -> int:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return default


def parse_amount(value: str) -> int:
    cleaned = re.sub(r"[\s\u00A0\u202F_.,']", "", str(value).strip())

    if not cleaned or not re.fullmatch(r"\d+", cleaned):
        return -1

    amount = int(cleaned)
    return amount if amount > 0 else -1


def format_seconds(value: int | float) -> str:
    seconds = int(value)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} дн.")
    if hours or days:
        parts.append(f"{hours} ч.")
    if minutes or hours or days:
        parts.append(f"{minutes} мин.")
    parts.append(f"{seconds} сек.")
    return " ".join(parts)


def file_time(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
