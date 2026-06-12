FL ControlPanel Separated Hold/Warehouse v13

Главное изменение:
- Разделили понятия "Трюм" и "Склад".

Теперь в кабинете отдельные вкладки:
1. Трюм корабля
   - содержимое корабля пилота;
   - читается из .fl;
   - груз, батареи, нанороботы, боеприпасы, оборудование.

2. Склад базы
   - отдельное хранилище базы/планеты;
   - хранится в SQLite;
   - личный для конкретного персонажа;
   - ключ: account_id + character_file + location_hash.

3. Крафт
   - работает через личный склад базы;
   - ресурсы списываются со склада;
   - результат возвращается в склад.

Важно:
- Кнопки "В склад" пока остаются в безопасном тестовом режиме.
- Они не меняют .fl и не вызывают FLHook.
- Это только запись в SQLite-склад.

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если нужно обновить DATA:
  py -m fl_panel.import_game_data --root "e:\[game]\freelancer\data" --ioncross "e:\[game]\freelancer\ioncross"
