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



AUTH_CODE_SUFFIXES = ("givecash",)


def normalize_auth_code(value: str) -> str:
    """Normalize user-entered auth code without changing the actual code.

    Removes wrapping whitespace, NBSP/zero-width chars and spaces accidentally
    copied from chat/console. Keeps letters/digits/_/- intact.
    """
    text = str(value or "")
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    return "".join(text.strip().split())


def decode_fl_hex_code(value: str) -> str:
    """Decode FLHook-style Code=003100320033... values.

    The plugin writes numeric codes as UTF-16BE hex:
      00310032003300340035 -> 12345

    v82 also accepts:
      - plain text Code=12345
      - accidental spaces in hex string
      - UTF-16LE-like hex
    """
    raw = str(value or "").strip()
    compact = re.sub(r"[\s;#]+", "", raw)
    if compact.lower().startswith("0x"):
        compact = compact[2:]

    if compact and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        data = bytes.fromhex(compact)
        candidates: list[str] = []

        # Normal case from your example: 00 31 00 32 ... = UTF-16BE.
        for encoding in ("utf-16-be", "utf-16-le", "utf-8", "cp1251", "latin-1"):
            try:
                decoded = data.decode(encoding, errors="ignore").strip("\x00\r\n\t ")
            except Exception:
                decoded = ""
            decoded = normalize_auth_code(decoded)
            if decoded:
                candidates.append(decoded)

        # Manual fallback for byte pairs:
        # 00 31 00 32 -> 12
        # 31 00 32 00 -> 12
        if len(data) >= 2:
            be_ascii = "".join(chr(data[i + 1]) for i in range(0, len(data) - 1, 2) if data[i] == 0 and data[i + 1] != 0)
            le_ascii = "".join(chr(data[i]) for i in range(0, len(data) - 1, 2) if data[i] != 0 and data[i + 1] == 0)
            for candidate in (be_ascii, le_ascii):
                candidate = normalize_auth_code(candidate)
                if candidate:
                    candidates.append(candidate)

        # Prefer simple login-code characters.
        for candidate in candidates:
            if re.fullmatch(r"[0-9A-Za-z_-]+", candidate):
                return candidate

        if candidates:
            return candidates[0]

    return normalize_auth_code(raw)


def read_ini_setting(path: Path, key: str = "Code") -> str:
    if not path.exists():
        return ""

    text = read_text(path)
    key_lower = key.lower()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#", "[")) or "=" not in line:
            continue
        name, value = [part.strip() for part in line.split("=", 1)]
        if name.lower() == key_lower:
            # INI can be manually edited; tolerate accidental inline comments.
            value = value.strip()
            for separator in (" ;", " #"):
                if separator in value:
                    value = value.split(separator, 1)[0].strip()
            return value.strip().strip('"').strip("'")

    return ""


def character_auth_code_files(character_file: Path) -> list[Path]:
    """Return supported auth-code ini files for a character .fl file."""
    stem = character_file.stem
    parent = character_file.parent
    return [parent / f"{stem}-{suffix}.ini" for suffix in AUTH_CODE_SUFFIXES]


def character_code_candidates(character_file: Path) -> set[str]:
    """Read auth codes created by in-game commands.

    Supported files next to pilot .fl:
      <pilot>-givecash.ini

    Both use:
      [Settings]
      Code=00310032003300340035
    """
    candidates: set[str] = set()

    for path in character_auth_code_files(character_file):
        raw = read_ini_setting(path, "Code")
        if not raw:
            continue

        decoded = decode_fl_hex_code(raw)
        if decoded:
            candidates.add(normalize_auth_code(decoded))

        raw_clean = normalize_auth_code(raw)
        if raw_clean:
            candidates.add(raw_clean)

    return {candidate for candidate in candidates if candidate}


def character_auth_code_file_status(character_file: Path) -> list[dict[str, str | bool]]:
    result: list[dict[str, str | bool]] = []
    for path in character_auth_code_files(character_file):
        raw = read_ini_setting(path, "Code")
        result.append({
            "file": path.name,
            "exists": path.exists(),
            "has_code": bool(raw.strip()),
        })
    return result


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
