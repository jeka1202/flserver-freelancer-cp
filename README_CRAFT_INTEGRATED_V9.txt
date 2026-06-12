FL ControlPanel Craft Integrated v9

Что добавлено:
1. Новый модуль:
   fl_panel/craft.py

2. Новая вкладка в кабинете:
   Крафт

3. Новые таблицы SQLite:
   craft_sources
   craft_recipes
   craft_recipe_inputs
   craft_recipe_outputs
   craft_jobs
   craft_log

4. Крафт привязан к складу текущей базы/планеты:
   - ресурсы берутся из warehouses;
   - задание создаётся в craft_jobs;
   - после завершения результат добавляется обратно в warehouses;
   - .fl и FLHook пока не трогаются.

5. Автоимпорт рецептов из JSON при старте панели.
   Скрипт ищет:
   - craft/recipes.json
   - Craft/recipes.json
   - craft_system/recipes.json
   - recipes.json
   - fl_panel/data/craft_recipes.json

6. В архив добавлен пример:
   fl_panel/data/craft_recipes.example.json

Чтобы включить пример:
   переименуй craft_recipes.example.json в craft_recipes.json
   или создай свой craft/recipes.json.

Минимальный формат:
[
  {
    "code": "polymers_to_alloys",
    "name": "Polymers to Basic Alloys",
    "duration_seconds": 60,
    "inputs": {"commodity_polymers": 10},
    "outputs": {"commodity_basic_alloys": 1}
  }
]

Поддерживаются варианты:
- inputs / requires / requirements / cost / ingredients / resources
- outputs / result / results / products
- item может быть hash, nickname, good_nickname или equipment_nickname
- quantity/qty/count

После замены:
   py -m fl_panel.import_game_data --root "путь_к_DATA" --ioncross "путь_к_IONCROSS"
   py .\account_panel.py --accounts "путь_к_Accts\MultiPlayer" --ioncross "путь_к_IONCROSS"

Проверка таблиц:
   py -c "import sqlite3; c=sqlite3.connect('fl_panel/data/flpanel.db'); print(c.execute('select count(*) from craft_recipes').fetchone()[0]); print(c.execute('select count(*) from craft_jobs').fetchone()[0])"

Важно:
GitHub code search по репозиторию сейчас не индексируется, поэтому этот модуль сделан как интеграция в текущую последнюю v8-версию панели и умеет импортировать твой recipes.json, если положить его в один из путей выше.
