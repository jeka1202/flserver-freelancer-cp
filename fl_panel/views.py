from __future__ import annotations

import html
import re
import json
import urllib.parse
from typing import Any

from .config import STATIC_DIR
from .repository import money
from .cargo_service import analyze_cargo
from .warehouse import current_base_warehouse, all_character_warehouses, get_warehouse_history
from .craft import current_craft_context
from .contracts import current_contract_context
from .finance_history import get_finance_history
from .admin_service import admin_pilot_url


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, body: str) -> bytes:
<<<<<<< Updated upstream
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="/static/style.css"><body><main class="wrap">{body}<p class="footer">Freelancer Account Panel · <a href="/game">браузерный прототип полёта</a> · клиентская часть показывает только персонажа после входа · админская логика отдельно в /admin</p></main><script src="/static/tabs.js"></script></body></html>""".encode()
=======
    language_switcher = """
    <div class="language-switcher" aria-label="Language">
      <span>LANG</span>
      <button type="button" data-lang-set="ru">RU</button>
      <button type="button" data-lang-set="en">EN</button>
    </div>
    """
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="/static/style.css?v=98"><body>{language_switcher}<main class="wrap">{body}<p class="footer">Freelancer Account Panel · клиентская часть показывает только персонажа после входа · админская логика отдельно в /admin</p></main><script src="/static/tabs.js?v=98"></script></body></html>""".encode()
>>>>>>> Stashed changes


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

    rows = "".join(
        "<tr>"
        f"<td>{esc(i.get('name') or '—')}</td>"
        f"<td>{esc(i.get('category','') or '—')}</td>"
        f"<td>{esc(i.get('count') or i.get('hardpoint') or '—')}</td>"
        "</tr>"
        for i in items
    )
    return f"<table><thead><tr><th>Название</th><th>Тип</th><th>{esc(third_label)}</th></tr></thead><tbody>{rows}</tbody></table>"


def meter(label: str, used: Any, limit: Any, free: Any, pct_value: Any, bar_value: Any, extra: str = "") -> str:
    return f"""
    <div class="stat cargo-meter-card">
      <b>{esc(used)} / {esc(limit)}</b>{esc(label)}
      <div class="cargo-meter"><span style="width:{esc(bar_value)}%"></span></div>
      <p class="muted small">Свободно: {esc(free)} · {esc(pct_value)}%{extra}</p>
    </div>
    """


def cargo_item_title(row: dict[str, Any]) -> str:
    # В пользовательском интерфейсе показываем только человеко-читаемое название.
    # hash/nickname/good_nickname остаются в БД и используются только для FLHook-команд.
    display_name = str(row.get("display_name") or "").strip()
    if not display_name:
        display_name = str(row.get("name") or "").strip()
    if not display_name:
        display_name = "Неизвестный предмет"
    return esc(display_name)


def cargo_type_label(row: dict[str, Any]) -> str:
    kind = str(row.get("kind") or "")
    category = str(row.get("category") or "")
    section = str(row.get("section") or "")

    labels = {
        "hold": "Груз",
        "nanobot": "Нанороботы",
        "shield_battery": "Батареи щита",
        "ammo": "Боеприпасы",
        "equipment": "Оборудование",
        "unknown": "Неизвестно",
        "commodity": "Товар",
        "equipment": "Оборудование",
        "munition": "Боеприпасы",
        "RepairKit": "Нанороботы",
        "ShieldBattery": "Батареи щита",
    }

    return labels.get(kind) or labels.get(section) or labels.get(category) or "Предмет"



def warehouse_add_form(row: dict[str, Any]) -> str:
    count = max(1, int(float(row.get("count") or 1)))
    item_hash = esc(row.get("hash") or "")
    return f"""
    <form method="post" action="/warehouse/add" class="inline-form to-warehouse-form" data-ajax-warehouse="true">
      <input type="hidden" name="item_hash" value="{item_hash}">
      <input name="amount" inputmode="numeric" pattern="[0-9]+" value="1" min="1" max="{esc(count)}" title="Количество">
      <button class="nowrap-btn" title="Перенести груз из трюма корабля на склад базы">На склад</button>
    </form>
    """


def warehouse_remove_form(row: dict[str, Any]) -> str:
    # Kept for compatibility. Actual warehouse UI uses one shared modal form.
    count = max(1, int(float(row.get("quantity") or 1)))
    item_hash = esc(row.get("item_hash") or "")
    return f"""
    <form method="post" action="/warehouse/remove" class="warehouse-action-form">
      <input type="hidden" name="item_hash" value="{item_hash}">
      <input name="amount" inputmode="numeric" pattern="[0-9]+" value="{esc(count)}" min="1" max="{esc(count)}">
      <button>Удалить</button>
    </form>
    """


def warehouse_actions(row: dict[str, Any]) -> str:
    # No visible button anymore: left click on the item row opens the modal.
    return ""


def warehouse_item_modal() -> str:
    return """
    <div id="warehouse-modal" class="warehouse-modal" hidden>
      <div class="warehouse-modal__shade" data-warehouse-close="1"></div>
      <div class="warehouse-modal__box" role="dialog" aria-modal="true">
        <div class="warehouse-modal__header">
          <div>
            <p class="muted small">Предмет склада</p>
            <h3 id="warehouse-modal-title">Предмет</h3>
          </div>
          <img id="warehouse-modal-icon" class="warehouse-modal__icon" alt="" hidden>
        </div>

        <div class="grid warehouse-modal__stats">
          <div class="stat"><b id="warehouse-modal-qty">0</b>На складе</div>
          <div class="stat"><b id="warehouse-modal-volume">0</b>Объём 1</div>
        </div>

        <div class="warehouse-modal__tabs">
          <button type="button" data-warehouse-pane="delete">Удалить</button>
          <button type="button" data-warehouse-pane="ship">В трюм</button>
          <button type="button" data-warehouse-pane="transfer">В склад пилота</button>
          <button type="button" data-warehouse-pane="contract">Выставить контракт</button>
        </div>

        <p id="warehouse-modal-notice" class="warehouse-modal__notice negative" hidden></p>

        <div class="warehouse-pane" id="warehouse-pane-delete" hidden>
          <p class="warning">Удалить предмет из SQLite-склада?</p>
          <form method="post" action="/warehouse/remove" class="modal-form" data-ajax-warehouse="true">
            <input type="hidden" name="item_hash" id="warehouse-delete-item">
            <input type="hidden" name="location_hash" id="warehouse-delete-location-hash">
            <input type="hidden" name="location_name" id="warehouse-delete-location-name">
            <input type="hidden" name="location_type" id="warehouse-delete-location-type">
            <label>Количество
              <input name="amount" id="warehouse-delete-amount" inputmode="numeric" pattern="[0-9]+" value="1" min="1" autocomplete="off" data-numeric-only="1">
            </label>
            <div class="modal-actions">
              <button type="submit">Да, удалить</button>
              <button type="button" data-warehouse-close="1">Нет</button>
            </div>
          </form>
        </div>

        <div class="warehouse-pane" id="warehouse-pane-transfer" hidden>
          <p class="muted small">Передача другому пилоту: только склад → склад. Корабль, .fl-файл и FLHook не используются.</p>
          <form method="post" action="/warehouse/transfer" class="modal-form" data-ajax-warehouse="true">
            <input type="hidden" name="item_hash" id="warehouse-transfer-item">
            <input type="hidden" name="location_hash" id="warehouse-transfer-location-hash">
            <input type="hidden" name="location_name" id="warehouse-transfer-location-name">
            <input type="hidden" name="location_type" id="warehouse-transfer-location-type">
            <label>Никнейм пилота
              <input name="target" id="warehouse-transfer-target" placeholder="Никнейм получателя">
            </label>
            <label>Количество
              <input name="amount" id="warehouse-transfer-amount" inputmode="numeric" pattern="[0-9]+" value="1" min="1" autocomplete="off" data-numeric-only="1">
            </label>
            <button type="submit">Передать в склад</button>
          </form>
        </div>


        <div class="warehouse-pane" id="warehouse-pane-contract" hidden>
          <p class="muted small">Создать контракт прямо из выбранного склада. Товар сразу будет снят со склада и зарезервирован в контракте.</p>
          <form method="post" action="/contracts/create" class="modal-form" id="warehouse-contract-form" data-ajax-warehouse="true">
            <input type="hidden" name="item_hash" id="warehouse-contract-item">
            <input type="hidden" name="location_hash" id="warehouse-contract-location-hash">
            <input type="hidden" name="location_name" id="warehouse-contract-location-name">
            <input type="hidden" name="location_type" id="warehouse-contract-location-type">
            <label>Количество
              <input name="quantity" id="warehouse-contract-quantity" inputmode="numeric" pattern="[0-9]+" value="1" min="1" autocomplete="off" data-numeric-only="1">
            </label>
            <label>Цена за весь контракт
              <input name="price" id="warehouse-contract-price" inputmode="numeric" pattern="[0-9]+" placeholder="100000" autocomplete="off" data-numeric-only="1" required>
            </label>
            <label>Срок
              <div class="contract-duration">
                <input name="lifetime_value" id="warehouse-contract-lifetime" inputmode="numeric" pattern="[0-9]+" value="24" min="1" autocomplete="off" data-numeric-only="1" required>
                <select name="lifetime_unit" id="warehouse-contract-lifetime-unit">
                  <option value="hours">часов</option>
                  <option value="days">дней</option>
                </select>
              </div>
            </label>
            <button type="submit">Выставить контракт</button>
          </form>
        </div>


        <div class="warehouse-pane" id="warehouse-pane-ship" hidden>
          <p class="warning" id="warehouse-ship-warning" hidden>В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0. Эквипмент и снаряжение пока не трогаем.</p>
          <form method="post" action="/warehouse/to-hold" class="modal-form" id="warehouse-ship-form" data-ajax-warehouse="true">
            <input type="hidden" name="item_hash" id="warehouse-ship-item">
            <input type="hidden" name="location_hash" id="warehouse-ship-location-hash">
            <input type="hidden" name="location_name" id="warehouse-ship-location-name">
            <input type="hidden" name="location_type" id="warehouse-ship-location-type">
            <label>Количество
              <input name="amount" id="warehouse-ship-amount" inputmode="numeric" pattern="[0-9]+" value="1" min="1" autocomplete="off" data-numeric-only="1">
            </label>
            <button type="submit">В трюм</button>
          </form>
        </div>
      </div>
    </div>
    """

