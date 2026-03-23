"""
Persistent Conversation Memory — SQLite Backend
================================================
Stores conversation exchanges per thread.
Used by agent.py for cross-session context injection.
"""

from __future__ import annotations

import sqlite3
import os
from datetime import datetime
from typing import List


class ConversationMemory:
    """
    Lightweight SQLite-backed memory for conversation context.
    Separate from LangGraph's SqliteSaver (which handles full state).
    This provides semantic summaries for system prompt injection.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exchanges (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id   TEXT NOT NULL,
                    human       TEXT NOT NULL,
                    assistant   TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_thread
                ON exchanges(thread_id, created_at DESC)
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_exchange(self, thread_id: str, human: str, assistant: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO exchanges (thread_id, human, assistant) VALUES (?, ?, ?)",
                (thread_id, human[:1000], assistant[:1000])
            )

    def get_context(self, thread_id: str, limit: int = 5) -> str:
        """
        Returns recent exchanges formatted for system prompt injection.
        Only includes exchanges from this thread.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT human, assistant, created_at
                   FROM exchanges
                   WHERE thread_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (thread_id, limit)
            ).fetchall()

        if not rows:
            return ""

        lines = []
        for human, assistant, ts in reversed(rows):
            lines.append(f"[{ts}] User: {human}")
            lines.append(f"[{ts}] You: {assistant}")

        return "\n".join(lines)

    def get_all_threads(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT thread_id FROM exchanges ORDER BY thread_id"
            ).fetchall()
        return [r[0] for r in rows]

    def delete_thread(self, thread_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM exchanges WHERE thread_id = ?", (thread_id,))

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM exchanges").fetchone()[0]
            threads = conn.execute("SELECT COUNT(DISTINCT thread_id) FROM exchanges").fetchone()[0]
        return {"total_exchanges": total, "threads": threads, "db_path": self.db_path}
