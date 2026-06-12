FL ControlPanel Human-only UI + Cargo-only inventory

Что изменено:
1. Из кабинета удалена вкладка "Инвентарь".
2. Главной вкладкой стала "Трюм / Склад".
3. В пользовательском интерфейсе скрыты технические hash, ID, nickname и системные имена:
   - cargo;
   - equipment;
   - navigation;
   - reputation;
   - ship card;
   - cargo tables.
4. Технические значения остались в БД и в коде для FLHook-команд.
5. cargo_probe теперь по умолчанию показывает человеко-читаемые имена.
   Для отладки добавлен флаг:
      --debug

Установка:
1. Распаковать архив в корень проекта с заменой файлов.
2. Обновить БД:
      py -m fl_panel.import_game_data --root .
3. Запустить панель:
      py .\account_panel.py

Проверка cargo_probe:
   py -m fl_panel.cargo_probe ".\Accts\MultiPlayer\23-xxxx\char.fl"

Проверка с техническими именами:
   py -m fl_panel.cargo_probe ".\Accts\MultiPlayer\23-xxxx\char.fl" --debug
