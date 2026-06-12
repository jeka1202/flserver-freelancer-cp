FL ControlPanel Per-Character Warehouse/Craft v12

Исправление поверх v11:
- Починен вход в кабинет, если в пароле или в сохранённых password-значениях есть не-ASCII символы.
- Ошибка была:
    TypeError: comparing strings with non-ASCII characters is not supported
- Причина:
    secrets.compare_digest(str, str) в Python работает только с ASCII-строками.
- Исправление:
    сравнение теперь идёт через UTF-8 bytes.

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если нужно обновить DATA/IONCROSS:
  py -m fl_panel.import_game_data --root "e:\[game]\freelancer\data" --ioncross "e:\[game]\freelancer\ioncross"
