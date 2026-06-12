FL ControlPanel Separated Hold/Warehouse v14

Исправление поверх v13:
- Вернул функцию render_craft_panel и вспомогательные функции крафта.
- В v13 при разделении вкладок "Трюм" и "Склад" был случайно вырезан блок рендера вкладки "Крафт".
- Из-за этого после логина сервер падал с:
    NameError: name 'render_craft_panel' is not defined

Структура вкладок:
1. Трюм корабля
   - содержимое корабля из .fl
2. Склад базы
   - личный SQLite-склад конкретного персонажа
3. Крафт
   - работает через личный склад базы

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если нужно обновить DATA:
  py -m fl_panel.import_game_data --root "e:\[game]\freelancer\data" --ioncross "e:\[game]\freelancer\ioncross"
