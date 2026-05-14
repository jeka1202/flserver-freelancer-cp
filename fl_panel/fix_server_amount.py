from pathlib import Path
import re

root = Path(__file__).resolve().parent
server_path = root / "fl_panel" / "server.py"

if not server_path.exists():
    raise SystemExit(f"Не найден файл: {server_path}")

text = server_path.read_text(encoding="utf-8")

# 1. Добавляем локальный парсер суммы прямо в server.py после импортов.
helper = 