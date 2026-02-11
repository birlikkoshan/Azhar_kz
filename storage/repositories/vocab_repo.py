import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from storage.db import get_connection


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_words(telegram_id: int, words: Iterable[Dict[str, Any]]) -> None:
    """Add multiple words for a user.

    Each item in words is expected to have keys: word, translation, example.
    """
    now = _utc_now_iso()
    rows = []
    for item in words:
        rows.append(
            (
                telegram_id,
                item.get("word"),
                item.get("translation"),
                item.get("example"),
                now,
            )
        )

    if not rows:
        return

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO vocab (telegram_id, word, translation, example, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def list_words(telegram_id: int) -> List[Dict[str, Any]]:
    """Return all vocab words for a user, newest first."""
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, telegram_id, word, translation, example, added_at
            FROM vocab
            WHERE telegram_id = ?
            ORDER BY datetime(added_at) DESC, id DESC
            """,
            (telegram_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def random_words(telegram_id: int, limit: int) -> List[Dict[str, Any]]:
    """Return up to `limit` random words for a user."""
    if limit <= 0:
        return []

    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, telegram_id, word, translation, example, added_at
            FROM vocab
            WHERE telegram_id = ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (telegram_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def clear_all(telegram_id: int) -> None:
    """Delete all vocab entries for a user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM vocab WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
    finally:
        conn.close()

