FL ControlPanel Cargo Tab v1
============================

Что добавлено:
- новая вкладка "Трюм / Склад" в личном кабинете пилота;
- read-only расчёт трюма из SQLite БД;
- отображение Hold / Nanobots / Shield batteries / Ammo / Mass;
- отображение групп груза;
- cargo_probe теперь использует общий cargo_service.py.

Перед использованием:
1. Убедись, что БД создана:
   py -m fl_panel.import_game_data --root .

2. Запуск панели:
   py .\account_panel.py

3. Открыть:
   http://127.0.0.1:8080

Это пока read-only этап. Следующий шаг:
- Ship Cargo -> Base Warehouse
- Base Warehouse -> Ship Cargo
через FLHook команды:
  enumcargo
  removecargo
  addcargo
