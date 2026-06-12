FL ControlPanel Item Images v19

Добавлена поддержка готовых PNG-картинок предметов.

Папка:
  fl_panel/static/img/items

Пример:
  fl_panel/static/img/items/commod_ale.png
  fl_panel/static/img/items/commod_ablativearmor.png
  fl_panel/static/img/items/alien_organisms.png

Команда импорта:
  py -m fl_panel.import_item_assets --data "e:\[upload]\github\flserver-freelancer-cp\data" --img "fl_panel/static/img/items"

Что делает:
1. Сканирует DATA/*.ini и переносит свойства в item_details.
2. Сканирует DATA/EQUIPMENT/MODELS/*.3db и достаёт имена встроенных *.tga.
3. Сканирует fl_panel/static/img/items/*.png.
4. Связывает картинки с предметами по hash/nickname/good_nickname/equipment_nickname, commodity_* <-> commod_*, icon_source и .3db -> .tga.

Интерфейс:
- В таблице склада показывается маленькая иконка.
- В окне предмета показывается большая иконка.

Запуск панели:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"
