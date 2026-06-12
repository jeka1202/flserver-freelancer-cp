"""Utility script plus compatibility shim for Python's stdlib ``copy`` module.

The repository historically has this file at the project root, so running Python
from the root shadows the standard-library module named ``copy``.  Re-export the
stdlib API first, then keep the original helper script behaviour under main().
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import sysconfig
from pathlib import Path

_stdlib_copy_path = Path(sysconfig.get_path("stdlib")) / "copy.py"
_spec = importlib.util.spec_from_file_location("_stdlib_copy", _stdlib_copy_path)
if _spec and _spec.loader:
    _stdlib_copy = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_stdlib_copy)
    Error = _stdlib_copy.Error
    copy = _stdlib_copy.copy
    deepcopy = _stdlib_copy.deepcopy
else:  # pragma: no cover - defensive fallback for unusual Python builds.
    class Error(Exception):
        pass

    def copy(value):
        copier = getattr(value, "copy", None)
        return copier() if copier else value

    def deepcopy(value, memo=None):
        return copy(value)


def main() -> None:
    """Copy a root helper file into every Accts/MultiPlayer account folder."""
    script_dir = Path(__file__).resolve().parent
    source_name = sys.argv[1] if len(sys.argv) > 1 else "bank.ini"
    source_file = script_dir / source_name
    multiplayer_dir = script_dir / "Accts" / "MultiPlayer"

    print(f"[INFO] Папка скрипта: {script_dir}")
    print(f"[INFO] Файл-источник: {source_file}")
    print(f"[INFO] Папка MultiPlayer: {multiplayer_dir}")

    if not source_file.is_file():
        print(f"[ERROR] Файл '{source_name}' не найден рядом со скриптом.")
        sys.exit(1)

    if not multiplayer_dir.is_dir():
        print("[ERROR] Папка Accts\\MultiPlayer\\ не найдена.")
        sys.exit(1)

    player_dirs = [path for path in multiplayer_dir.iterdir() if path.is_dir()]
    if not player_dirs:
        print("[WARN] В папке Accts\\MultiPlayer\\ не найдено подпапок.")
        sys.exit(0)

    print(f"[OK] Найдено папок: {len(player_dirs)}")
    copied_count = 0
    for player_dir in player_dirs:
        target_file = player_dir / source_name
        try:
            shutil.copy2(source_file, target_file)
            copied_count += 1
            print(f"[OK] Скопировано: {target_file}")
        except OSError as exc:
            print(f"[ERROR] Не удалось скопировать в папку: {player_dir}")
            print(f"        Причина: {exc}")

    print()
    print(f"[DONE] Готово. Успешно скопировано в папок: {copied_count}")


if __name__ == "__main__":
    main()
