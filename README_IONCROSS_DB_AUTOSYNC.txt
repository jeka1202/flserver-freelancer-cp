FL ControlPanel — IONCROSS DB autosync

Что изменено:
1. IONCROSS/GAMEDATA_*.txt теперь импортируется в SQLite.
2. При старте панели выполняется быстрая проверка IONCROSS:
   - если файлы не изменились — пропускаются;
   - если изменились — переимпортируются в БД;
   - display_name в items/ships/locations обновляется автоматически.
3. Добавлены таблицы:
   - ioncross_sources
   - ioncross_entries
   - name_map уже используется как быстрый lookup hash/nickname -> display_name.

Почему в той же БД flpanel.db:
Так проще делать JOIN и не держать два соединения. Логически IONCROSS отделён отдельными таблицами.
Если потом захочешь — можно вынести эти таблицы в ioncross.db без изменения основной логики.

Установка:
1. Распаковать архив в корень проекта с заменой файлов.
2. Убедиться, что рядом лежат:
   DATA\
   IONCROSS\GAMEDATA_*.txt
   fl_panel\

3. Один раз обновить импорт DATA:
   py -m fl_panel.import_game_data --root .

4. Отдельно проверить IONCROSS sync:
   py -m fl_panel.ioncross_db --root .

5. Запуск панели:
   py .\account_panel.py

При запуске будет строка:
   IONCROSS sync: files=20 changed=0 skipped=20 ...

Примеры проверки:
   py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); print(c.execute('select count(*) from ioncross_entries').fetchone()[0])"

   py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); c.row_factory=sqlite3.Row; print(dict(c.execute('select * from name_map where token=?', ('2211307011',)).fetchone()))"
