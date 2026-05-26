from pathlib import Path
import shutil
import sys


def main():
    # Папка, где лежит сам скрипт
    script_dir = Path(__file__).resolve().parent

<<<<<<< Updated upstream
    # Файл bank.ini рядом со скриптом
    source_file = script_dir / "bank.ini"
=======
    # Файл name рядом со скриптом
    source_file = script_dir / "name"
>>>>>>> Stashed changes

    # Папка Accts\MultiPlayer\
    multiplayer_dir = script_dir / "Accts" / "MultiPlayer"

    print(f"[INFO] Папка скрипта: {script_dir}")
    print(f"[INFO] Файл-источник: {source_file}")
    print(f"[INFO] Папка MultiPlayer: {multiplayer_dir}")

<<<<<<< Updated upstream
    # Проверяем файл bank.ini
    if not source_file.is_file():
        print("[ERROR] Файл 'bank.ini' не найден рядом со скриптом.")
=======
    # Проверяем файл name
    if not source_file.is_file():
        print("[ERROR] Файл 'name' не найден рядом со скриптом.")
>>>>>>> Stashed changes
        sys.exit(1)

    # Проверяем папку Accts\MultiPlayer
    if not multiplayer_dir.is_dir():
        print("[ERROR] Папка Accts\\MultiPlayer\\ не найдена.")
        sys.exit(1)

    # Ищем папки внутри Accts\MultiPlayer\
    player_dirs = [p for p in multiplayer_dir.iterdir() if p.is_dir()]

    if not player_dirs:
        print("[WARN] В папке Accts\\MultiPlayer\\ не найдено подпапок.")
        sys.exit(0)

    print(f"[OK] Найдено папок: {len(player_dirs)}")

    copied_count = 0

    for player_dir in player_dirs:
<<<<<<< Updated upstream
        target_file = player_dir / "bank.ini"
=======
        target_file = player_dir / "name"
>>>>>>> Stashed changes

        try:
            shutil.copy2(source_file, target_file)
            copied_count += 1
            print(f"[OK] Скопировано: {target_file}")

        except Exception as e:
            print(f"[ERROR] Не удалось скопировать в папку: {player_dir}")
            print(f"        Причина: {e}")

    print()
    print(f"[DONE] Готово. Успешно скопировано в папок: {copied_count}")


if __name__ == "__main__":
    main()