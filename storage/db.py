import os
import sqlite3
from pathlib import Path
from typing import Final


_DEFAULT_DB_PATH: Final[Path] = Path(__file__).resolve().parent / "bot.db"
DB_PATH: Final[str] = os.getenv("BOT_DB_PATH", str(_DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create required tables if they do not exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                level TEXT,
                last_lesson_id TEXT,
                created_at TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                word TEXT,
                translation TEXT,
                example TEXT,
                added_at TEXT
            )
            """
        )

        conn.commit()
    finally:
        conn.close()


def reset_db() -> None:
    """Drop all tables and recreate them (empty). Use after loading new lessons/words."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS vocab")
        cur.execute("DROP TABLE IF EXISTS users")
        conn.commit()
    finally:
        conn.close()
    init_db()

