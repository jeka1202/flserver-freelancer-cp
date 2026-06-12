Тестовый импорт DATA в SQLite

1. Распакуй архив в корень проекта:
   E:\[UPLOAD]\GitHub\flserver-freelancer-cp\

Должно появиться:
   fl_panel\db.py
   fl_panel\fl_ini_parser.py
   fl_panel\fl_hash.py
   fl_panel\import_game_data.py
   fl_panel\cargo_probe.py

2. Запусти импорт DATA:

   py -m fl_panel.import_game_data --root .

Будет создана БД:
   fl_panel\data\flpanel.db

3. Проверить конкретного персонажа:

   py -m fl_panel.cargo_probe ".\Accts\MultiPlayer\ACCOUNT_ID\CHARACTER.fl"

Что уже делает:
- импортирует корабли из DATA\SHIPS\shiparch.ini
- импортирует предметы из DATA\EQUIPMENT\*_good.ini и *_equip.ini
- импортирует базовые locations из DATA\UNIVERSE
- считает used/free hold для cargo строк персонажа

Пока это только тестовый read-only прототип.
