FLHook money integration для панели

Что изменилось:
- Добавлен fl_panel/flhook_client.py
- fl_panel/repository.py теперь:
  - если пилот онлайн, меняет деньги через FLHook командой addcash;
  - если пилот оффлайн или FLHook выключен, использует старый файловый режим;
  - bank.ini всё равно меняется файлово, потому что это внешний банк панели.

Настройка FLHook socket через переменные окружения PowerShell:

$env:FLHOOK_HOST="127.0.0.1"
$env:FLHOOK_PORT="1919"
$env:FLHOOK_TIMEOUT="3"

Если у socket есть пароль:
$env:FLHOOK_PASSWORD="твой_пароль"
$env:FLHOOK_AUTH_COMMAND="pass"

Потом запуск:
py .\account_panel.py

Если FLHOOK_PORT не задан — интеграция выключена и всё работает по-старому.

Важно:
- В FLHook командах консоли используются имена без слеша:
  getcash <charname>
  addcash <charname> <amount>
  setcash <charname> <amount>
- Для онлайн-пилота .fl напрямую не перезаписывается.
