FL ControlPanel Warehouse UI v16

Что изменено:
1. Склад больше не выглядит как огромная простыня.
   - вкладка ограничена высотой экрана;
   - таблица склада прокручивается внутри блока;
   - шапка таблицы закреплена.

2. Кнопка в каждой строке убрана.
   - теперь действия открываются кликом левой кнопкой мыши по строке предмета.

3. Добавлено всплывающее окно предмета:
   - Удалить -> подтверждение Да/Нет;
   - Передать -> ввод никнейма пилота и количества;
   - На корабль -> пока отключено до FLHook/addcargo;
   - Свойства -> описание/характеристики предмета.

4. Передача другому пилоту уже работает в DB-only режиме:
   - списывает предмет со склада отправителя;
   - создаёт/пополняет личный склад получателя на этой же базе;
   - .fl и FLHook не трогает.

5. Добавлен импорт характеристик/описаний/иконок:
   py -m fl_panel.import_item_assets --data "e:\[game]\freelancer\data"

   Скрипт:
   - сканирует DATA/*.ini;
   - переносит ids_name, ids_info, volume, mass, price, hit_pts и другие поля в item_details;
   - пытается конвертировать TGA в PNG через Pillow;
   - если Pillow не установлен, пропускает конвертацию и пишет подсказку.

Запуск панели:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Импорт DATA/IONCROSS:
  py -m fl_panel.import_game_data --root "e:\[game]\freelancer\data" --ioncross "e:\[game]\freelancer\ioncross"

Импорт свойств предметов:
  py -m fl_panel.import_item_assets --data "e:\[game]\freelancer\data"
