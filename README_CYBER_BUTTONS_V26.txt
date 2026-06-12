FL ControlPanel Cyber Buttons v26

Исправление поверх v25:
- Агрессивно сброшены старые стили кнопок.
- Убраны старые skew/косые кнопки и старые стрелки через псевдоэлементы.
- Оставлена только новая cyber-геометрия из референса:
  ровная кнопка с нижним левым скосом и правым нижним вырезом.
- Текст кнопок больше не наклоняется.
- Цвета оставлены под общий стиль панели: синий/cyan + жёлтый hover/active.
- Добавлен cache-bust:
  style.css?v=26
  tabs.js?v=26

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если браузер покажет старые кнопки:
  ctrl+f5
