FL ControlPanel Cargo Tab + IONCROSS human-readable names
=========================================================

Что изменено:
- импортёр DATA теперь также читает папку IONCROSS/GAMEDATA_*.txt;
- в SQLite добавлено поле display_name для items/ships/locations;
- cargo tab и cargo_probe показывают человеко-читаемые названия из IONCROSS;
- системные nickname/hash остаются второй строкой для отладки.

Пример:
  2211307011 = ge_s_cm_03_ammo, Adv. Countermeasure Ammo

После замены файлов ОБЯЗАТЕЛЬНО обнови БД:

  py -m fl_panel.import_game_data --root .

Если IONCROSS лежит нестандартно:

  py -m fl_panel.import_game_data --root . --ioncross .\IONCROSS

Проверка конкретного предмета:

  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; r=c.execute('select hash,nickname,display_name from items where hash=?', ('2211307011',)).fetchone(); print(dict(r) if r else 'not found')"

Проверка cargo:

  py -m fl_panel.cargo_probe ".\Accts\MultiPlayer\23-xxxx\pilot.fl"

Запуск панели:

  py .\account_panel.py