def render_warehouse_panel(warehouse: dict[str, Any]) -> str:
    location = warehouse.get("location") or {}
    items = warehouse.get("items") or []
    location_name = location.get("name") or "Текущая база"
    character_name_text = warehouse.get("character_name") or "текущего пилота"

    if not items:
        table = "<p class='muted'>Склад этой базы пока пуст.</p>"
    else:
        rows = "".join(
            "<tr class='warehouse-row'"
            f" data-item-hash='{esc(item.get('item_hash') or '')}'"
            f" data-item-name='{esc(item.get('item_display_name') or 'Неизвестный предмет')}'"
            f" data-quantity='{esc(item.get('quantity') or 0)}'"
            f" data-volume='{esc(item.get('volume') or 0)}'"
            f" data-location-hash='{esc(item.get('location_hash') or '')}'"
            f" data-location-name='{esc(item.get('location_name') or '')}'"
            f" data-location-type='{esc(item.get('location_type') or 'base')}'"
            f" data-current-location='1'"
            f" data-cargo-eligible='{1 if item.get('cargo_eligible') else 0}'"
            f" data-cargo-reason='{esc(item.get('cargo_reject_reason') or '')}'"
            f" data-description='{esc(item.get('description') or 'Описание пока не импортировано. Запусти: py -m fl_panel.import_item_assets --data путь_к_DATA --img fl_panel/static/img/items')}'"
            f" data-icon='{esc(item.get('icon_png') or '')}'"
            " tabindex='0'>"
            f"<td class='item-name'>"
            f"{'<img class=\'warehouse-item-thumb\' src=\'/static/' + esc(item.get('icon_png')) + '\' alt=\'\'>' if item.get('icon_png') else '<span class=\'warehouse-item-thumb placeholder\'></span>'}"
            f"<span>{esc(item.get('item_display_name') or 'Неизвестный предмет')}</span>"
            f"</td>"
            f"<td class='num'>{esc(item.get('quantity') or 0)}</td>"
            f"<td class='num'>{esc(item.get('volume') or 0)}</td>"
            "</tr>"
            for item in items
        )
        table = f"""
        <div class="warehouse-scroll">
          <table class="warehouse-table">
            <thead>
              <tr>
                <th>Предмет</th>
                <th>Кол-во</th>
                <th>Объём 1</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        """

    return f"""
    {table}
    {warehouse_item_modal()}
    """

def cargo_rows_table(rows: list[dict[str, Any]], empty: str, show_volume: bool = False) -> str:
    if not rows:
        return f"<p class='muted'>{esc(empty)}</p>"

    if show_volume:
        rows_html = "".join(
            "<tr>"
            f"<td>{cargo_item_title(row)}</td>"
            f"<td>{esc(row['count'])}</td>"
            f"<td>{esc(row['volume'])}</td>"
            f"<td>{esc(row['total_volume'])}</td>"
            f"<td>{warehouse_add_form(row)}</td>"
            "</tr>"
            for row in rows
        )
        return f"<table><thead><tr><th>Предмет</th><th>Кол-во</th><th>Объём 1</th><th>Всего</th><th>Действие</th></tr></thead><tbody>{rows_html}</tbody></table>"

    rows_html = "".join(
        "<tr>"
        f"<td>{cargo_item_title(row)}</td>"
        f"<td>{esc(row['count'])}</td>"
        f"<td>{esc(cargo_type_label(row))}</td>"
        f"<td>{warehouse_add_form(row)}</td>"
        "</tr>"
        for row in rows
    )
    return f"<table><thead><tr><th>Предмет</th><th>Кол-во</th><th>Тип</th><th>Действие</th></tr></thead><tbody>{rows_html}</tbody></table>"


def render_hold_panel(summary: dict[str, Any]) -> str:
    if not summary.get("available"):
        notes = "".join(f"<p class='pill negative'>{esc(note)}</p>" for note in summary.get("notes", []))
        return f"<p class='pill negative'>БД груза недоступна: {esc(summary.get('error', 'unknown error'))}</p>{notes}"

    groups = summary.get("groups", {})
    visible_notes = [note for note in summary.get("notes", []) if "Принято как текущий запас персонажа" not in str(note)]
    notes = "".join(f"<p class='pill warning'>{esc(note)}</p>" for note in visible_notes)

    hold = meter("Трюм корабля", summary["hold_used"], summary["hold_size"], summary["hold_free"], summary["hold_pct"], summary["hold_bar"])
    nanobots = meter(
        "Нанороботы",
        summary["nanobots"],
        summary["effective_nanobot_limit"],
        summary["nanobot_free"],
        summary["nanobot_pct"],
        summary["nanobot_bar"],
    )
    batteries = meter(
        "Батареи щита",
        summary["shield_batteries"],
        summary["effective_shield_battery_limit"],
        summary["shield_battery_free"],
        summary["shield_battery_pct"],
        summary["shield_battery_bar"],
    )

    ship_name = summary.get("ship_display_name") or (summary.get("ship") or {}).get("display_name") or "—"

    return f"""
    <div class="stat">
      <b>{esc(ship_name)}</b>Корабль
      <p class="muted small">Во вкладке «Трюм корабля» показываются только товары / commodity, которые занимают место в трюме. Боеприпасы, нанороботы, батареи щита и остальная экипировка вынесены во вкладку «Снаряжение».</p>
    </div>

    <div class="grid cargo-summary cargo-summary-fixed">
      {hold}
      {nanobots}
      {batteries}
      <div class="stat"><b>{esc(summary['ammo_count'])}</b>Боеприпасы</div>
      <div class="stat"><b>{esc(summary['total_mass'])}</b>Масса груза</div>
    </div>

    {notes}

    <div>
      <h3>Товары / commodity в трюме</h3>
      {cargo_rows_table(groups.get('hold', []), 'Товаров в трюме нет.', True)}
    </div>
    """



def signed_quantity(value: Any) -> str:
    amount = int(value or 0)
    return f"+{amount}" if amount > 0 else str(amount)


def signed_quantity_class(value: Any) -> str:
    amount = int(value or 0)
    if amount > 0:
        return "money"
    if amount < 0:
        return "negative"
    return "muted"


def warehouse_operation_label(row: dict[str, Any]) -> str:
    labels = {
        "warehouse_add": "Добавлено в склад",
        "test_remove": "Удалено со склада",
        "to_hold": "Склад → трюм",
        "from_hold": "Трюм → склад",
        "transfer_out": "Передано пилоту",
        "transfer_in": "Получено от пилота",
        "flhook_to_hold": "Склад → трюм",
        "contract_create": "Контракт создан",
        "contract_buy": "Контракт куплен",
        "contract_cancel": "Контракт отменён",
    }
    return labels.get(str(row.get("operation") or ""), str(row.get("operation") or "Операция склада"))



def warehouse_counterparty(row: dict[str, Any]) -> str:
    operation = str(row.get("operation") or "")
    note = str(row.get("note") or "")

    if operation == "transfer_out":
        match = re.search(r"to pilot\s+(.+?)(?:\s*\(|\.|$)", note, flags=re.I)
        return f"Кому: {match.group(1).strip()}" if match else "Кому: пилоту"
    if operation == "transfer_in":
        match = re.search(r"from pilot\s+(.+?)(?:\s*\(|\.|$)", note, flags=re.I)
        return f"От: {match.group(1).strip()}" if match else "От: пилота"

    return "—"

def warehouse_clean_note(note: str) -> str:
    text = str(note or "")
    text = text.replace("warehouse_to_warehouse_only:", "склад → склад:")
    text = text.replace("DB-only prototype.", "")
    text = text.replace("Ship cargo was not changed.", "")
    text = text.replace("Added to personal SQLite warehouse.", "")
    text = text.replace("warehouse -> hold", "склад → трюм")
    text = text.replace("hold -> warehouse", "трюм → склад")
    return " ".join(text.split())


def render_warehouse_history_panel(history: list[dict[str, Any]]) -> str:
    if not history:
        table = "<p class='muted'>Истории операций склада на этой базе пока нет.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td>{esc(row.get('created_at') or '')}</td>"
            f"<td><b>{esc(warehouse_operation_label(row))}</b></td>"
            f"<td>{esc(row.get('item_display_name') or 'Предмет')}</td>"
            f"<td class='{esc(signed_quantity_class(row.get('quantity_delta')))}'>{esc(signed_quantity(row.get('quantity_delta')))}</td>"
            f"<td>{esc(row.get('location_name') or '')}</td>"
            f"<td>{esc(warehouse_counterparty(row))}</td>"
            "</tr>"
            for row in history
        )
        table = (
            "<div class='warehouse-history-scroll'>"
            "<table class='warehouse-history-table'>"
            "<thead><tr>"
            "<th>Дата</th><th>Операция</th><th>Предмет</th><th>Кол-во</th><th>Место</th><th>Пилот</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
            "</div>"
        )

    return f"""
    <div id="warehouse-history" class="stat warehouse-history">
      <h3>История операций склада</h3>
      <p class="muted small">История хранится отдельно для каждого пилота и текущей базы: склад → склад, склад ↔ трюм, удаления и пополнения склада.</p>
      {table}
    </div>
    """



