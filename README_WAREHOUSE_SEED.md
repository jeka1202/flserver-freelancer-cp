# base_warehouse_full_seed

В архиве склад базы со всеми предметами, которые встречаются в craft_recipes.json.

Количество каждого предмета:
  1 000 000

Всего уникальных предметов:
  189

Файлы:
  base_warehouse_full.json  — основной файл склада
  base_warehouse_full.sql   — SQL-шаблон для SQLite
  import_base_warehouse.py  — удобный импорт в flpanel.db

Рекомендуемый импорт:

1. Распакуй архив в корень панели, рядом с account_panel.py.

2. Запусти импорт. Пример:

   py import_base_warehouse.py ^
     --db "fl_panel/data/flpanel.db" ^
     --json "base_warehouse_full.json" ^
     --account-id "23-XXXXXXXX" ^
     --location-hash "li01_01_base" ^
     --location-name "Manhattan"

Где взять location-hash:
  сейчас можно временно взять из панели/БД текущей базы персонажа.
  Позже сделаем кнопку "Заполнить текущий склад тестовыми ресурсами".

Проверка:

  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); print(c.execute('select count(*) from warehouses').fetchone()[0])"

