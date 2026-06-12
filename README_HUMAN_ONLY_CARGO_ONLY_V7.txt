FL ControlPanel Human-only Cargo-only v7

Главное исправление:
- В .fl аккаунтах корабли часто записаны без префикса:
    ku_gunboat
- В IONCROSS эти же корабли часто идут с префиксом:
    dsy_ku_gunboat

Теперь при импорте создаётся alias:
    ku_gunboat -> dsy_ku_gunboat

В БД это помечается в отдельной таблице:
    ioncross_aliases

Также alias добавляется в name_map, чтобы обычный поиск по ku_gunboat сразу возвращал человеко-читаемое имя.

После замены обязательно:
    py -m fl_panel.import_game_data --root .
    py .\account_panel.py

Проверка alias:
    py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print(dict(c.execute('select alias_token,target_token,display_name,alias_type,note from ioncross_aliases where alias_token=?', ('ku_gunboat',)).fetchone() or {}))"

Проверка name_map:
    py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print(dict(c.execute('select token,nickname,display_name from name_map where token=?', ('ku_gunboat',)).fetchone() or {}))"

При старте панели будет видно:
    IONCROSS sync: files=20 changed=0 skipped=20 imported=0 total=2842 aliases=...