def render_all_warehouses_panel(all_data: dict[str, Any]) -> str:
    locations = all_data.get("locations") or []
    current_token = ((all_data.get("current_location") or {}).get("token") or "")

    if not locations:
        locations_table = "<p class='muted'>У этого пилота пока нет складов на других базах или планетах.</p>"
        templates = ""
    else:
        rows = []
        templates_parts = []

        for idx, location_block in enumerate(locations):
            location = location_block.get("location") or {}
            items = location_block.get("items") or []
            location_hash = str(location.get("token") or "")
            location_name = str(location.get("name") or "Неизвестная база")
            location_type = str(location.get("type") or "base")
            is_current = "1" if location_hash == current_token else "0"

            rows.append(
                "<tr class='warehouse-location-row' tabindex='0' "
                f"data-template='warehouse-location-template-{esc(idx)}' "
                f"data-location-name='{esc(location_name)}' "
                f"data-location-hash='{esc(location_hash)}'>"
                f"<td><b>{esc(location_name)}</b>{' <span class=\"pill money\">текущая</span>' if is_current == '1' else ''}</td>"
                f"<td>{esc(location_type)}</td>"
                f"<td class='num'>{esc(location_block.get('item_rows') or len(items))}</td>"
                f"<td class='num'>{esc(location_block.get('total_quantity') or 0)}</td>"
                f"<td class='num'>{esc(round(float(location_block.get('total_volume') or 0), 2))}</td>"
                "</tr>"
            )

            item_rows = []
            for item in items:
                item_rows.append(
                    "<tr class='warehouse-location-item-row warehouse-row' tabindex='0' "
                    f"data-item-hash='{esc(item.get('item_hash') or '')}' "
                    f"data-item-name='{esc(item.get('item_display_name') or 'Неизвестный предмет')}' "
                    f"data-quantity='{esc(item.get('quantity') or 0)}' "
                    f"data-volume='{esc(item.get('volume') or 0)}' "
                    f"data-location-hash='{esc(location_hash)}' "
                    f"data-location-name='{esc(location_name)}' "
                    f"data-location-type='{esc(location_type)}' "
                    f"data-current-location='{is_current}' "
                    f"data-cargo-eligible='{1 if item.get('cargo_eligible') else 0}' "
                    f"data-cargo-reason='{esc(item.get('cargo_reject_reason') or '')}' "
                    f"data-description='{esc(item.get('description') or 'Описание пока не импортировано.')}' "
                    f"data-icon='{esc(item.get('icon_png') or '')}'>"
                    f"<td class='item-name'>"
                    f"{'<img class=\"warehouse-item-thumb\" src=\"/static/' + esc(item.get('icon_png')) + '\" alt=\"\">' if item.get('icon_png') else '<span class=\"warehouse-item-thumb placeholder\"></span>'}"
                    f"<span>{esc(item.get('item_display_name') or 'Неизвестный предмет')}</span></td>"
                    f"<td class='num'>{esc(item.get('quantity') or 0)}</td>"
                    f"<td class='num'>{esc(item.get('volume') or 0)}</td>"
                    "</tr>"
                )

            templates_parts.append(
                f"<template id='warehouse-location-template-{esc(idx)}'>"
                "<div class='warehouse-location-items'>"
                f"<p class='muted small'>Ресурсы на складе: {esc(location_name)}</p>"
                "<div class='warehouse-scroll'>"
                "<table class='warehouse-table'>"
                "<thead><tr><th>Предмет</th><th>Кол-во</th><th>Объём 1</th></tr></thead>"
                f"<tbody>{''.join(item_rows)}</tbody>"
                "</table>"
                "</div>"
                "</div>"
                "</template>"
            )

        locations_table = (
            "<div class='warehouse-history-scroll'>"
            "<table class='warehouse-locations-table warehouse-history-table'>"
            "<thead><tr><th>База / планета</th><th>Тип</th><th>Строк</th><th>Кол-во</th><th>Объём</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
        )
        templates = "".join(templates_parts)

    return f"""
    <div id="warehouse-all-locations" class="stat warehouse-history">
      <h3>Ваши склады</h3>
      <p class="muted small">Здесь показаны все базы и планеты, где у текущего пилота есть складские ресурсы. Нажми на базу, затем на ресурс для операций.</p>
      {locations_table}
      {templates}
    </div>

    <div id="warehouse-location-modal" class="warehouse-modal" hidden>
      <div class="warehouse-modal__shade" data-warehouse-location-close="1"></div>
      <div class="warehouse-modal__box" role="dialog" aria-modal="true">
        <button type="button" class="warehouse-modal__close" data-warehouse-location-close="1">×</button>
        <div class="warehouse-modal__header">
          <div>
            <p class="muted small">Ваш склад</p>
            <h3 id="warehouse-location-modal-title">Склад</h3>
          </div>
        </div>
        <div id="warehouse-location-modal-body"></div>
      </div>
    </div>
    """


def render_warehouse_tab_panel(warehouse: dict[str, Any], history: list[dict[str, Any]] | None = None, all_warehouses: dict[str, Any] | None = None) -> str:
    history = history or []
    all_warehouses = all_warehouses or {"locations": []}
    stock_html = render_warehouse_panel(warehouse)
    history_html = render_warehouse_history_panel(history)
    all_html = render_all_warehouses_panel(all_warehouses)
    stock_count = len(warehouse.get("items") or [])
    history_count = len(history)
    locations_count = len(all_warehouses.get("locations") or [])
    return f"""
    <div id="warehouse-content">
      <div class="warehouse-subtabs">
        <button type="button" class="warehouse-subtab active" data-warehouse-tab="stock">Склад <span class="warehouse-subtab-count">{esc(stock_count)}</span></button>
        <button type="button" class="warehouse-subtab" data-warehouse-tab="history">История <span class="warehouse-subtab-count">{esc(history_count)}</span></button>
        <button type="button" class="warehouse-subtab" data-warehouse-tab="all">Ваши склады <span class="warehouse-subtab-count">{esc(locations_count)}</span></button>
      </div>

      <div class="warehouse-subpanels">
        <div class="warehouse-subpanel active" data-warehouse-panel="stock">
          {stock_html}
        </div>
        <div class="warehouse-subpanel" data-warehouse-panel="history">
          {history_html}
        </div>
        <div class="warehouse-subpanel" data-warehouse-panel="all">
          {all_html}
        </div>
      </div>
    </div>
    """

