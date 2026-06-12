FL ControlPanel Item Images v21

Правка интерфейса окна предмета:
- окно предмета теперь переносится JS-ом в body и больше не должно обрезаться контейнером вкладки/карточки;
- окно сделано как правое боковое окно, ближе к оригинальному интерфейсу Freelancer;
- позиция: справа от основного блока, но внутри видимой области экрана;
- на 100% масштабе браузера окно должно открываться целиком без необходимости увеличивать/уменьшать масштаб;
- затемнение фона оставлено лёгким.

После замены:
  py .\account_panel.py --accounts "c:\users\jeka1202\documents\my games\freelancer\accts\multiplayer" --ioncross "e:\[game]\freelancer\ioncross"

Если картинки уже импортированы, повторно импортировать не обязательно.
Если нужно обновить связи картинок:
  py -m fl_panel.import_item_assets --data "e:\[upload]\github\flserver-freelancer-cp\data" --img "fl_panel/static/img/items" --no-icons
