FL ControlPanel Warehouse Test v8

Что добавлено:
1. fl_panel/warehouse.py
2. Таблицы склада в SQLite:
   - warehouses
   - warehouse_log
3. Вкладка "Трюм / Склад" теперь показывает склад текущей базы/планеты.
4. Добавлены тестовые DB-only операции:
   - из строки трюма нажать "В склад"
   - из строки склада нажать "Убрать"

ВАЖНО:
На этом этапе операции склада безопасные:
- .fl персонажа НЕ меняется;
- FLHook НЕ вызывается;
- онлайн-пилот НЕ затрагивается;
- это только проверка логики складов и интерфейса.

После замены:
  py -m fl_panel.import_game_data --root .
  py .\account_panel.py

Проверка таблиц:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); print(c.execute('select count(*) from warehouses').fetchone()[0]); print(c.execute('select count(*) from warehouse_log').fetchone()[0])"

Дальше:
- заменим DB-only test_add/test_remove на реальные FLHook enumcargo/removecargo/addcargo;
- при переносе "корабль -> склад" будем сначала removecargo, потом запись в warehouse;
- при переносе "склад -> корабль" будем проверять свободный трюм и addcargo.
