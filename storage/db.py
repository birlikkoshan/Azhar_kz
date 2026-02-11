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
                telegram_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                translation TEXT,
                example TEXT,
                added_at TEXT,
                UNIQUE(telegram_id, word)
            )
            """
        )
        # Ensure unique index exists (for DBs created before this constraint was added)
        try:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_user_word ON vocab(telegram_id, word)"
            )
        except sqlite3.OperationalError:
            # Old DB may have duplicate (telegram_id, word); dedupe then add index
            cur.execute(
                """
                CREATE TABLE vocab_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    translation TEXT,
                    example TEXT,
                    added_at TEXT,
                    UNIQUE(telegram_id, word)
                )
                """
            )
            cur.execute(
                """
                INSERT OR IGNORE INTO vocab_new (id, telegram_id, word, translation, example, added_at)
                SELECT id, telegram_id, word, translation, example, added_at FROM vocab
                ORDER BY id DESC
                """
            )
            cur.execute("DROP TABLE vocab")
            cur.execute("ALTER TABLE vocab_new RENAME TO vocab")
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

