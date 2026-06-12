from __future__ import annotations

from datetime import datetime
from typing import Any
import sqlite3

from .db import connect


def now_sql() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_finance_history_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS finance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            account_id TEXT NOT NULL,
            character_file TEXT NOT NULL,
            character_name TEXT,
            operation TEXT NOT NULL,
            direction TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            character_delta INTEGER NOT NULL DEFAULT 0,
            bank_delta INTEGER NOT NULL DEFAULT 0,
            counterparty_account_id TEXT,
            counterparty_character_file TEXT,
            counterparty_character_name TEXT,
            mode TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_finance_log_owner
            ON finance_log(account_id, character_file, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_finance_log_counterparty
            ON finance_log(counterparty_character_name);

        CREATE INDEX IF NOT EXISTS idx_finance_log_created
            ON finance_log(created_at DESC);
        """
    )
    conn.commit()


def log_finance_event(
    account_id: str,
    character_file: str,
    character_name: str,
    operation: str,
    direction: str,
    amount: int,
    *,
    character_delta: int = 0,
    bank_delta: int = 0,
    counterparty_account_id: str = "",
    counterparty_character_file: str = "",
    counterparty_character_name: str = "",
    mode: str = "",
    status: str = "ok",
    note: str = "",
) -> bool:
    """Append a per-pilot finance history row.

    The function is intentionally tolerant: money operations must not be rolled
    back only because the optional history log failed.
    """

    try:
        conn = connect()
        ensure_finance_history_schema(conn)
        conn.execute(
            """
            INSERT INTO finance_log (
                created_at,
                account_id,
                character_file,
                character_name,
                operation,
                direction,
                amount,
                character_delta,
                bank_delta,
                counterparty_account_id,
                counterparty_character_file,
                counterparty_character_name,
                mode,
                status,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_sql(),
                str(account_id or ""),
                str(character_file or ""),
                str(character_name or ""),
                str(operation or ""),
                str(direction or ""),
                int(amount or 0),
                int(character_delta or 0),
                int(bank_delta or 0),
                str(counterparty_account_id or ""),
                str(counterparty_character_file or ""),
                str(counterparty_character_name or ""),
                str(mode or ""),
                str(status or "ok"),
                str(note or ""),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_finance_history(account_id: str, character_file: str, limit: int = 80) -> list[dict[str, Any]]:
    conn = connect()
    ensure_finance_history_schema(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM finance_log
        WHERE account_id = ?
          AND character_file = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (str(account_id or ""), str(character_file or ""), int(limit or 80)),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
