from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def iter_ini_sections(path: Path):
    section_name: str | None = None
    values: dict[str, list[str]] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()

        if not line or line.startswith((";", "#")):
            continue

        if line.startswith("[") and line.endswith("]"):
            if section_name:
                yield section_name, values
            section_name = line[1:-1].strip()
            values = {}
            continue

        if section_name and "=" in line:
            key, value = [part.strip() for part in line.split("=", 1)]
            values.setdefault(key.lower(), []).append(value)

    if section_name:
        yield section_name, values


def first(values: dict[str, list[str]], key: str, default: str = "") -> str:
    item = values.get(key.lower()) or []
    return item[0] if item else default


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
