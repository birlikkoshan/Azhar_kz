"""
Drop and recreate the bot database (users + vocab). Run after updating
words.json / sentances.json and regenerating lessons, quizzes, trends.

  python reset_db.py
"""
from storage.db import reset_db

if __name__ == "__main__":
    reset_db()
    print("Database reset: tables dropped and recreated.")
