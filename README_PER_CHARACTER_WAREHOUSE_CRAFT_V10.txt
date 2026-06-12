FL ControlPanel Per-Character Warehouse/Craft v10

Главное исправление:
- Склады и крафт теперь изолированы не только по account_id, но и по character_file.
- Если в одном аккаунте 23-xxxx два персонажа, их склады на Manhattan / любой базе НЕ пересекаются.
- Крафт-очереди тоже отдельные для каждого персонажа.

Ключ владения:
  account_id + character_file + location_hash + item_hash

Что изменено:
  fl_panel/warehouse.py
  fl_panel/craft.py
  fl_panel/db.py
  fl_panel/views.py

Миграция:
- При первом запуске старая таблица warehouses будет перестроена.
- Старые общие складские записи не будут показаны реальным персонажам.
- Они сохраняются с character_file="__legacy_shared__", чтобы не дать одному пилоту забрать склад другого.

После замены:
  py -m fl_panel.import_game_data --root "путь_к_DATA" --ioncross "путь_к_IONCROSS"
  py .\account_panel.py --accounts "путь_к_Accts\MultiPlayer" --ioncross "путь_к_IONCROSS"

Проверка структуры:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); print(c.execute('pragma table_info(warehouses)').fetchall())"

Проверка складов:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print([dict(r) for r in c.execute('select account_id, character_file, character_name, location_name, count(*) rows from warehouses group by account_id, character_file, location_hash').fetchall()])"

Важно:
- Трансфер между персонажами позже будет отдельной операцией.
- Самопроизвольного общего склада на аккаунт больше нет.
