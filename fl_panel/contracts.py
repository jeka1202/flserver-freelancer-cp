from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .db import connect
from .finance import read_bank_balance, write_bank_balance
from .repository import money
from .warehouse import (
    add_item_to_specific_warehouse,
    character_file_key,
    character_name,
    ensure_warehouse_schema,
    location_from_character,
    log_operation,
    now_iso,
    parse_positive_int,
    resolve_item,
    row_value,
)


def now_dt() -> datetime:
    return datetime.now()


def parse_dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def fmt_dt(value: Any) -> str:
    dt = parse_dt(value)
    if not dt:
        return str(value or "—")
    return dt.strftime("%d.%m.%Y %H:%M")


def seconds_left(value: Any) -> int:
    dt = parse_dt(value)
    if not dt:
        return 0
    return max(0, int((dt - now_dt()).total_seconds()))


def fmt_seconds_left(value: Any) -> str:
    total = seconds_left(value)
    if total <= 0:
        return "истёк"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}д {hours:02d}:{minutes:02d}"
    return f"{hours:02d}:{minutes:02d}"


def ensure_contract_schema(conn: sqlite3.Connection) -> None:
    ensure_warehouse_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            closed_at TEXT,
            sold_at TEXT,

            seller_account_id TEXT NOT NULL,
            seller_character_file TEXT NOT NULL,
            seller_character_name TEXT,
            buyer_account_id TEXT,
            buyer_character_file TEXT,
            buyer_character_name TEXT,

            location_hash TEXT NOT NULL,
            location_type TEXT DEFAULT 'base',
            location_name TEXT,

            item_hash TEXT NOT NULL,
            item_nickname TEXT,
            item_display_name TEXT,
            category TEXT,
            volume REAL DEFAULT 0,
            mass REAL DEFAULT 0,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL,
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_contracts_status_expires
            ON contracts(status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_contracts_seller
            ON contracts(seller_account_id, seller_character_file);
        CREATE INDEX IF NOT EXISTS idx_contracts_buyer
            ON contracts(buyer_account_id, buyer_character_file);
        CREATE INDEX IF NOT EXISTS idx_contracts_location
            ON contracts(location_hash);

        CREATE TABLE IF NOT EXISTS contract_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            contract_id INTEGER,
            operation TEXT NOT NULL,
            actor_account_id TEXT,
            actor_character_file TEXT,
            actor_character_name TEXT,
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_contract_log_contract
            ON contract_log(contract_id);
        CREATE INDEX IF NOT EXISTS idx_contract_log_created
            ON contract_log(created_at);
        """
    )
    conn.commit()


def log_contract(
    conn: sqlite3.Connection,
    *,
    contract_id: int | None,
    operation: str,
    actor_account_id: str = "",
    actor_character_file: str = "",
    actor_character_name: str = "",
    note: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO contract_log
        (created_at, contract_id, operation, actor_account_id, actor_character_file, actor_character_name, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (now_iso(), contract_id, operation, actor_account_id, actor_character_file, actor_character_name, note),
    )


def contract_item(row: Any) -> dict[str, Any]:
    return {
        "hash": row_value(row, "item_hash", ""),
        "nickname": row_value(row, "item_nickname", ""),
        "display_name": row_value(row, "item_display_name", "") or "Неизвестный предмет",
        "category": row_value(row, "category", ""),
        "volume": float(row_value(row, "volume", 0) or 0),
        "mass": float(row_value(row, "mass", 0) or 0),
    }


def contract_location(row: Any) -> dict[str, str]:
    return {
        "token": str(row_value(row, "location_hash", "") or "unknown_base"),
        "name": str(row_value(row, "location_name", "") or "Неизвестная база"),
        "type": str(row_value(row, "location_type", "base") or "base"),
    }


def fake_character(file_name: str, name: str) -> dict[str, Any]:
    return {"file": file_name or "unknown_character", "name": name or "Пилот"}


def return_contract_to_seller(conn: sqlite3.Connection, row: Any, reason: str) -> None:
    seller_character = fake_character(
        str(row_value(row, "seller_character_file", "")),
        str(row_value(row, "seller_character_name", "")),
    )
    item = contract_item(row)
    location = contract_location(row)
    quantity = int(row_value(row, "quantity", 0) or 0)

    if quantity > 0:
        add_item_to_specific_warehouse(
            conn,
            account_id=str(row_value(row, "seller_account_id", "")),
            character=seller_character,
            location=location,
            item=item,
            quantity=quantity,
        )

        log_operation(
            conn,
            account_id=str(row_value(row, "seller_account_id", "")),
            character=seller_character,
            location=location,
            item=item,
            quantity_delta=quantity,
            operation="contract_return",
            note=reason,
        )


def process_expired_contracts(conn: sqlite3.Connection) -> int:
    ensure_contract_schema(conn)
    now = now_iso()
    rows = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE status = 'active'
          AND expires_at <= ?
        ORDER BY expires_at
        """,
        (now,),
    ).fetchall()

    count = 0

    for row in rows:
        contract_id = int(row_value(row, "id", 0) or 0)
        return_contract_to_seller(conn, row, "Контракт истёк. Товар возвращён продавцу.")
        conn.execute(
            """
            UPDATE contracts
            SET status = 'expired',
                closed_at = ?
            WHERE id = ?
            """,
            (now_iso(), contract_id),
        )
        log_contract(
            conn,
            contract_id=contract_id,
            operation="expired",
            actor_account_id=str(row_value(row, "seller_account_id", "")),
            actor_character_file=str(row_value(row, "seller_character_file", "")),
            actor_character_name=str(row_value(row, "seller_character_name", "")),
            note="Срок действия контракта истёк. Товар возвращён продавцу.",
        )
        count += 1

    if count:
        conn.commit()

    return count


