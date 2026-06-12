FL ControlPanel Latest FULL + DB/Cargo Prototype
================================================

Это полный актуальный комплект панели, а не только DB-прототип.

Внутри:
- account_panel.py
- fl_panel/config.py
- fl_panel/server.py
- fl_panel/repository.py
- fl_panel/finance.py
- fl_panel/gamedata.py
- fl_panel/utils.py
- fl_panel/views.py
- fl_panel/flhook_client.py
- fl_panel/static/index.html
- fl_panel/static/style.css
- fl_panel/static/tabs.js
- fl_panel/db.py
- fl_panel/fl_ini_parser.py
- fl_panel/fl_hash.py
- fl_panel/import_game_data.py
- fl_panel/cargo_probe.py

Что уже есть:
1. Личный кабинет пилота.
2. Финансовые операции.
3. FLHook money integration:
   - онлайн-пилот: деньги через FLHook addcash/getcash;
   - оффлайн-пилот: старый файловый режим.
4. Sci-fi/Freelancer-like интерфейс.
5. SQLite-прототип под справочники DATA.
6. Импорт кораблей/предметов/локаций из DATA.
7. Тестовый расчёт трюма по cargo.

Установка:
1. Распаковать в корень проекта:
   flserver-freelancer-cp/

2. Если используешь локальный шрифт:
   положи agencyfbcyrillic.ttf сюда:
   fl_panel/static/agencyfbcyrillic.ttf

3. Запуск панели:
   py .\account_panel.py

4. Импорт DATA в SQLite:
   py -m fl_panel.import_game_data --root .

5. Проверка трюма конкретного персонажа:
   py -m fl_panel.cargo_probe ".\Accts\MultiPlayer\ACCOUNT_ID\CHARACTER.fl"

FLHook money integration:
Если хочешь включить изменение денег онлайн-пилота через FLHook socket:

PowerShell:
   $env:FLHOOK_HOST="127.0.0.1"
   $env:FLHOOK_PORT="1919"
   $env:FLHOOK_TIMEOUT="3"

Если нужен пароль:
   $env:FLHOOK_PASSWORD="твой_пароль"
   $env:FLHOOK_AUTH_COMMAND="pass"

Если FLHOOK_PORT не задан — панель работает в файловом режиме.

Следующий этап:
- Ship Cargo <-> Base Warehouse
- FLHook enumcargo/addcargo/removecargo
- EVE-like склада на каждой базе/планете
