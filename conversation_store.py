"""
Persistent conversation memory using SQLite.

Stores message history per user (phone number or web session key)
so the assistant remembers recent context across sessions and restarts.
"""

import json
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "conversations.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_created
            ON conversations (session_id, created_at)
        """)


def save_message(session_id: str, role: str, content: str):
    """
    Save a single message to the conversation history.
    session_id is a phone number ("+16465551234") or web key ("web:Mark").
    content should be a plain text string.
    """
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )


def load_recent_messages(session_id: str, limit: int = 10) -> list:
    """
    Return the last `limit` messages for a session as Claude-compatible
    message dicts: [{"role": "user"/"assistant", "content": "..."}]
    """
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at
                FROM conversations
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def prune_old_messages(days: int = 90):
    """Delete messages older than `days` days. Run occasionally for housekeeping."""
    cutoff = time.time() - (days * 86400)
    with _get_conn() as conn:
        result = conn.execute(
            "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
        )
        return result.rowcount


# Initialize DB on import
init_db()
