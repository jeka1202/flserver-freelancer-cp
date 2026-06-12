FL ControlPanel Cyber Buttons v27

Исправление поверх v26:
- Убран конфликт старых и новых стилей.
- Из CSS удалены прошлые v25/v26 cyber-эксперименты.
- В конце CSS оставлен один финальный блок v27.
- Кнопки теперь получают класс cybr-btn и HTML-структуру как в референсе:
  button.cybr-btn
    text
    span "_"
    span.cybr-btn__glitch
    span.cybr-btn__tag
- Обычные button/.tab псевдоэлементы сначала принудительно отключаются.
- Геометрия кнопок теперь только из референса: ровная кнопка, без skew/косины.
- Cache-bust:
  style.css?v=27
  tabs.js?v=27

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если браузер покажет старое:
  Ctrl+F5