def contract_row_to_dict(row: Any) -> dict[str, Any]:
    price = int(row_value(row, "price", 0) or 0)
    quantity = int(row_value(row, "quantity", 0) or 0)
    return {
        "id": int(row_value(row, "id", 0) or 0),
        "status": row_value(row, "status", ""),
        "created_at": row_value(row, "created_at", ""),
        "expires_at": row_value(row, "expires_at", ""),
        "expires_text": fmt_dt(row_value(row, "expires_at", "")),
        "left_text": fmt_seconds_left(row_value(row, "expires_at", "")),
        "seller_account_id": row_value(row, "seller_account_id", ""),
        "seller_character_file": row_value(row, "seller_character_file", ""),
        "seller_character_name": row_value(row, "seller_character_name", ""),
        "buyer_account_id": row_value(row, "buyer_account_id", ""),
        "buyer_character_file": row_value(row, "buyer_character_file", ""),
        "buyer_character_name": row_value(row, "buyer_character_name", ""),
        "location_hash": row_value(row, "location_hash", ""),
        "location_type": row_value(row, "location_type", "base"),
        "location_name": row_value(row, "location_name", "") or "Неизвестная база",
        "item_hash": row_value(row, "item_hash", ""),
        "item_nickname": row_value(row, "item_nickname", ""),
        "item_display_name": row_value(row, "item_display_name", "") or "Неизвестный предмет",
        "category": row_value(row, "category", ""),
        "volume": float(row_value(row, "volume", 0) or 0),
        "mass": float(row_value(row, "mass", 0) or 0),
        "quantity": quantity,
        "price": price,
        "price_text": money(price),
        "unit_price_text": money(price // quantity) if quantity > 0 else money(price),
        "note": row_value(row, "note", "") or "",
    }


def load_contracts_for_context(account_id: str, character: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    ensure_contract_schema(conn)
    process_expired_contracts(conn)

    char_file = character_file_key(character)

    public_rows = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE status = 'active'
        ORDER BY expires_at, item_display_name COLLATE NOCASE
        """
    ).fetchall()

    my_rows = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE seller_account_id = ?
          AND seller_character_file = ?
        ORDER BY
          CASE status
            WHEN 'active' THEN 0
            WHEN 'expired' THEN 1
            WHEN 'sold' THEN 2
            WHEN 'cancelled' THEN 3
            ELSE 9
          END,
          id DESC
        LIMIT 80
        """,
        (account_id, char_file),
    ).fetchall()

    bought_rows = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE buyer_account_id = ?
          AND buyer_character_file = ?
        ORDER BY sold_at DESC, id DESC
        LIMIT 50
        """,
        (account_id, char_file),
    ).fetchall()

    conn.close()

    return {
        "public": [contract_row_to_dict(row) for row in public_rows],
        "mine": [contract_row_to_dict(row) for row in my_rows],
        "bought": [contract_row_to_dict(row) for row in bought_rows],
    }


def create_contract(
    account_id: str,
    character: dict[str, Any],
    item_token: str,
    quantity: int,
    price: int,
    lifetime_value: int,
    lifetime_unit: str = "hours",
    source_location: dict[str, str] | None = None,
) -> tuple[bool, str]:
    if quantity <= 0:
        return False, "Количество должно быть положительным целым числом."

    if price <= 0:
        return False, "Цена должна быть положительным целым числом."

    if lifetime_value <= 0:
        return False, "Срок жизни контракта должен быть положительным числом."

    lifetime_unit = str(lifetime_unit or "hours").strip().lower()
    if lifetime_unit not in {"hours", "days"}:
        lifetime_unit = "hours"

    if lifetime_unit == "days":
        if lifetime_value > 30:
            return False, "Максимальный срок контракта: 30 дней."
        delta = timedelta(days=lifetime_value)
    else:
        if lifetime_value > 720:
            return False, "Максимальный срок контракта: 720 часов."
        delta = timedelta(hours=lifetime_value)

    conn = connect()
    ensure_contract_schema(conn)
    process_expired_contracts(conn)

    location = source_location or location_from_character(character)
    char_file = character_file_key(character)
    char_name = character_name(character)
    item = resolve_item(conn, item_token)

    if not item:
        conn.close()
        return False, "Предмет не найден в БД."

    try:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            """
            SELECT quantity
            FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
            LIMIT 1
            """,
            (account_id, char_file, location["token"], item["hash"]),
        ).fetchone()

        current = int(row_value(row, "quantity", 0) or 0)
        if current <= 0:
            conn.close()
            return False, "Такого предмета нет на личном складе этой базы."

        if quantity > current:
            conn.close()
            return False, f"На складе только {current} шт."

        new_quantity = current - quantity
        ts = now_iso()
        expires_at = (now_dt() + delta).isoformat(timespec="seconds")

        updated = conn.execute(
            """
            UPDATE warehouses
            SET quantity = quantity - ?, updated_at = ?
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity >= ?
            """,
            (quantity, ts, account_id, char_file, location["token"], item["hash"], quantity),
        )

        if updated.rowcount != 1:
            conn.rollback()
            conn.close()
            return False, f"На складе только {current} шт. Нельзя выставить {quantity} шт."

        conn.execute(
            """
            DELETE FROM warehouses
            WHERE account_id = ?
              AND character_file = ?
              AND location_hash = ?
              AND item_hash = ?
              AND quantity <= 0
            """,
            (account_id, char_file, location["token"], item["hash"]),
        )

        cur = conn.execute(
            """
            INSERT INTO contracts
            (status, created_at, expires_at,
             seller_account_id, seller_character_file, seller_character_name,
             location_hash, location_type, location_name,
             item_hash, item_nickname, item_display_name, category, volume, mass,
             quantity, price, note)
            VALUES ('active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                expires_at,
                account_id,
                char_file,
                char_name,
                location["token"],
                location["type"],
                location["name"],
                item["hash"],
                item["nickname"],
                item["display_name"],
                item["category"],
                item["volume"],
                item["mass"],
                quantity,
                price,
                "Создано из склада базы.",
            ),
        )
        contract_id = int(cur.lastrowid)

        log_operation(
            conn,
            account_id=account_id,
            character=character,
            location=location,
            item=item,
            quantity_delta=-quantity,
            operation="contract_create",
            note=f"Товар зарезервирован в контракте #{contract_id}.",
        )
        log_contract(
            conn,
            contract_id=contract_id,
            operation="created",
            actor_account_id=account_id,
            actor_character_file=char_file,
            actor_character_name=char_name,
            note=f"{quantity} шт. за {money(price)} кредитов. Локация: {location['name']}.",
        )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка создания контракта: {exc}"

    conn.close()
    return True, f"Контракт #{contract_id} создан: {quantity} шт. «{item['display_name']}» за {money(price)} кредитов. Место: {location['name']}. Товар снят со склада и зарезервирован."


