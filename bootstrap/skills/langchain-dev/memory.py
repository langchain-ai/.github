"""
Persistent Conversation Memory — SQLite Backend + ACMM Integration
====================================================================
Stores conversation exchanges per thread.
Used by agent.py for cross-session context injection.

ACMM Upgrade:
  Wenn das memory-mesh Skill verfügbar ist, wird semantisches Retrieval
  (sentence-transformers + FTS5) für get_context() verwendet statt
  chronologischem Fallback.
"""

from __future__ import annotations

import sqlite3
import os
import sys
from typing import List

# Optionaler ACMM-Import — graceful degradation wenn nicht installiert
_semantic_memory = None
_acmm_available = False

def _try_load_acmm(db_path: str):
    """Versucht das ACMM-Skill zu laden. Kein Fehler wenn nicht verfügbar."""
    global _semantic_memory, _acmm_available
    if _semantic_memory is not None:
        return

    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mesh_path = os.path.join(skill_root, "memory-mesh")

    if not os.path.isdir(mesh_path):
        return

    if mesh_path not in sys.path:
        sys.path.insert(0, mesh_path)

    try:
        from embedder import SemanticMemory  # noqa: PLC0415
        _semantic_memory = SemanticMemory(db_path)
        _acmm_available = True
    except Exception:
        pass  # sentence-transformers nicht installiert — kein Problem


class ConversationMemory:
    """
    SQLite-backed Memory mit optionalem semantischen ACMM-Upgrade.

    Fallback-Hierarchie:
      1. ACMM semantisches Retrieval (wenn memory-mesh installiert)
      2. Chronologische Recency (immer verfügbar)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        _try_load_acmm(db_path)

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
        # ACMM: Auch in semantischem Memory speichern
        if _acmm_available and _semantic_memory:
            combined = f"User: {human}\nAssistant: {assistant}"
            _semantic_memory.embed_and_store(
                content=combined,
                thread_id=thread_id,
                source="exchange",
                importance=1.0,
            )

    def get_context(self, thread_id: str, limit: int = 5, query: str = "") -> str:
        """
        Gibt relevanten Kontext für System-Prompt-Injektion zurück.

        Wenn ACMM verfügbar und query angegeben:
          → Semantisches Retrieval (relevanteste Erinnerungen)
        Sonst:
          → Chronologisches Fallback (letzte N Exchanges)
        """
        if _acmm_available and _semantic_memory and query:
            return self._semantic_context(thread_id, query, limit)
        return self._recency_context(thread_id, limit)

    def _semantic_context(self, thread_id: str, query: str, top_k: int) -> str:
        """ACMM: Semantisch relevanteste Erinnerungen."""
        results = _semantic_memory.semantic_search(
            query=query,
            thread_id=thread_id,
            top_k=top_k,
        )
        if not results:
            return self._recency_context(thread_id, top_k)
        return _semantic_memory.format_for_prompt(results)

    def _recency_context(self, thread_id: str, limit: int) -> str:
        """Chronologisches Fallback."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT human, assistant, created_at
                   FROM exchanges
                   WHERE thread_id = ?
                   AND human NOT LIKE '[COMPRESSED%'
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
        result = {"total_exchanges": total, "threads": threads, "db_path": self.db_path}
        if _acmm_available and _semantic_memory:
            result["acmm"] = _semantic_memory.stats()
        return result

    @property
    def acmm_available(self) -> bool:
        return _acmm_available
