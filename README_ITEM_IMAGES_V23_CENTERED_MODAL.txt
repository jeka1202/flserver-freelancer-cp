FL ControlPanel Item Images v23

Правка окна предмета:
- окно предмета теперь принудительно открывается по центру окна браузера;
- убрана маленькая кнопка закрытия в правом верхнем углу окна предмета;
- закрытие остаётся кликом по затемнённому фону или клавишей Esc;
- добавлен cache-bust для style.css и tabs.js: ?v=23, чтобы браузер не держал старый CSS/JS.

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если браузер всё равно покажет старый вариант:
  ctrl+f5
или включи в DevTools -> Network -> Disable cache.
