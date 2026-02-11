import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from storage.db import get_connection


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Return user row as dict or None."""
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT telegram_id, level, last_lesson_id, created_at "
            "FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_user(
    telegram_id: int,
    level: Optional[str] = None,
    last_lesson_id: Optional[str] = None,
) -> None:
    """Insert or update user by telegram_id."""
    created_at = _utc_now_iso()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (telegram_id, level, last_lesson_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                level = excluded.level,
                last_lesson_id = excluded.last_lesson_id
            """,
            (telegram_id, level, last_lesson_id, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def set_level(telegram_id: int, level: str) -> None:
    """Update user level, creating user if necessary."""
    existing = get_user(telegram_id)
    if existing is None:
        upsert_user(telegram_id=telegram_id, level=level, last_lesson_id=None)
        return

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET level = ? WHERE telegram_id = ?",
            (level, telegram_id),
        )
        conn.commit()
    finally:
        conn.close()

