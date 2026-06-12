FL ControlPanel Reputation Fix v36

Исправлено:
- В render_cabinet было два блока reputation_rows.
- Первый блок создавал новую шкалу reputation_scale(...).
- Второй блок ниже перетирал его старым HTML вида:
  <td class="">0.9</td>
- Второй старый блок удалён.
- Теперь HTML должен содержать:
  rep-scale-wrap
  rep-bar-inline
  rep-fill-positive / rep-fill-negative
- Число справа оставлено белым через class='rep-number'.

Проверка в браузере:
  DevTools -> Elements -> Ctrl+F -> rep-bar-inline

После замены:
  py .\account_panel.py

В браузере:
  Ctrl+F5
