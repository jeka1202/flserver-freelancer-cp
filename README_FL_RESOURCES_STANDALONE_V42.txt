FL ControlPanel FL Resources Standalone v42

Главное изменение:
- Импорт строк из Freelancer\EXE больше НЕ запускается вместе с панелью.
- Это теперь отдельный временный скрипт для редкого обновления, например раз в месяц.
- Данные пишутся в отдельную БД:
  fl_panel/data/fl_resources.db

Панель запускается как раньше:
  py .\account_panel.py

Ручной запуск отдельного импортёра:
  py -m fl_panel.import_fl_resources --exe "e:\[game]\freelancer\exe" --data "e:\[game]\freelancer\data"

Тест на первых 50 записях:
  py -m fl_panel.import_fl_resources --exe "e:\[game]\freelancer\exe" --data "e:\[game]\freelancer\data" --limit 50

Своя отдельная БД:
  py -m fl_panel.import_fl_resources --exe "e:\[game]\freelancer\exe" --data "e:\[game]\freelancer\data" --db "e:\[game]\freelancer\fl_resources.db"

Что создаётся в fl_resources.db:
- resource_meta
- resource_dlls
- resource_strings
- resource_items
- resource_sync_log

Что собирается:
- DLL из EXE\freelancer.ini [Resources]
- ids_name / ids_info из DATA\*.ini
- display_name из ids_name
- description из ids_info
- базовые параметры предметов:
  nickname, category, price, volume, mass, hit_pts, icon, source_file

Важно:
- Основная БД панели fl_panel/data/flpanel.db этим скриптом НЕ трогается.
- Это именно отдельный кэш/справочник ресурсов.
- Чтение DLL работает через WinAPI, то есть запускать нужно на Windows.

Быстрая проверка после импорта:
  py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/fl_resources.db'); c.row_factory=sqlite3.Row; print(c.execute('select count(*) from resource_items').fetchone()[0]); print([dict(x) for x in c.execute(\"select nickname, display_name, substr(description,1,120) as descr from resource_items where display_name<>'' limit 5\")])"
