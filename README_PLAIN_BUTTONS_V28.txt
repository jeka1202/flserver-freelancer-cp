FL ControlPanel Plain Buttons v28

Что сделано:
- Убраны cyber/glitch кнопки.
- Удалён JS, который оборачивал кнопки в cybr-btn.
- Вырезаны CSS-блоки v25/v26/v27, связанные с cyber-кнопками.
- Вырезан старый CTA/Freelancer стиль кнопок.
- Все кнопки теперь обычные браузерные.
- Вкладки .tab тоже обычные button без декоративного стиля.
- Добавлен cache-bust:
  style.css?v=28
  tabs.js?v=28

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если браузер покажет старый вид:
  Ctrl+F5
