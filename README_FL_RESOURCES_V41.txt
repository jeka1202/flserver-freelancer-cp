FL ControlPanel Freelancer EXE Resources v41

Добавлено:
- fl_panel/fl_resources.py
- fl_panel/import_fl_resources.py
- автоматический sync ресурсов из папки Freelancer\EXE при запуске панели

Что делает:
1. Ищет freelancer.ini в папке EXE.
2. Читает секцию [Resources] и строки DLL = ...
3. Собирает список ресурсных DLL.
4. Для item_details берёт ids_name и ids_info.
5. Через WinAPI LoadStringW читает строки из DLL.
6. ids_name записывает в display_name.
7. ids_info записывает в description.
8. Обновляет item_details, items.display_name и name_map.display_name.
9. Создаёт диагностическую таблицу resource_strings.

Запуск панели:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross" --exe "e:\[game]\freelancer\exe"

Если --exe не указан, панель попробует сама найти EXE рядом с IONCROSS:
  e:\[game]\freelancer\IONCROSS -> e:\[game]\freelancer\EXE

Ручной запуск импорта:
  py -m fl_panel.import_fl_resources --exe "e:\[game]\freelancer\exe"

Тест на первых 20 предметах:
  py -m fl_panel.import_fl_resources --exe "e:\[game]\freelancer\exe" --limit 20

Важно:
- Чтение DLL работает на Windows через ctypes/WinAPI.
- На Linux/не-Windows модуль не упадёт, но winapi=False и строки не вытащит.
- Перед этим должен быть заполнен item_details через:
  py -m fl_panel.import_item_assets --data "путь\к\DATA" --img "fl_panel/static/img/items"

Проверка после импорта:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; r=c.execute(\"select nickname, display_name, description from item_details where description is not null and description<>'' limit 3\").fetchall(); print([dict(x) for x in r])"