def cancel_contract(account_id: str, character: dict[str, Any], contract_id: int) -> tuple[bool, str]:
    if contract_id <= 0:
        return False, "Некорректный номер контракта."

    conn = connect()
    ensure_contract_schema(conn)
    process_expired_contracts(conn)

    char_file = character_file_key(character)

    row = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE id = ?
        LIMIT 1
        """,
        (contract_id,),
    ).fetchone()

    if not row:
        conn.close()
        return False, "Контракт не найден."

    if row_value(row, "status") != "active":
        conn.close()
        return False, "Этот контракт уже закрыт."

    if row_value(row, "seller_account_id") != account_id or row_value(row, "seller_character_file") != char_file:
        conn.close()
        return False, "Можно отменить только свой контракт."

    try:
        return_contract_to_seller(conn, row, "Контракт отменён продавцом. Товар возвращён продавцу.")
        conn.execute(
            """
            UPDATE contracts
            SET status = 'cancelled',
                closed_at = ?
            WHERE id = ?
            """,
            (now_iso(), contract_id),
        )
        log_contract(
            conn,
            contract_id=contract_id,
            operation="cancelled",
            actor_account_id=account_id,
            actor_character_file=char_file,
            actor_character_name=character_name(character),
            note="Контракт отменён продавцом.",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return False, f"Ошибка отмены контракта: {exc}"

    item_name = row_value(row, "item_display_name", "предмет")
    conn.close()
    return True, f"Контракт #{contract_id} отменён. «{item_name}» возвращён на склад."


def buy_contract(repo: Any, buyer_account_id: str, buyer_character: dict[str, Any], contract_id: int) -> tuple[bool, str]:
    if contract_id <= 0:
        return False, "Некорректный номер контракта."

    conn = connect()
    ensure_contract_schema(conn)
    process_expired_contracts(conn)

    buyer_char_file = character_file_key(buyer_character)
    buyer_char_name = character_name(buyer_character)

    row = conn.execute(
        """
        SELECT *
        FROM contracts
        WHERE id = ?
        LIMIT 1
        """,
        (contract_id,),
    ).fetchone()

    if not row:
        conn.close()
        return False, "Контракт не найден."

    if row_value(row, "status") != "active":
        conn.close()
        return False, "Этот контракт уже закрыт."

    expires = parse_dt(row_value(row, "expires_at", ""))
    if expires and expires <= now_dt():
        try:
            return_contract_to_seller(conn, row, "Контракт истёк во время покупки. Товар возвращён продавцу.")
            conn.execute(
                "UPDATE contracts SET status='expired', closed_at=? WHERE id=?",
                (now_iso(), contract_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
        return False, "Срок действия контракта истёк. Товар возвращён продавцу."

    seller_account_id = str(row_value(row, "seller_account_id", ""))
    seller_char_file = str(row_value(row, "seller_character_file", ""))

    if seller_account_id == buyer_account_id and seller_char_file == buyer_char_file:
        conn.close()
        return False, "Нельзя купить собственный контракт."

    buyer_found = repo.find_character_by_file(buyer_account_id, buyer_char_file)
    if not buyer_found:
        conn.close()
        return False, "Пилот-покупатель не найден."

    buyer_account, buyer_character_real = buyer_found
    buyer_account_path = repo.accounts_dir / buyer_account_id
    buyer_character_path = buyer_account_path / buyer_char_file

    if not buyer_character_path.exists():
        conn.close()
        return False, "Файл покупателя не найден."

    seller_account = repo.by_id.get(seller_account_id.lower())
    seller_account_path = repo.accounts_dir / seller_account_id

    if not seller_account_path.exists():
        conn.close()
        return False, "Аккаунт продавца не найден. Покупка отменена."

    price = int(row_value(row, "price", 0) or 0)
    quantity = int(row_value(row, "quantity", 0) or 0)
    item = contract_item(row)
    location = contract_location(row)

    try:
        buyer_money, buyer_online = repo.get_live_or_file_money(buyer_character_real, buyer_character_path)
    except Exception as exc:
        conn.close()
        return False, f"Не удалось прочитать деньги покупателя: {exc}"

    buyer_bank = read_bank_balance(buyer_account_path)

    if buyer_money + buyer_bank < price:
        conn.close()
        return False, f"Недостаточно средств. Нужно {money(price)} кредитов."

    debit_from_character = min(buyer_money, price)
    debit_from_bank = price - debit_from_character
    new_buyer_bank = buyer_bank - debit_from_bank

    try:
        if debit_from_character:
            new_buyer_money, used_flhook = repo.add_cash_safe(buyer_character_real, buyer_character_path, -debit_from_character)
        else:
            new_buyer_money = buyer_money
            used_flhook = False

        if debit_from_bank:
            write_bank_balance(buyer_account_path, new_buyer_bank)

        seller_bank_before = read_bank_balance(seller_account_path)
        seller_bank_after = seller_bank_before + price
        write_bank_balance(seller_account_path, seller_bank_after)

        if seller_account:
            repo.set_account_bank(seller_account, seller_bank_after)

        repo.set_character_money(buyer_account, buyer_character_real, new_buyer_money)
        if debit_from_bank:
            repo.set_account_bank(buyer_account, new_buyer_bank)

        add_item_to_specific_warehouse(
            conn,
            account_id=buyer_account_id,
            character=buyer_character_real,
            location=location,
            item=item,
            quantity=quantity,
        )

        ts = now_iso()
        conn.execute(
            """
            UPDATE contracts
            SET status = 'sold',
                sold_at = ?,
                closed_at = ?,
                buyer_account_id = ?,
                buyer_character_file = ?,
                buyer_character_name = ?
            WHERE id = ?
              AND status = 'active'
            """,
            (ts, ts, buyer_account_id, buyer_char_file, buyer_char_name, contract_id),
        )

        log_operation(
            conn,
            account_id=buyer_account_id,
            character=buyer_character_real,
            location=location,
            item=item,
            quantity_delta=quantity,
            operation="contract_buy",
            note=f"Покупка по контракту #{contract_id}. Цена {money(price)}.",
        )
        log_contract(
            conn,
            contract_id=contract_id,
            operation="sold",
            actor_account_id=buyer_account_id,
            actor_character_file=buyer_char_file,
            actor_character_name=buyer_char_name,
            note=f"Куплено {quantity} шт. за {money(price)}. Товар доставлен на склад покупателя в локации {location['name']}.",
        )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        # best-effort откат денег, если успели списать/начислить
        try:
            if debit_from_character:
                repo.add_cash_safe(buyer_character_real, buyer_character_path, debit_from_character)
            if debit_from_bank:
                write_bank_balance(buyer_account_path, buyer_bank)
            write_bank_balance(seller_account_path, read_bank_balance(seller_account_path) - price)
        except Exception:
            pass
        conn.close()
        return False, f"Ошибка покупки контракта: {exc}"

    conn.close()

    mode = "через FLHook" if used_flhook or buyer_online else "файловый режим"
    return True, f"Контракт #{contract_id} куплен: {quantity} шт. «{item['display_name']}» за {money(price)} кредитов. Товар помещён на личный склад покупателя в локации «{location['name']}». Оплата: {mode}."


def current_contract_context(account_id: str, character: dict[str, Any]) -> dict[str, Any]:
    return load_contracts_for_context(account_id, character)
