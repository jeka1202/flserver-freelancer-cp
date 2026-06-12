FL ControlPanel Per-Character Warehouse/Craft v11

Исправление поверх v10:
- Исправлена миграция warehouses.
- Ошибка:
    Incorrect number of bindings supplied. The current statement uses 1, and there are 2 supplied.
  возникала при переходе старой таблицы склада на новую per-character схему, если в таблице уже была колонка character_file.

Что делать:
1. Распаковать архив с заменой файлов.
2. Запустить:
   py -m fl_panel.import_game_data --root "E:\[GAME]\Freelancer\DATA" --ioncross "E:\[GAME]\Freelancer\IONCROSS"
   py .\account_panel.py --accounts "C:\Users\Jeka1202\Documents\My Games\Freelancer\Accts\MultiPlayer" --ioncross "E:\[GAME]\Freelancer\IONCROSS"

Диагностика БД:
   py -m fl_panel.db_diag

Если IONCROSS пишет total=0, сделай принудительный переимпорт:
   py -m fl_panel.import_game_data --root "E:\[GAME]\Freelancer\DATA" --ioncross "E:\[GAME]\Freelancer\IONCROSS"
