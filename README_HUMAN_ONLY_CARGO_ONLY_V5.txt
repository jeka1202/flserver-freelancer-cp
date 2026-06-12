FL ControlPanel Human-only Cargo-only v5

Исправления поверх v4:
1. Убрано предупреждение Python:
   SyntaxWarning: "\s" is an invalid escape sequence
2. Строка IONCROSS sync теперь понятнее:
   imported=0 total=2842
   Это значит: новых импортированных строк сейчас нет, но в БД уже есть 2842 записи.

Важно:
changed=0 skipped=20 imported=0 — это нормально.
Это означает, что файлы IONCROSS не изменились, поэтому они не переимпортировались.

Установка:
1. Распаковать в корень проекта с заменой.
2. Запустить:
   py -m fl_panel.import_game_data --root .
   py .\account_panel.py
