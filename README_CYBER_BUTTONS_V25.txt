FL ControlPanel Cyber Buttons v25

Что изменено:
- Переделаны все обычные <button> и вкладки .tab под cyber/glitch стиль из референса.
- Цвета адаптированы под общий стиль панели Freelancer: тёмно-синий, cyan-свечение, жёлтый акцент активной кнопки.
- JS автоматически оборачивает текст кнопок в элементы:
  - cybr-btn__label
  - cybr-btn__cursor
  - cybr-btn__glitch
  - cybr-btn__tag
- Формы и действия кнопок не ломаются, меняется только визуальное содержимое кнопки.
- Добавлен cache-bust:
  - style.css?v=25
  - tabs.js?v=25

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если браузер покажет старые кнопки:
  ctrl+f5
