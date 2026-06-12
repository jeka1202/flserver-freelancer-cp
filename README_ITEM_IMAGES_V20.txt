FL ControlPanel Item Images v20

Исправление поверх v19:
- Усилен алгоритм связывания PNG с предметами.
- Теперь он использует:
  - hash
  - nickname
  - good_nickname
  - equipment_nickname
  - display_name
  - item_details.icon_source
  - item_details.source_file
  - item_details.raw_json
  - .3db filename -> embedded .tga filename
  - commodity_* <-> commod_* alias
  - мягкое contains-сопоставление для длинных имён

Повторный импорт картинок:
  py -m fl_panel.import_item_assets --data "e:\[upload]\github\flserver-freelancer-cp\data" --img "fl_panel/static/img/items" --no-icons

С отладкой:
  py -m fl_panel.import_item_assets --data "e:\[upload]\github\flserver-freelancer-cp\data" --img "fl_panel/static/img/items" --no-icons --debug-icons

Важно:
- --no-icons лучше использовать, если PNG уже лежат в fl_panel/static/img/items.
- Тогда скрипт не будет пытаться заново конвертировать TGA, а только привяжет готовые PNG к БД.

Запуск панели:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"
