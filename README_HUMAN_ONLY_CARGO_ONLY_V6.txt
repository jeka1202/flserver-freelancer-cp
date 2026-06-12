FL ControlPanel Human-only Cargo-only v6

Исправление:
- Названия кораблей теперь тоже берутся из SQLite IONCROSS name_map.
- Если в ships.display_name осталось системное имя типа ku_gunboat, panel/cargo_service попробуют заново найти нормальное название в name_map.
- В UI больше не должен появляться технический nickname корабля.
- repository/gamedata теперь поверх старых IONCROSS TXT использует быстрый overlay из flpanel.db/name_map.

После замены обязательно выполнить:
  py -m fl_panel.import_game_data --root .
  py .\account_panel.py

Проверка конкретного корабля:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print(dict(c.execute('select hash,nickname,display_name from ships where nickname=?', ('ku_gunboat',)).fetchone() or {}))"

Если display_name всё ещё ku_gunboat, проверь есть ли он в name_map:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print(dict(c.execute('select token,nickname,display_name from name_map where lower(token)=lower(?) or lower(nickname)=lower(?)', ('ku_gunboat','ku_gunboat')).fetchone() or {}))"
