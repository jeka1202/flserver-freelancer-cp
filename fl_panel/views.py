from __future__ import annotations

import html
import json
from typing import Any

from .config import STATIC_DIR
from .repository import money


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="/static/style.css"><body><main class="wrap">{body}<p class="footer">Freelancer Account Panel · клиентская часть показывает только персонажа после входа · админская логика отдельно в /admin</p></main><script src="/static/tabs.js"></script></body></html>""".encode()


def render_login(repo, message: str = "") -> bytes:
    stats = repo.public_stats()
    content = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    message_html = f'<p class="pill negative">{esc(message)}</p>' if message else ""
    content = content.replace("{{message}}", message_html)
    content = content.replace("{{characters}}", str(stats["characters"]))
    content = content.replace("{{gamedata_items}}", str(stats["gamedata_items"]))
    return content.encode()


def item_table(items: list[dict[str, str]], empty: str, third_label: str = "Кол-во / слот") -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(i['name'])}<br><span class='muted small'>{esc(i['nickname'])}</span></td><td>{esc(i.get('category',''))}</td><td>{esc(i.get('count') or i.get('hardpoint') or '—')}</td></tr>" for i in items)
    return f"<table><thead><tr><th>Название</th><th>Тип</th><th>{esc(third_label)}</th></tr></thead><tbody>{rows}</tbody></table>"


def nav_table(items: list[dict[str, str]], empty: str) -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(item['name'])}</td><td>{esc(item['nickname'])}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Название</th><th>Код</th></tr></thead><tbody>{rows}</tbody></table>"


def raw_visit_table(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>Нет visit-записей.</p>"
    rows = "".join(f"<tr><td>{esc(item['name'])}<br><span class='muted small'>{esc(item['nickname'])}</span></td><td>{esc(item['type'])}</td><td>{esc(item['code'])}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Объект</th><th>Тип</th><th>Код</th></tr></thead><tbody>{rows}</tbody></table>"


def crafting_table(recipes: list[dict[str, Any]]) -> str:
    if not recipes:
        return "<p class='muted'>Рецепты не найдены. Проверьте crafting_recipes.json.</p>"
    rows = []
    for recipe in recipes:
        ingredients = "".join(
            f"<li class='{'' if part['available'] >= part['amount'] else 'negative'}'>{esc(part['item']['name'])}: {part['available']}/{part['amount']}</li>"
            for part in recipe['ingredients']
        )
        button = "<button>Создать</button>" if recipe["can_craft"] else "<button disabled>Не хватает ресурсов</button>"
        rows.append(
            f"<tr><td><b>{esc(recipe['result']['name'])} x{recipe['amount']}</b><br><span class='muted small'>{esc(recipe['result']['nickname'])}</span></td>"
            f"<td>{esc(recipe['station'])}<br><span class='muted small'>уровень {esc(recipe['tier'])}</span></td>"
            f"<td><ul class='craft-list'>{ingredients}</ul></td>"
            f"<td><form method='post' action='/craft'><input type='hidden' name='recipe_id' value='{esc(recipe['id'])}'>{button}</form></td></tr>"
        )
    return f"<table><thead><tr><th>Результат</th><th>Станция</th><th>Компоненты</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_cabinet(repo: Any, account: dict[str, Any], char: dict[str, Any], message: str = "", error: str = "") -> bytes:
    top_factions = "".join(f"<span class='pill'>{esc(h['name'])}: {esc(h['reputation'])}</span>" for h in char["houses"][:8])
    nav = char["navigation"]
    raw = esc(json.dumps(char["raw_fields"], ensure_ascii=False, indent=2))
    recipes = repo.crafting_recipes_for(char)
    notice = f'<p class="pill money">{esc(message)}</p>' if message else f'<p class="pill negative">{esc(error)}</p>' if error else ""
    finance_notice_class = "money" if message else "negative" if error else ""
    finance_notice = f'<p id="finance-message" class="pill {finance_notice_class}">{esc(message or error)}</p>' if (message or error) else '<p id="finance-message" class="pill" hidden></p>'
    body = f"""
    <div class="card"><a class="pill" href="/logout">← выйти</a><span class="pill">Аккаунт: {esc(account['id'])}</span>{notice}<h1>{esc(char['name'])}</h1>
    <p class="ship">{esc(char['ship']['name'])}</p><p class="muted">{esc(char['system']['name'])} · {esc(char['base']['name'])} · ранг {esc(char['rank'])}</p></div>
    <div class="tabs"><button class="tab active" data-tab="inventory">Инвентарь</button><button class="tab" data-tab="equipment">Снаряжение</button><button class="tab" data-tab="stats">Статистика</button><button class="tab" data-tab="crafting">Крафт</button><button class="tab" data-tab="finance">Финансы</button><button class="tab" data-tab="reputation">Репутация</button><button class="tab" data-tab="navigation">Навигация</button></div>
    <section id="inventory" class="card tab-panel active"><h2>Инвентарь</h2>{item_table(char['cargo'], 'Груз отсутствует.', 'Кол-во')}</section>
    <section id="equipment" class="card tab-panel"><h2>Снаряжение</h2><div class="grid"><div class="stat"><b>{esc(char['ship']['name'])}</b>Корабль<br><span class="muted">{esc(char['ship']['nickname'])}</span></div><div class="stat"><b>{esc(char['base']['name'])}</b>Текущая база</div><div class="stat"><b>{esc(char['last_base']['name'])}</b>Последняя база</div></div><h3>Установлено на корабле</h3>{item_table(char['equip'], 'Нет установленного оборудования.', 'Слот')}<details><summary>Оборудование на базе/последнее сохранённое состояние</summary>{item_table(char['base_equip'], 'Нет данных base_equip.', 'Слот')}{item_table(char['base_cargo'], 'Нет данных base_cargo.', 'Кол-во')}</details></section>
    <section id="stats" class="card tab-panel"><h2>Статистика</h2><div class="grid"><div class="stat"><b>{esc(char['time_played'])}</b>Время в игре</div><div class="stat"><b>{esc(account['created'])}</b>Создан аккаунт</div><div class="stat"><b>{esc(char['created'])}</b>Создан персонаж / первая дата файла</div><div class="stat"><b>{esc(char['updated'])}</b>Последнее изменение</div><div class="stat"><b>{esc(char['kills'])}</b>Убийства</div><div class="stat"><b>{esc(char['deaths'])}</b>Смерти</div><div class="stat"><b>{esc(char['missions_success'])}/{esc(char['missions_failed'])}</b>Миссии успех/провал</div></div><details><summary>Все прочитанные сырые поля персонажа</summary><pre class="raw">{raw}</pre></details></section>
    <section id="crafting" class="card tab-panel"><h2>Крафт и производство</h2><p class="muted">Рецепты загружаются из <code>crafting_recipes.json</code>. Начальные ресурсы добываются из loot-полей астероидов и руды; дальше предметы производятся по уровням сложности.</p>{crafting_table(recipes)}</section>
    <section id="finance" class="card tab-panel"><h2>Финансы</h2>{finance_notice}<div class="grid"><div class="stat"><b id="character-money" class="money" data-balance="{esc(char['money'])}">{money(char['money'])}</b>Деньги персонажа</div><div class="stat"><b id="bank-money" class="money" data-balance="{esc(char['bank'])}">{money(char['bank'])}</b>Bank.ini</div></div><div class="two"><div class="stat"><h3>Перевод другому пилоту</h3><form method="post" action="/finance/transfer" data-ajax-finance="true"><label>Никнейм пилота-получателя</label><input name="target" placeholder="Имя персонажа" required><label>Сумма перевода</label><input name="amount" inputmode="numeric" pattern=\"[0-9\\s\\u00A0\\u202F_.,']+\" placeholder="100000" required><button>Перевести</button></form><p class="muted small">Сначала списывается игровой счёт персонажа. Если его не хватает, остаток берётся из bank.ini текущего аккаунта.</p></div><div class="stat"><h3>Банк персонажа</h3><form method="post" action="/finance/bank" data-ajax-finance="true"><label>Операция</label><select name="action"><option value="deposit">Перевести с персонажа в банк</option><option value="withdraw">Перевести из банка персонажу</option></select><label>Сумма</label><input name="amount" inputmode="numeric" pattern=\"[0-9\\s\\u00A0\\u202F_.,']+\" placeholder="50000" required><button>Выполнить</button></form><p class="muted small">Банк хранится в файле <code>bank.ini</code> одной строкой: просто число кредитов.</p></div></div></section>
    <section id="reputation" class="card tab-panel"><h2>Репутация</h2><p>{top_factions}</p><table><thead><tr><th>Фракция</th><th>Код</th><th>Отношение</th></tr></thead><tbody>{''.join(f'<tr><td>{esc(h["name"])}</td><td>{esc(h["code"])}</td><td class="{ "negative" if str(h["reputation"]).startswith("-") else "" }">{esc(h["reputation"])}</td></tr>' for h in char['houses'])}</tbody></table></section>
    <section id="navigation" class="card tab-panel"><h2>Навигация</h2><div class="grid"><div class="stat"><b>{esc(char['system']['name'])}</b>Текущая система</div><div class="stat"><b>{len(nav['systems'])}</b>Посещённых систем</div><div class="stat"><b>{len(nav['bases'])}</b>Посещённых баз</div><div class="stat"><b>{nav['raw_total']}</b>Отметок карты</div></div><div class="two"><div><h3>Посещённые системы</h3>{nav_table(nav['systems'], 'Нет записей sys_visited.')}</div><div><h3>Посещённые базы</h3>{nav_table(nav['bases'], 'Нет записей base_visited.')}</div></div><details><summary>Прыжковые дыры и сырые отметки карты</summary>{nav_table(nav['holes'], 'Нет записей holes_visited.')}<h3>Первые 250 visit-записей</h3>{raw_visit_table(nav['raw'])}</details></section>
    """
    return page(f"{char['name']} · Кабинет", body)


def render_admin(repo) -> bytes:
    rows = "".join(f"<tr><td><a href='/admin/account/{esc(account['id'])}'>{esc(account['id'])}</a></td><td>{account['character_count']}</td><td>{money(account['total_money'])}</td><td>{account['max_rank']}</td><td>{', '.join(esc(c['name']) for c in account['characters'][:5])}</td></tr>" for account in repo.accounts)
    body = f"""<div class="card"><h1>Админская зона</h1><p class="muted">Отдельная операторская логика: список аккаунтов, поиск и JSON. Клиентский вход находится на <a href="/">главной</a>.</p><div class="toolbar"><input class="search" id="q" placeholder="Поиск по аккаунту или персонажу..."><a class="pill" href="/api/accounts">JSON API</a></div><table id="accounts"><thead><tr><th>ID</th><th>Перс.</th><th>Кредиты</th><th>Max rank</th><th>Персонажи</th></tr></thead><tbody>{rows}</tbody></table></div><script>q.oninput=()=>{{const v=q.value.toLowerCase();document.querySelectorAll('#accounts tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(v)?'':'none')}};</script>"""
    return page("Админ · Freelancer Account Panel", body)


def render_admin_account(account: dict[str, Any]) -> bytes:
    rows = "".join(f"<tr><td>{esc(char['name'])}</td><td>{esc(char['file'])}</td><td>{esc(char['ship']['name'])}</td><td>{money(char['money'])}</td><td>{esc(char['system']['name'])}</td></tr>" for char in account["characters"])
    body = f"<div class='card'><a class='pill' href='/admin'>← админка</a><h1>{esc(account['id'])}</h1><table><thead><tr><th>Персонаж</th><th>Файл</th><th>Корабль</th><th>Кредиты</th><th>Система</th></tr></thead><tbody>{rows}</tbody></table></div>"
    return page(f"Админ · {account['id']}", body)