def fmt_seconds(seconds: Any) -> str:
    seconds = int(float(seconds or 0))
    if seconds <= 0:
        return "мгновенно"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}д {hours:02d}:{minutes:02d}:{sec:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def craft_requirements_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "—"
    parts = []
    for item in items:
        cls = "money" if item.get("ok") else "negative"
        parts.append(
            f"<span class='pill {cls}'>{esc(item.get('name') or 'Предмет')}: "
            f"{esc(item.get('have', 0))}/{esc(item.get('need', 0))}</span>"
        )
    return "".join(parts)


def craft_outputs_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "—"
    return "".join(
        f"<span class='pill'>{esc(item.get('name') or 'Предмет')} ×{esc(item.get('quantity', 0))}</span>"
        for item in items
    )


def render_craft_panel(craft: dict[str, Any]) -> str:
    location = craft.get("location") or {}
    recipes = craft.get("recipes") or []
    jobs = craft.get("jobs") or []
    location_name = location.get("name") or "Текущая база"

    if jobs:
        jobs_rows = "".join(
            "<tr class='craft-job-row' "
            f"data-start-at='{esc(job.get('started_at'))}' "
            f"data-finish-at='{esc(job.get('finish_at'))}' "
            f"data-total-seconds='{esc(job.get('total_seconds'))}' "
            f"data-ready='{'1' if job.get('ready') else '0'}'>"
            f"<td><b>{esc(job.get('recipe_name'))}</b><p class='muted small'>Запущено ×{esc(job.get('quantity'))}</p></td>"
            f"<td>{esc(job.get('quantity'))}</td>"
            f"<td class='craft-job-status'>{'Готово' if job.get('ready') else 'В работе'}</td>"
            f"<td><div class='craft-progress'><span style='width:{esc(job.get('progress_pct', 0))}%'></span></div><p class='muted small craft-job-left'>{fmt_seconds(job.get('seconds_left'))}</p></td>"
            "<td class='craft-actions'>"
            f"<form method='post' action='/craft/claim' class='inline-form single-button craft-claim-form {'is-visible' if job.get('ready') else 'is-hidden'}' data-ajax-craft='true'>"
            f"<input type='hidden' name='job_id' value='{esc(job.get('id'))}'>"
            f"<button class='craft-ready-button'>Готово</button></form>"
            f"<form method='post' action='/craft/cancel' class='inline-form single-button craft-cancel-form {'is-hidden' if job.get('ready') else 'is-visible'}' data-ajax-craft='true'>"
            f"<input type='hidden' name='job_id' value='{esc(job.get('id'))}'>"
            f"<button>Отменить</button></form>"
            "</td>"
            "</tr>"
            for job in jobs
        )
        jobs_table = f"<table class='craft-jobs-table'><thead><tr><th>Задание</th><th>Кол-во</th><th>Статус</th><th>Прогресс</th><th>Действие</th></tr></thead><tbody>{jobs_rows}</tbody></table>"
    else:
        jobs_table = "<p class='muted'>Активных заданий крафта на этой базе нет.</p>"

    if recipes:
        recipe_rows = "".join(
            "<tr>"
            f"<td><b>{esc(recipe.get('name'))}</b><p class='muted small'>{esc(recipe.get('description') or '')}</p></td>"
            f"<td>{craft_requirements_text(recipe.get('requirements') or [])}</td>"
            f"<td>{craft_outputs_text(recipe.get('outputs') or [])}</td>"
            f"<td>{fmt_seconds(recipe.get('duration_seconds'))}</td>"
            "<td>"
            f"<form method='post' action='/craft/start' class='inline-form' data-ajax-craft='true'>"
            f"<input type='hidden' name='recipe_code' value='{esc(recipe.get('code'))}'>"
            f"<input name='quantity' inputmode='numeric' pattern='[0-9]+' value='1' min='1' title='Количество'>"
            f"<button {'disabled' if not recipe.get('can_make') else ''}>Создать</button>"
            "</form>"
            "</td>"
            "</tr>"
            for recipe in recipes
        )
        recipes_table = f"<table class='craft-recipes-table'><thead><tr><th>Рецепт</th><th>Нужно</th><th>Получится</th><th>Время</th><th>Запуск</th></tr></thead><tbody>{recipe_rows}</tbody></table>"
    else:
        recipes_table = """
        <p class='muted'>Рецепты не найдены. Положи recipes.json в папку craft рядом с account_panel.py или в fl_panel/data/craft_recipes.json.</p>
        <details>
          <summary>Минимальный формат recipes.json</summary>
          <pre class='raw'>[
  {
    "code": "polymers_to_parts",
    "name": "Example craft",
    "duration_seconds": 60,
    "inputs": {"commodity_polymers": 10},
    "outputs": {"commodity_basic_alloys": 1}
  }
]</pre>
        </details>
        """

    active_jobs_count = len(jobs)
    ready_jobs_count = sum(1 for job in jobs if job.get("ready"))

    return f"""
    <div id="craft-content">
      <p id="craft-message" class="pill" hidden></p>

      <div class="craft-subtabs" role="tablist" aria-label="Разделы крафта">
        <button type="button" class="craft-subtab active" data-craft-tab="recipes">Рецепты</button>
        <button type="button" class="craft-subtab" data-craft-tab="jobs">Активные крафты <span class="craft-subtab-count">{esc(active_jobs_count)}</span>{f"<span class='craft-ready-badge'>{esc(ready_jobs_count)}</span>" if ready_jobs_count else ""}</button>
      </div>

      <div class="craft-subpanels">
        <div class="craft-subpanel active" data-craft-panel="recipes">
          <h3>Рецепты</h3>
          {recipes_table}
        </div>

        <div class="craft-subpanel" data-craft-panel="jobs">
          <h3>Активные крафты</h3>
          {jobs_table}
        </div>
      </div>
    </div>
    """


def nav_table(items: list[dict[str, str]], empty: str) -> str:
    if not items:
        return f"<p class='muted'>{esc(empty)}</p>"
    rows = "".join(f"<tr><td>{esc(item.get('name') or '—')}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Название</th></tr></thead><tbody>{rows}</tbody></table>"


def raw_visit_table(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>Нет отметок карты.</p>"
    rows = "".join(f"<tr><td>{esc(item.get('name') or '—')}</td><td>{esc(item.get('type') or '—')}</td></tr>" for item in items)
    return f"<table><thead><tr><th>Объект</th><th>Тип</th></tr></thead><tbody>{rows}</tbody></table>"



def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return default


def reputation_scale(value: Any) -> str:
    rep = max(-1.0, min(1.0, _safe_float(value, 0.0)))
    fill_width = abs(rep) * 50.0
    rep_text = f"{rep:.3f}".rstrip('0').rstrip('.').replace('.', ',')
    if rep_text in ('-0', '+0', ''):
        rep_text = '0'

    # Inline styles are intentional: the indicator must be visible even if
    # browser cache ignores the latest CSS file.
    bar_style = (
        "position:relative;display:inline-block;width:300px;height:16px;"
        "vertical-align:middle;border:1px solid rgba(110,210,255,.38);"
        "background:linear-gradient(180deg,rgba(4,16,30,.96),rgba(8,28,46,.96));"
        "box-shadow:inset 0 0 0 1px rgba(0,0,0,.72),0 0 10px rgba(99,215,255,.18);"
        "overflow:hidden;"
    )

    center_style = (
        "position:absolute;top:-1px;bottom:-1px;left:50%;width:2px;"
        "transform:translateX(-50%);background:rgba(255,255,255,.95);"
        "box-shadow:0 0 8px rgba(255,255,255,.28);z-index:3;"
    )

    fill_html = ""
    if rep > 0:
        fill_style = (
            f"position:absolute;left:50%;top:2px;height:calc(100% - 4px);width:{fill_width:.2f}%;"
            "background:linear-gradient(90deg,rgba(245,245,245,.78),rgba(75,220,110,.96));"
            "box-shadow:0 0 8px rgba(75,220,110,.45);z-index:2;"
        )
        fill_html = f"<span class='rep-fill-positive' style='{fill_style}'></span>"
    elif rep < 0:
        fill_style = (
            f"position:absolute;right:50%;top:2px;height:calc(100% - 4px);width:{fill_width:.2f}%;"
            "background:linear-gradient(90deg,rgba(220,55,55,.96),rgba(245,245,245,.78));"
            "box-shadow:0 0 8px rgba(220,55,55,.45);z-index:2;"
        )
        fill_html = f"<span class='rep-fill-negative' style='{fill_style}'></span>"

    return (
        f"<div class='rep-scale-wrap' style='display:flex;align-items:center;justify-content:center;width:100%'>"
        f"<div class='rep-bar-inline' title='Репутация {esc(rep_text)}' style='{bar_style}'>"
        f"{fill_html}"
        f"<span style='{center_style}'></span>"
        f"</div>"
        f"</div>"
    )

def classify_base_entry(item: dict[str, str]) -> str:
    name = str(item.get('name') or '').strip().lower()
    nickname = str(item.get('nickname') or '').strip().lower()
    planet_hints = ('planet ', 'planet_', 'pl_', 'ga_planet', 'li0', 'br0')
    if name.startswith('planet ') or ' planet ' in f' {name} ' or 'планет' in name:
        return 'planet'
    if 'planet' in nickname or 'pl_' in nickname or '_planet' in nickname:
        return 'planet'
    if any(h in nickname for h in ('station', 'base', 'depot', 'trade', 'battleship', 'dock', 'jump')):
        return 'station'
    return 'station'


def navigation_three_columns(nav: dict[str, Any]) -> str:
    systems = nav.get('systems') or []
    bases = nav.get('bases') or []
    planets = [item for item in bases if classify_base_entry(item) == 'planet']
    stations = [item for item in bases if classify_base_entry(item) != 'planet']

    def col(title: str, items: list[dict[str, Any]], empty: str) -> str:
        if not items:
            body = f"<p class='muted'>{esc(empty)}</p>"
        else:
            rows = ''.join(f"<li>{esc(item.get('name') or '—')}</li>" for item in items)
            body = f"<ul class='nav-list'>{rows}</ul>"
        return f"<div class='nav-col'><h3>{esc(title)}</h3>{body}</div>"

    return f"<div class='nav-columns'>{col('Системы', systems, 'Нет посещённых систем.')}{col('Планеты', planets, 'Нет посещённых планет.')}{col('Станции / базы', stations, 'Нет посещённых станций и баз.')}</div>"


def equipment_groups_html(char: dict[str, Any], cargo_summary: dict[str, Any]) -> str:
    equip = char.get('equip') or []
    installed = {
        'weapons': [],
        'shields': [],
        'scanners': [],
        'engines': [],
        'other': [],
    }
    for item in equip:
        cat = str(item.get('category') or '').lower()
        name = str(item.get('name') or '')
        if any(k in cat for k in ('оружие', 'турели', 'турель', 'guns', 'turrets')):
            installed['weapons'].append(item)
        elif 'щит' in cat or 'shields' in cat:
            installed['shields'].append(item)
        elif 'сканер' in cat or 'scanners' in cat:
            installed['scanners'].append(item)
        elif 'двиг' in cat or 'engines' in cat or 'форсаж' in cat or 'thrusters' in cat:
            installed['engines'].append(item)
        else:
            installed['other'].append(item)

    groups = cargo_summary.get('groups', {})
    ammo_like = (groups.get('ammo') or []) + (groups.get('unknown') or [])
    nanobots = groups.get('nanobot') or []
    batteries = groups.get('shield_battery') or []

    parts = [
        "<div class='equipment-grid'>",
        f"<div><h3>Оружие / турели</h3>{item_table(installed['weapons'], 'Оружие не установлено.', 'Слот')}</div>",
        f"<div><h3>Щиты / защита</h3>{item_table(installed['shields'], 'Щитов и защитных модулей нет.', 'Слот')}</div>",
        f"<div><h3>Сканеры / электроника</h3>{item_table(installed['scanners'], 'Сканеры отсутствуют.', 'Слот')}</div>",
        f"<div><h3>Двигатели / форсаж</h3>{item_table(installed['engines'], 'Двигатели и форсаж не найдены.', 'Слот')}</div>",
        f"<div><h3>Прочее оборудование</h3>{item_table(installed['other'], 'Прочее оборудование не найдено.', 'Слот')}</div>",
        f"<div><h3>Боеприпасы / расходники</h3>{cargo_rows_table(ammo_like, 'Боеприпасов и расходников нет.')}</div>",
        f"<div><h3>Нанороботы</h3>{cargo_rows_table(nanobots, 'Нанороботов нет.')}</div>",
        f"<div><h3>Батареи щита</h3>{cargo_rows_table(batteries, 'Батарей щита нет.')}</div>",
        "</div>",
    ]
    return ''.join(parts)



def contract_status_label(status: str) -> str:
    labels = {
        "active": "Активен",
        "sold": "Продан",
        "expired": "Истёк",
        "cancelled": "Отменён",
    }
    return labels.get(str(status or ""), str(status or "—"))


def render_contract_create_form(warehouse: dict[str, Any]) -> str:
    items = warehouse.get("items") or []
    location = warehouse.get("location") or {}
    location_name = location.get("name") or "Текущая база"

    if not items:
        return f"<p class='muted'>На личном складе «{esc(location_name)}» нет предметов для выставления на контракт.</p>"

    options = "".join(
        f"<option value='{esc(item.get('item_hash'))}'>{esc(item.get('item_display_name'))} — на складе {esc(item.get('quantity'))} шт.</option>"
        for item in items
    )

    return f"""
    <form method="post" action="/contracts/create" class="contract-create-form">
      <div>
        <label>Предмет со склада</label>
        <select name="item_hash" required>{options}</select>
      </div>
      <div>
        <label>Количество</label>
        <input name="quantity" inputmode="numeric" pattern="[0-9]+" value="1" min="1" required>
      </div>
      <div>
        <label>Цена за весь контракт</label>
        <input name="price" inputmode="numeric" pattern="[0-9\\s\\u00A0\\u202F_.,']+" placeholder="100000" required>
      </div>
      <div>
        <label>Срок</label>
        <div class="contract-duration">
          <input name="lifetime_value" inputmode="numeric" pattern="[0-9]+" value="24" min="1" required>
          <select name="lifetime_unit">
            <option value="hours">часов</option>
            <option value="days">дней</option>
          </select>
        </div>
      </div>
      <button>Выставить контракт</button>
    </form>
    <p class="muted small">При выставлении товар сразу снимается со склада и резервируется в контракте. Если срок истечёт — товар вернётся на склад продавца.</p>
    """


def render_public_contracts(contracts: list[dict[str, Any]], current_account_id: str, current_character_file: str) -> str:
    if not contracts:
        return "<p class='muted'>Активных контрактов пока нет.</p>"

    rows = []
    for item in contracts:
        is_own = item.get("seller_account_id") == current_account_id and item.get("seller_character_file") == current_character_file
        action = (
            "<span class='pill'>Ваш контракт</span>"
            if is_own
            else (
                f"<form method='post' action='/contracts/buy' class='inline-form single-button'>"
                f"<input type='hidden' name='contract_id' value='{esc(item.get('id'))}'>"
                f"<button>Купить</button>"
                f"</form>"
            )
        )
        rows.append(
            "<tr>"
            f"<td><b>#{esc(item.get('id'))}</b></td>"
            f"<td>{esc(item.get('item_display_name'))}</td>"
            f"<td>{esc(item.get('quantity'))}</td>"
            f"<td>{esc(item.get('price_text'))}</td>"
            f"<td>{esc(item.get('seller_character_name'))}</td>"
            f"<td><b>{esc(item.get('location_name'))}</b><p class='muted small'>Товар будет лежать здесь. Проверь, что база/планета доступна по репутации.</p></td>"
            f"<td>{esc(item.get('left_text'))}<p class='muted small'>до {esc(item.get('expires_text'))}</p></td>"
            f"<td>{action}</td>"
            "</tr>"
        )

    return (
        "<table class='contracts-table'>"
        "<thead><tr><th>ID</th><th>Предмет</th><th>Кол-во</th><th>Цена</th><th>Продавец</th><th>База / планета</th><th>Осталось</th><th>Действие</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_my_contracts(contracts: list[dict[str, Any]]) -> str:
    if not contracts:
        return "<p class='muted'>У этого пилота ещё нет своих контрактов.</p>"

    rows = []
    for item in contracts:
        status = str(item.get("status") or "")
        cancel = ""
        if status == "active":
            cancel = (
                f"<form method='post' action='/contracts/cancel' class='inline-form single-button'>"
                f"<input type='hidden' name='contract_id' value='{esc(item.get('id'))}'>"
                f"<button>Отменить</button>"
                f"</form>"
            )

        rows.append(
            "<tr>"
            f"<td><b>#{esc(item.get('id'))}</b></td>"
            f"<td>{esc(contract_status_label(status))}</td>"
            f"<td>{esc(item.get('item_display_name'))}</td>"
            f"<td>{esc(item.get('quantity'))}</td>"
            f"<td>{esc(item.get('price_text'))}</td>"
            f"<td>{esc(item.get('location_name'))}</td>"
            f"<td>{esc(item.get('left_text') if status == 'active' else item.get('expires_text'))}</td>"
            f"<td>{cancel}</td>"
            "</tr>"
        )

    return (
        "<table class='contracts-table'>"
        "<thead><tr><th>ID</th><th>Статус</th><th>Предмет</th><th>Кол-во</th><th>Цена</th><th>База / планета</th><th>Срок</th><th>Действие</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_bought_contracts(contracts: list[dict[str, Any]]) -> str:
    if not contracts:
        return "<p class='muted'>Покупок по контрактам пока нет.</p>"

    rows = "".join(
        "<tr>"
        f"<td><b>#{esc(item.get('id'))}</b></td>"
        f"<td>{esc(item.get('item_display_name'))}</td>"
        f"<td>{esc(item.get('quantity'))}</td>"
        f"<td>{esc(item.get('price_text'))}</td>"
        f"<td>{esc(item.get('seller_character_name'))}</td>"
        f"<td>{esc(item.get('location_name'))}</td>"
        "</tr>"
        for item in contracts
    )

    return (
        "<table class='contracts-table'>"
        "<thead><tr><th>ID</th><th>Предмет</th><th>Кол-во</th><th>Цена</th><th>Продавец</th><th>Где лежит</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_contract_history(contracts: list[dict[str, Any]]) -> str:
    if not contracts:
        return "<p class='muted'>История контрактов пока пустая.</p>"

    rows = []
    for item in contracts:
        status = str(item.get("status") or "")
        role = "Покупка" if item.get("buyer_character_name") else "Мой контракт"
        if status == "sold" and item.get("buyer_character_name"):
            role = f"Продажа → {esc(item.get('buyer_character_name'))}"
        rows.append(
            "<tr>"
            f"<td><b>#{esc(item.get('id'))}</b></td>"
            f"<td>{esc(contract_status_label(status))}</td>"
            f"<td>{role}</td>"
            f"<td>{esc(item.get('item_display_name'))}</td>"
            f"<td>{esc(item.get('quantity'))}</td>"
            f"<td>{esc(item.get('price_text'))}</td>"
            f"<td>{esc(item.get('location_name'))}</td>"
            f"<td>{esc(item.get('expires_text'))}</td>"
            "</tr>"
        )

    return (
        "<table class='contracts-table'>"
        "<thead><tr><th>ID</th><th>Статус</th><th>Тип</th><th>Предмет</th><th>Кол-во</th><th>Цена</th><th>База / планета</th><th>Дата</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_contracts_panel(contracts: dict[str, Any], warehouse: dict[str, Any], account_id: str, character: dict[str, Any]) -> str:
    char_file = str(character.get("file") or "")
    location = warehouse.get("location") or {}
    location_name = location.get("name") or "Текущая база"

    history_contracts = []
    for row in contracts.get("mine") or []:
        if str(row.get("status") or "") != "active":
            history_contracts.append(row)
    history_contracts.extend(contracts.get("bought") or [])

    return f"""
    <div class="stat">
      <b>{esc(location_name)}</b>Текущая база / планета для выставления
      <p class="muted small">Важно: покупатель заберёт товар именно на этой базе/планете. В списке контрактов место указано отдельно, чтобы пилот заранее понимал, доступна ли ему эта локация по репутации.</p>
    </div>

    <details open class="contract-create-box">
      <summary>Выставить предмет со склада на продажу</summary>
      {render_contract_create_form(warehouse)}
    </details>

    <div class="contract-subtabs" role="tablist" aria-label="Разделы контрактов">
      <button type="button" class="contract-subtab active" data-contract-tab="server">Активные контракты сервера</button>
      <button type="button" class="contract-subtab" data-contract-tab="mine">Мои контракты</button>
      <button type="button" class="contract-subtab" data-contract-tab="history">История контрактов</button>
    </div>

    <div class="contracts-scroll">
      <div class="contract-subpanel active" data-contract-panel="server">
        <h3>Активные контракты сервера</h3>
        {render_public_contracts(contracts.get('public') or [], account_id, char_file)}
      </div>

      <div class="contract-subpanel" data-contract-panel="mine">
        <h3>Мои контракты</h3>
        {render_my_contracts(contracts.get('mine') or [])}
      </div>

      <div class="contract-subpanel" data-contract-panel="history">
        <h3>История контрактов</h3>
        {render_contract_history(history_contracts)}
      </div>
    </div>
    """



def finance_clean_note(note: Any) -> str:
    text = str(note or "").strip()
    if not text:
        return ""

    # Старые записи могли содержать технический режим. В интерфейсе это лишнее.
    text = re.sub(r"\s*\((через файл|через FLHook|via file|via FLHook)\)\.?", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*Режим:\s*(файловый режим|через файл|через FLHook|file mode|via file|via FLHook)\.?", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*Mode:\s*(file mode|via file|via FLHook)\.?", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\.\s*\.", ".", text)
    return text.strip()

def finance_operation_label(row: dict[str, Any]) -> str:
    operation = str(row.get("operation") or "")
    direction = str(row.get("direction") or "")

    if operation == "bank_deposit":
        return "Персонаж → банк"
    if operation == "bank_withdraw":
        return "Банк → персонаж"
    if operation == "pilot_transfer":
        if direction == "incoming":
            return "Входящий перевод"
        if direction == "outgoing":
            return "Исходящий перевод"
        return "Перевод пилоту"
    return operation or "Операция"


def signed_money(value: Any) -> str:
    amount = int(value or 0)
    if amount > 0:
        return "+" + money(amount)
    if amount < 0:
        return "−" + money(abs(amount))
    return "0"


def signed_money_class(value: Any) -> str:
    amount = int(value or 0)
    if amount > 0:
        return "money"
    if amount < 0:
        return "negative"
    return "muted"


def finance_counterparty(row: dict[str, Any]) -> str:
    operation = str(row.get("operation") or "")
    if operation in {"bank_deposit", "bank_withdraw"}:
        return "Свои счета"

    name = str(row.get("counterparty_character_name") or "").strip()
    return name or "—"


def render_finance_history_panel(history: list[dict[str, Any]]) -> str:
    if not history:
        table = "<p class='muted'>Финансовых операций у этого пилота пока нет.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td>{esc(row.get('created_at') or '')}</td>"
            f"<td><b>{esc(finance_operation_label(row))}</b></td>"
            f"<td class='{esc(signed_money_class(row.get('amount')))}'>{money(int(row.get('amount') or 0))}</td>"
            f"<td>{esc(finance_counterparty(row))}</td>"
            f"<td class='{esc(signed_money_class(row.get('character_delta')))}'>{esc(signed_money(row.get('character_delta')))}</td>"
            f"<td class='{esc(signed_money_class(row.get('bank_delta')))}'>{esc(signed_money(row.get('bank_delta')))}</td>"
            f"<td class='muted small'>{esc(finance_clean_note(row.get('note') or ''))}</td>"
            "</tr>"
            for row in history
        )
        table = (
            "<div class='finance-history-scroll'>"
            "<table class='finance-history-table'>"
            "<thead><tr>"
            "<th>Дата</th><th>Операция</th><th>Сумма</th><th>Кто</th><th>Персонаж</th><th>Банк</th><th>Примечание</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
            "</div>"
        )

    return f"""
    <div id="finance-history" class="stat finance-history">
      <h3>История финансовых операций</h3>
      <p class="muted small">История хранится отдельно для каждого пилота: входящие и исходящие переводы, а также переводы между персонажем и bank.ini.</p>
      {table}
    </div>
    """



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
    reputation_rows = ''.join(
        f"<tr><td>{esc(h['name'])}</td><td>{reputation_scale(h['reputation'])}</td><td class='rep-number'>{esc(str(h['reputation']).replace('.', ','))}</td></tr>"
        for h in char['houses']
    )
    nav = char["navigation"]
<<<<<<< Updated upstream
    raw = esc(json.dumps(char["raw_fields"], ensure_ascii=False, indent=2))
    recipes = repo.crafting_recipes_for(char)
=======
>>>>>>> Stashed changes
    notice = f'<p class="pill money">{esc(message)}</p>' if message else f'<p class="pill negative">{esc(error)}</p>' if error else ""
    finance_notice_class = "money" if message else "negative" if error else ""
    finance_notice = f'<p id="finance-message" class="pill {finance_notice_class}">{esc(message or error)}</p>' if (message or error) else '<p id="finance-message" class="pill" hidden></p>'
    cargo_summary = analyze_cargo(char.get("ship_token", char["ship"]["nickname"]), char.get("cargo_rows", []))
    warehouse = current_base_warehouse(account["id"], char)
    warehouse_history = get_warehouse_history(account["id"], char["file"], (warehouse.get("location") or {}).get("token", ""), limit=80)
    all_warehouses = all_character_warehouses(account["id"], char)
    craft_context = current_craft_context(account["id"], char)
    contracts_context = current_contract_context(account["id"], char)
    hold_html = render_hold_panel(cargo_summary)
    warehouse_html = render_warehouse_tab_panel(warehouse, warehouse_history, all_warehouses)
    craft_html = render_craft_panel(craft_context)
    contracts_html = render_contracts_panel(contracts_context, warehouse, account["id"], char)
    finance_history_html = render_finance_history_panel(get_finance_history(account["id"], char["file"], limit=80))

    body = f"""
<<<<<<< Updated upstream
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
=======
    <div class="card">
      <a class="pill" href="/logout">← выйти</a>
      <span class="pill">Кабинет пилота</span>
      {notice}
      <h1>{esc(char['name'])}</h1>
      <p class="ship">{esc(cargo_summary.get('ship_display_name') or char['ship']['name'])}</p>
      <p class="muted">{esc(char['system']['name'])} · {esc(char['base']['name'])} · ранг {esc(char['rank'])}</p>
    </div>

    <div class="tabs">
      <button class="tab active" data-tab="hold">Трюм корабля</button>
      <button class="tab" data-tab="warehouse">Склад базы</button>
      <button class="tab" data-tab="craft">Крафт</button>
      <button class="tab" data-tab="contracts">Контракты</button>
      <button class="tab" data-tab="equipment">Снаряжение</button>
      <button class="tab" data-tab="stats">Статистика</button>
      <button class="tab" data-tab="finance">Финансы</button>
      <button class="tab" data-tab="reputation">Репутация</button>
      <button class="tab" data-tab="navigation">Навигация</button>
    </div>

    <section id="hold" class="card tab-panel active">
      <h2>Трюм корабля</h2>
      <p class="muted">Трюм — это текущее содержимое корабля пилота. Оно читается из .fl-файла персонажа и показывает груз, боеприпасы, батареи, нанороботы и оборудование корабля.</p>
      <div id="hold-live-content">{hold_html}</div>
    </section>

    <section id="warehouse" class="card tab-panel">
      <h2>Склад базы</h2>
      <div id="warehouse-live-content">{warehouse_html}</div>
    </section>

    <section id="craft" class="card tab-panel">
      <h2>Крафт</h2>
      {craft_html}
    </section>

    <section id="contracts" class="card tab-panel">
      <h2>Контракты</h2>
      {contracts_html}
    </section>

    <section id="equipment" class="card tab-panel">
      <h2>Снаряжение</h2>
      <p class="muted">Здесь собрано всё, что не относится к обычному товару в трюме: вооружение, турели, щиты, сканеры, боеприпасы, ID пилота, нанороботы, батареи щита и прочая корабельная экипировка.</p>
      <div class="grid equipment-top-grid">
        <div class="stat"><b>{esc(cargo_summary.get('ship_display_name') or char['ship']['name'])}</b>Корабль</div>
        <div class="stat"><b>{esc(char['base']['name'])}</b>Текущая база</div>
        <div class="stat"><b>{esc(char['last_base']['name'])}</b>Последняя база</div>
        <div class="stat"><b>{esc(cargo_summary.get('nanobots', 0))}</b>Нанороботы</div>
        <div class="stat"><b>{esc(cargo_summary.get('shield_batteries', 0))}</b>Батареи щита</div>
      </div>
      {equipment_groups_html(char, cargo_summary)}
    </section>

    <section id="stats" class="card tab-panel">
      <h2>Статистика</h2>
      <div class="grid">
        <div class="stat"><b>{esc(char['time_played'])}</b>Время в игре</div>
        <div class="stat"><b>{esc(account['created'])}</b>Создан аккаунт</div>
        <div class="stat"><b>{esc(char['created'])}</b>Создан персонаж / первая дата файла</div>
        <div class="stat"><b>{esc(char['updated'])}</b>Последнее изменение</div>
        <div class="stat"><b>{esc(char['kills'])}</b>Убийства</div>
        <div class="stat"><b>{esc(char['deaths'])}</b>Смерти</div>
        <div class="stat"><b>{esc(char['missions_success'])}/{esc(char['missions_failed'])}</b>Миссии успех/провал</div>
      </div>
    </section>

    <section id="finance" class="card tab-panel">
      <h2>Финансы</h2>
      {finance_notice}
      <div class="grid">
        <div class="stat"><b id="character-money" class="money" data-balance="{esc(char['money'])}">{money(char['money'])}</b>Деньги персонажа</div>
        <div class="stat"><b id="bank-money" class="money" data-balance="{esc(char['bank'])}">{money(char['bank'])}</b>Банк аккаунта</div>
      </div>
      <div class="two">
        <div class="stat">
          <h3>Перевод другому пилоту</h3>
          <form method="post" action="/finance/transfer" data-ajax-finance="true">
            <label>Имя пилота-получателя</label>
            <input name="target" placeholder="Имя персонажа" required>
            <label>Сумма перевода</label>
            <input name="amount" inputmode="numeric" pattern="[0-9\\s\\u00A0\\u202F_.,']+" placeholder="100000" required>
            <button>Перевести</button>
          </form>
          <p class="muted small">Сначала списывается игровой счёт персонажа. Если его не хватает, остаток берётся из банка аккаунта.</p>
        </div>
        <div class="stat">
          <h3>Банк персонажа</h3>
          <form method="post" action="/finance/bank" data-ajax-finance="true">
            <label>Операция</label>
            <select name="action">
              <option value="deposit">Перевести с персонажа в банк</option>
              <option value="withdraw">Перевести из банка персонажу</option>
            </select>
            <label>Сумма</label>
            <input name="amount" inputmode="numeric" pattern="[0-9\\s\\u00A0\\u202F_.,']+" placeholder="50000" required>
            <button>Выполнить</button>
          </form>
          <p class="muted small">Банк аккаунта хранит кредиты отдельно от текущего корабля.</p>
        </div>
      </div>
      {finance_history_html}
    </section>

    <section id="reputation" class="card tab-panel">
      <h2>Репутация</h2>
      <p class="muted">Шкала слева направо: от красного (-1.0) через нейтральное белое (0.0) к зелёному (+1.0). Заливка идёт от центра: влево красным для отрицательной репутации, вправо зелёным для положительной.</p>
      <p>{top_factions}</p>
      <table class="reputation-table">
        <thead><tr><th>Фракция</th><th>Шкала</th><th>Значение</th></tr></thead>
        <tbody>{reputation_rows}</tbody>
      </table>
    </section>

    <section id="navigation" class="card tab-panel">
      <h2>Навигация</h2>
      <div class="grid navigation-top-grid">
        <div class="stat"><b>{esc(char['system']['name'])}</b>Текущая система</div>
        <div class="stat"><b>{len(nav['systems'])}</b>Систем</div>
        <div class="stat"><b>{len(nav['bases'])}</b>Планет / станций</div>
        <div class="stat"><b>{nav['raw_total']}</b>Отметок карты</div>
      </div>
      <p class="muted">Ниже показаны реально посещённые объекты: отдельно системы, отдельно планеты и станции/базы.</p>
      {navigation_three_columns(nav)}
      <details>
        <summary>Прыжковые дыры и сырые отметки карты</summary>
        {nav_table(nav['holes'], 'Нет записей прыжковых дыр.')}
        <h3>Первые 250 отметок карты</h3>
        {raw_visit_table(nav['raw'])}
      </details>
    </section>
>>>>>>> Stashed changes
    """
    return page(f"{char['name']} · Кабинет", body)




def render_admin_all_warehouses(all_data: dict[str, Any]) -> str:
    locations = all_data.get("locations") or []
    if not locations:
        return "<p class='muted'>Складов на базах/планетах пока нет.</p>"

    blocks = []
    for block in locations:
        location = block.get("location") or {}
        items = block.get("items") or []

        item_rows = "".join(
            "<tr>"
            f"<td class='item-name'>{'<img class=\"warehouse-item-thumb\" src=\"/static/' + esc(item.get('icon_png')) + '\" alt=\"\">' if item.get('icon_png') else '<span class=\"warehouse-item-thumb placeholder\"></span>'}<span>{esc(item.get('item_display_name') or 'Предмет')}</span></td>"
            f"<td class='num'>{esc(item.get('quantity') or 0)}</td>"
            f"<td class='num'>{esc(item.get('volume') or 0)}</td>"
            "</tr>"
            for item in items
        ) or "<tr><td colspan='3' class='muted'>Пусто</td></tr>"

        blocks.append(
            "<details class='admin-location-block' open>"
            f"<summary><b>{esc(location.get('name') or location.get('token') or 'База')}</b>"
            f" <span class='pill'>{esc(block.get('item_rows') or len(items))} строк</span>"
            f" <span class='pill'>{esc(block.get('total_quantity') or 0)} шт.</span>"
            f" <span class='pill'>{esc(round(float(block.get('total_volume') or 0), 2))} объём</span>"
            f"{' <span class=\"pill money\">текущая</span>' if block.get('is_current') else ''}</summary>"
            "<table class='admin-warehouse-table'>"
            "<thead><tr><th>Предмет</th><th>Кол-во</th><th>Объём 1</th></tr></thead>"
            f"<tbody>{item_rows}</tbody>"
            "</table>"
            "</details>"
        )

    return "".join(blocks)


def render_admin_online_table(online: dict[str, Any] | None) -> str:
    online = online or {"ok": False, "message": "Нет данных.", "players": []}
    players = online.get("players") or []

    if not players:
        rows = "<tr><td colspan='9' class='muted'>Онлайн-пилотов нет или FLHook не вернул список.</td></tr>"
    else:
        rows = "".join(
            "<tr>"
            f"<td>{('<a href=\"' + esc(row.get('url')) + '\">' + esc(row.get('name') or '—') + '</a>') if row.get('url') else esc(row.get('name') or '—')}</td>"
            f"<td>{esc(row.get('ip') or '—')}</td>"
            f"<td>{esc(row.get('system') or '—')}</td>"
            f"<td>{esc(row.get('base') or '—')}</td>"
            f"<td>{esc(row.get('ship') or '—')}</td>"
            f"<td>{esc(row.get('rank') or '—')}</td>"
            f"<td>{money(int(row.get('money') or 0)) if row.get('known') else '—'}</td>"
            f"<td>{esc(row.get('account_id') or '—')}</td>"
            f"<td class='muted small'>{esc(row.get('raw') or '')}</td>"
            "</tr>"
            for row in players
        )

    return f"""
    <div class="card admin-card">
      <h2>Онлайн-пилоты FLHook</h2>
      <p class="muted">{esc(online.get('message') or '')}</p>
      <div class="admin-table-scroll">
        <table id="admin-online-pilots">
          <thead>
            <tr>
              <th>Пилот</th>
              <th>IP</th>
              <th>Система</th>
              <th>База</th>
              <th>Корабль</th>
              <th>Ранг</th>
              <th>Кредиты</th>
              <th>Аккаунт</th>
              <th>Raw FLHook</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def render_admin_flhook_console(command_result: dict[str, Any] | None = None) -> str:
    result_html = ""
    modal_hidden = " hidden" if not command_result else ""
    if command_result:
        cls = "money" if command_result.get("ok") else "negative"
        result_html = (
            f"<p class='pill {cls}'>Команда: {esc(command_result.get('command') or '')}</p>"
            f"<pre class='admin-console-output'>{esc(command_result.get('text') or '')}</pre>"
        )

    return f"""
    <div id="admin-flhook-modal" class="admin-flhook-modal"{modal_hidden}>
      <div class="admin-flhook-modal__shade" data-admin-console-close="1"></div>
      <div class="admin-flhook-modal__box" role="dialog" aria-modal="true">
        <button type="button" class="warehouse-modal__close" data-admin-console-close="1">×</button>
        <h2>FLHook console</h2>
        <p class="muted">Команды выполняются через WPort FLHook. Например: <code>getplayers</code>, <code>getcash PilotName</code>, <code>enumcargo PilotName</code>.</p>
        <form method="post" action="/admin/flhook" class="admin-command-form">
          <input name="command" placeholder="getplayers" autocomplete="off" required>
          <button type="submit">Выполнить</button>
        </form>
        {result_html}
      </div>
    </div>
    """




def admin_location_options(character: dict[str, Any], all_warehouses: dict[str, Any]) -> str:
    current = all_warehouses.get("current_location") or {}
    locations = []
    seen = set()

    def add(location: dict[str, Any], label_suffix: str = "") -> None:
        token = str(location.get("token") or "").strip()
        if not token or token in seen:
            return
        seen.add(token)
        name = str(location.get("name") or token)
        loc_type = str(location.get("type") or "base")
        label = f"{name}{label_suffix}"
        locations.append((token, name, loc_type, label))

    add(current, " — текущая база")
    for block in all_warehouses.get("locations") or []:
        add(block.get("location") or {})

    return "".join(
        f"<option value='{esc(token)}' data-location-name='{esc(name)}' data-location-type='{esc(loc_type)}'>{esc(label)}</option>"
        for token, name, loc_type, label in locations
    )




def admin_clean_location_text(value: str) -> str:
    return re.sub(r"^(system|sys|systemname|base|station|planet|dock|docked|location|loc)\s*[=:]\s*", "", str(value or "").strip(), flags=re.I).strip()


def admin_pilot_system_name(character: dict[str, Any]) -> str:
    live = character.get("admin_live_location") or {}
    live_system = admin_clean_location_text(live.get("system") or "")
    if live_system and live_system.casefold() not in {"—", "-", "неизвестно", "unknown"}:
        return live_system

    value = admin_clean_location_text((character.get("system") or {}).get("name") or "")
    return value if value.casefold() not in {"", "—", "-", "неизвестно", "unknown"} else "—"


def admin_pilot_place_name(character: dict[str, Any]) -> str:
    """Base/planet/space label for admin pages.

    For online pilots we prefer live FLHook/getplayers state over stale .fl
    `base =` value. If the pilot is online and FLHook does not expose dock/base,
    show "в космосе" instead of old planet/station from the save file.
    """
    live = character.get("admin_live_location") or {}
    live_place = admin_clean_location_text(live.get("place") or "")
    if live_place and live_place.casefold() not in {"—", "-", "неизвестно", "unknown"}:
        return live_place

    base = character.get("base") or {}
    for key in ("name", "display_name", "nickname", "token", "code"):
        value = admin_clean_location_text(base.get(key) or "")
        if value and value.casefold() not in {"—", "-", "неизвестно", "unknown"}:
            return value

    return "в космосе"


def admin_pilot_location_source(character: dict[str, Any]) -> str:
    live = character.get("admin_live_location") or {}
    source = str(live.get("source") or "file").strip()
    if source == "flhook_getplayers":
        return "FLHook getplayers"
    if source == "flhook_online":
        return "FLHook online"
    return "file"


def admin_pilot_location_label(character: dict[str, Any]) -> str:
    return f"{admin_pilot_system_name(character)} · {admin_pilot_place_name(character)}"


def render_admin_warehouse_forms(account: dict[str, Any], character: dict[str, Any], all_warehouses: dict[str, Any]) -> str:
    account_id = str(account.get("id") or "")
    char_file = str(character.get("file") or "")
    char_name = str(character.get("name") or "")
    options = admin_location_options(character, all_warehouses)

    if not options:
        current = all_warehouses.get("current_location") or {}
        options = f"<option value='{esc(current.get('token') or '')}' data-location-name='{esc(current.get('name') or '')}' data-location-type='{esc(current.get('type') or 'base')}'>{esc(current.get('name') or 'Текущая база')}</option>"

    common_hidden = (
        f"<input type='hidden' name='account_id' value='{esc(account_id)}'>"
        f"<input type='hidden' name='character_file' value='{esc(char_file)}'>"
    )

    return f"""
    <div class="card admin-card">
      <h2>Админские операции со складом</h2>
      <p class="muted">Админ может создать, удалить или переместить любой item в любом складе пилота. Item указывается как hash / nickname / good_nickname / equipment_nickname.</p>
      <p class="pill money">Пилот сейчас: {esc(admin_pilot_location_label(character))}</p>
      <p class="muted small">Источник местоположения: {esc(admin_pilot_location_source(character))}</p>

      <div class="admin-actions-grid">
        <form method="post" action="/admin/warehouse/add" class="stat admin-action-form">
          <h3>Добавить item в склад</h3>
          {common_hidden}
          <label>Склад / база</label>
          <select name="location_hash" data-location-select required>{options}</select>
          <input type="hidden" name="location_name">
          <input type="hidden" name="location_type">
          <label>Хэш / никнейм предмета</label>
          <input name="item_token" placeholder="commodity_water / хэш / никнейм" required>
          <label>Количество</label>
          <input name="amount" inputmode="numeric" pattern="[0-9]+" value="1" required>
          <button type="submit">Создать / добавить</button>
        </form>

        <form method="post" action="/admin/warehouse/remove" class="stat admin-action-form">
          <h3>Удалить item со склада</h3>
          {common_hidden}
          <label>Склад / база</label>
          <select name="location_hash" data-location-select required>{options}</select>
          <input type="hidden" name="location_name">
          <input type="hidden" name="location_type">
          <label>Хэш предмета</label>
          <input name="item_token" placeholder="хэш предмета из строки склада" required>
          <label>Количество</label>
          <input name="amount" inputmode="numeric" pattern="[0-9]+" value="1" required>
          <button type="submit" class="danger">Удалить</button>
        </form>

        <form method="post" action="/admin/warehouse/move" class="stat admin-action-form">
          <h3>Переместить item</h3>
          {common_hidden}
          <label>Откуда</label>
          <select name="source_location_hash" data-location-select required>{options}</select>
          <input type="hidden" name="source_location_name">
          <input type="hidden" name="source_location_type">
          <label>Хэш предмета</label>
          <input name="item_token" placeholder="хэш предмета из строки склада" required>
          <label>Количество</label>
          <input name="amount" inputmode="numeric" pattern="[0-9]+" value="1" required>
          <label>Пилот-получатель</label>
          <input name="target" value="{esc(char_name)}" required>
          <label>Куда</label>
          <select name="target_location_hash" data-location-select required>{options}</select>
          <input type="hidden" name="target_location_name">
          <input type="hidden" name="target_location_type">
          <button type="submit">Переместить</button>
        </form>
      </div>
    </div>
    """




def reputation_admin_value(value: Any) -> str:
    try:
        rep = max(-1.0, min(1.0, float(str(value).replace(",", ".") or 0)))
    except Exception:
        rep = 0.0
    text = f"{rep:.3f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", "+0", ""} else text


def render_admin_reputation_editor(account: dict[str, Any], character: dict[str, Any]) -> str:
    houses = character.get("houses") or []
    if not houses:
        return """
        <div class="card admin-card">
          <h2>Ручное изменение репутации</h2>
          <p class="muted">Репутация не найдена в файле персонажа.</p>
        </div>
        """

    account_id = str(account.get("id") or "")
    char_file = str(character.get("file") or "")

    rows = []
    for row in houses:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or code or "Фракция")
        value = reputation_admin_value(row.get("reputation", "0"))
        if not code:
            continue

        rows.append(
            "<tr class='admin-rep-row' data-admin-rep-row='1'>"
            f"<td><b>{esc(name)}</b><br><span class='muted small'>{esc(code)}</span></td>"
            "<td class='admin-rep-controls'>"
            f"<button type='button' class='rep-step rep-minus' data-rep-delta='-0.05'>−</button>"
            f"{reputation_scale(value)}"
            f"<button type='button' class='rep-step rep-plus' data-rep-delta='0.05'>+</button>"
            "</td>"
            "<td>"
            f"<input class='admin-rep-input' name='rep_value' value='{esc(value)}' data-original-rep='{esc(value)}' inputmode='decimal' pattern='-?[0-9]+([\\.,][0-9]+)?'>"
            f"<input type='hidden' name='rep_code' value='{esc(code)}'>"
            f"<input type='hidden' name='rep_old' value='{esc(value)}'>"
            "</td>"
            "</tr>"
        )

    body_rows = "".join(rows) or "<tr><td colspan='3' class='muted'>Нет строк репутации.</td></tr>"

    return f"""
    <div class="card admin-card admin-reputation-card">
      <h2>Ручное изменение репутации</h2>
      <p class="muted">Кнопки − и + меняют значение с шагом 0.05. После правки нажми «Изменить репутацию» — изменённые строки будут отправлены через FLHook.</p>
      <form method="post" action="/admin/reputation/update" id="admin-reputation-form">
        <input type="hidden" name="account_id" value="{esc(account_id)}">
        <input type="hidden" name="character_file" value="{esc(char_file)}">
        <div class="admin-table-scroll admin-rep-scroll">
          <table class="reputation-table admin-reputation-table">
            <thead><tr><th>Фракция</th><th>Шкала</th><th>Значение</th></tr></thead>
            <tbody>{body_rows}</tbody>
          </table>
        </div>
        <div class="admin-rep-actions">
          <button type="submit" class="admin-flhook-green">Изменить репутацию</button>
          <span class="muted small">Команда выполняется через FLHook, затем вызывается savechar.</span>
        </div>
      </form>
    </div>
    """


def render_admin_pilot(account: dict[str, Any], character: dict[str, Any], cargo_summary: dict[str, Any], all_warehouses: dict[str, Any], online: bool | None = None, message: str = '', error: str = '') -> bytes:
    online_badge = "<span class='pill money'>online</span>" if online else "<span class='pill'>offline / unknown</span>"
    notice = f"<p class='pill money'>{esc(message)}</p>" if message else f"<p class='pill negative'>{esc(error)}</p>" if error else ""
    warehouse_html = render_admin_all_warehouses(all_warehouses)

    body = f"""
    <div class="card">
      <a class="pill" href="/admin">← админка</a>
      <a class="pill" href="/admin/account/{esc(urllib.parse.quote(str(account.get('id') or ''), safe=''))}">аккаунт</a>
      <button type="button" class="pill admin-flhook-green" data-admin-console-open="1">FLHook console</button>
      {online_badge}
      {notice}
      <h1>{esc(character.get('name') or 'Пилот')}</h1>
      <p class="ship">{esc(cargo_summary.get('ship_display_name') or (character.get('ship') or {}).get('name') or '')}</p>
      <p class="muted">
        Аккаунт: {esc(account.get('id') or '')} · файл: {esc(character.get('file') or '')}
      </p>
      <p class="muted small">Источник местоположения: {esc(admin_pilot_location_source(character))}</p>
    </div>

    {render_admin_flhook_console()}

    <div class="grid admin-pilot-grid">
      <div class="stat"><b>{money(int(character.get('money') or 0))}</b>Кредиты персонажа</div>
      <div class="stat"><b>{money(int(account.get('bank') or character.get('bank') or 0))}</b>Банк аккаунта</div>
      <div class="stat"><b>{esc(admin_pilot_system_name(character))}</b>Система</div>
      <div class="stat"><b>{esc(admin_pilot_place_name(character))}</b>Место</div>
      <div class="stat"><b>{esc(character.get('rank') or '0')}</b>Ранг</div>
      <div class="stat"><b>{esc(character.get('file') or '')}</b>.fl файл</div>
    </div>

    {render_admin_reputation_editor(account, character)}

    <div class="card admin-card">
      <h2>Трюм корабля</h2>
      {render_hold_panel(cargo_summary)}
    </div>

    {render_admin_warehouse_forms(account, character, all_warehouses)}

    <div class="card admin-card">
      <h2>Имущество на всех базах / планетах</h2>
      {warehouse_html}
    </div>

    <div class="card admin-card">
      <h2>Снаряжение корабля</h2>
      {equipment_groups_html(character, cargo_summary)}
    </div>
    """
    return page(f"Админ · {character.get('name')}", body)


def render_admin(repo, online: dict[str, Any] | None = None, command_result: dict[str, Any] | None = None) -> bytes:
    rows = "".join(
        "<tr>"
        f"<td><a href='/admin/account/{esc(urllib.parse.quote(str(account['id']), safe=''))}'>{esc(account['id'])}</a></td>"
        f"<td>{esc(account['character_count'])}</td>"
        f"<td>{money(account['total_money'])}</td>"
        f"<td>{esc(account['max_rank'])}</td>"
        f"<td>{', '.join('<a href=\'/admin/pilot/' + esc(urllib.parse.quote(str(account['id']), safe='')) + '/' + esc(urllib.parse.quote(str(c.get('file') or ''), safe='')) + '\'>' + esc(c['name']) + '</a>' for c in account['characters'][:8])}</td>"
        "</tr>"
        for account in repo.accounts
    )

    body = f"""
    <div class="card">
      <h1>Админская зона</h1>
      <p class="muted">Операторская часть: онлайн-пилоты FLHook, консоль команд, аккаунты и просмотр имущества пилота на всех базах.</p>
      <div class="toolbar">
        <input class="search" id="q" placeholder="Поиск по аккаунту или персонажу...">
        <a class="pill" href="/api/accounts" target="_blank" rel="noopener">JSON API</a>
        <a class="pill" href="/">клиентский вход</a>
        <button type="button" class="pill admin-flhook-green" data-admin-console-open="1">FLHook console</button>
      </div>
    </div>

    {render_admin_online_table(online)}
    {render_admin_flhook_console(command_result)}

    <div class="card admin-card">
      <h2>Аккаунты</h2>
      <div id="admin-accounts-scroll" class="admin-table-scroll admin-accounts-scroll">
        <table id="accounts">
          <thead><tr><th>ID</th><th>Перс.</th><th>Кредиты</th><th>Max rank</th><th>Персонажи</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>

    <script>
    q.oninput=()=>{{
      const v=q.value.toLowerCase();
      document.querySelectorAll('#accounts tbody tr,#admin-online-pilots tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(v)?'':'none')
    }};
    </script>
    """
    return page("Админ · Freelancer Account Panel", body)


def render_admin_account(account: dict[str, Any]) -> bytes:
    rows = "".join(
        "<tr>"
        f"<td><a href='{esc(admin_pilot_url(account['id'], char['file']))}'>{esc(char['name'])}</a></td>"
        f"<td>{esc(char['file'])}</td>"
        f"<td>{esc(char['ship']['name'])}</td>"
        f"<td>{money(char['money'])}</td>"
        f"<td>{esc(char['system']['name'])}</td>"
        f"<td>{esc(admin_pilot_place_name(char))}</td>"
        f"<td>{esc(char['rank'])}</td>"
        "</tr>"
        for char in account["characters"]
    )
    body = (
        render_admin_flhook_console() +
        f"<div class='card'><a class='pill' href='/admin'>← админка</a><button type='button' class='pill admin-flhook-green' data-admin-console-open='1'>FLHook console</button>"
        f"<h1>{esc(account['id'])}</h1>"
        f"<p class='muted'>Банк аккаунта: {money(int(account.get('bank') or 0))}</p>"
        "<div class='admin-table-scroll'>"
        "<table><thead><tr><th>Персонаж</th><th>Файл</th><th>Корабль</th><th>Кредиты</th><th>Система</th><th>Место</th><th>Ранг</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return page(f"Админ · {account['id']}", body)
