from __future__ import annotations

from pathlib import Path

from .config import CATEGORY_LABELS, DATA_FILES, VISIT_TYPES
from .db import DB_PATH
from .utils import nickname_hash, read_text, split_csv


class GameItem:
    def __init__(self, code: str, nickname: str, name: str, category: str) -> None:
        self.code = code
        self.nickname = nickname
        self.name = name
        self.category = category


class GameData:
    def __init__(self, directory: Path) -> None:
        self.by_category: dict[str, dict[str, GameItem]] = {}
        self.by_code: dict[str, GameItem] = {}
        self.by_nickname: dict[str, GameItem] = {}
        self.load(directory)
        self.load_sqlite_names()

    def load(self, directory: Path) -> None:
        for category, filename in DATA_FILES.items():
            items: dict[str, GameItem] = {}
            path = directory / filename
            if not path.exists():
                self.by_category[category] = items
                continue
            for raw_line in read_text(path).splitlines():
                line = raw_line.strip()
                if not line or line.startswith(("#", ";")) or "=" not in line:
                    continue
                code, rest = [part.strip() for part in line.split("=", 1)]
                if category == "mapinfo" and code == "visit":
                    parts = split_csv(rest)
                    code = parts[0] if parts else rest.strip()
                    nickname = code
                    visit_type = parts[1] if len(parts) > 1 else ""
                    name = f"Отметка карты {code} ({VISIT_TYPES.get(visit_type, visit_type or 'тип неизвестен')})"
                else:
                    parts = [part.strip() for part in rest.split(",", 1)]
                    nickname = parts[0]
                    name = parts[1] if len(parts) > 1 and parts[1] else nickname
                item = GameItem(code=code, nickname=nickname, name=name, category=category)
                for lookup_code in {code, code.lower(), nickname, nickname.lower(), nickname_hash(code), nickname_hash(nickname)}:
                    items[lookup_code] = item
                    self.by_code[lookup_code] = item
                self.by_nickname[nickname.lower()] = item
            self.by_category[category] = items


    def load_sqlite_names(self) -> None:
        """Overlay human-readable names from flpanel.db/name_map.

        This fixes cases where an old IONCROSS file reader did not resolve a
        ship/base/equipment nickname, but the SQLite IONCROSS dictionary has it.
        """
        if not DB_PATH.exists():
            return

        try:
            import sqlite3

            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='name_map'"
            ).fetchone()

            if not table:
                conn.close()
                return

            rows = conn.execute(
                """
                SELECT token, hash, nickname, display_name, category
                FROM name_map
                WHERE display_name IS NOT NULL
                  AND display_name != ''
                """
            ).fetchall()
            conn.close()

            for row in rows:
                token = str(row["token"] or "").strip()
                code = str(row["hash"] or token).strip()
                nickname = str(row["nickname"] or token).strip()
                name = str(row["display_name"] or nickname).strip()
                category = str(row["category"] or "unknown").strip() or "unknown"

                if not token or not name:
                    continue

                item = GameItem(code=code, nickname=nickname, name=name, category=category)

                for lookup_code in {token, token.lower(), code, nickname, nickname.lower()}:
                    if lookup_code:
                        self.by_code[lookup_code] = item

                if nickname:
                    self.by_nickname[nickname.lower()] = item

        except Exception:
            # DB lookup is an enhancement. If it fails, the old file-based
            # resolver still works.
            return


    def resolve(self, token: str | None) -> dict[str, str]:
        token = (token or "").strip()
        item = self.by_code.get(token) or self.by_code.get(token.lower()) or self.by_nickname.get(token.lower())
        if item:
            return {
                "code": item.code,
                "nickname": item.nickname,
                "name": item.name,
                "category": item.category,
                "category_label": CATEGORY_LABELS.get(item.category, item.category),
            }
        return {"code": token, "nickname": token, "name": "Неизвестно", "category": "unknown", "category_label": CATEGORY_LABELS["unknown"]}
