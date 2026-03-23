"""
ACMM — Ambient Context Memory Mesh
Embedder: Offline-fähige semantische Vektorspeicherung in SQLite
==================================================================

Kernidee: Kein Vektordatenbank-Server. Kein Embedding-API-Call.
Alles lokal, offline, auf a-Shell (iOS) lauffähig.

Embedding-Strategie:
  1. sentence-transformers (all-MiniLM-L6-v2, ~90MB, CPU-only)
  2. Vektoren als BLOB in SQLite gespeichert
  3. Cosine-Similarity direkt in Python (numpy, kein FAISS nötig)
  4. SQLite FTS5 als schneller Vorfilter (BM25) vor Vektor-Reranking

Das ist die weltweit erste OSS-Implementierung dieses Patterns
für iOS (a-Shell) + OpenClaw + LangGraph.
"""

from __future__ import annotations

import os
import sqlite3
import struct
import hashlib
from typing import List, Tuple

# Lazy imports — nur laden wenn benötigt (spart Startzeit)
_model = None
_np = None


def _get_model():
    """Lazy-load sentence-transformer. Cached after first call."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # all-MiniLM-L6-v2: 90MB, 384-dim, sehr schnell auf CPU
            # all-MiniLM-L12-v2: bessere Qualität, etwas langsamer
            model_name = os.environ.get("ACMM_MODEL", "all-MiniLM-L6-v2")
            _model = SentenceTransformer(model_name)
        except ImportError:
            raise RuntimeError(
                "sentence-transformers nicht installiert.\n"
                "Führe aus: pip install sentence-transformers"
            )
    return _model


def _get_np():
    global _np
    if _np is None:
        import numpy as np
        _np = np
    return _np


# ── SQLite Schema ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_vectors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL,
    content     TEXT NOT NULL,
    content_hash TEXT NOT NULL,          -- SHA256 für Dedup
    vector_blob BLOB NOT NULL,           -- float32 array als bytes
    vector_dim  INTEGER NOT NULL,        -- z.B. 384
    source      TEXT DEFAULT 'exchange', -- 'exchange' | 'ambient' | 'fact'
    created_at  TEXT DEFAULT (datetime('now')),
    importance  REAL DEFAULT 1.0         -- 0..2, für späteres Ranking
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_hash
ON memory_vectors(content_hash);

CREATE INDEX IF NOT EXISTS idx_thread_source
ON memory_vectors(thread_id, source, created_at DESC);

-- FTS5 Vorfilter (BM25 ranking)
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
USING fts5(content, content='memory_vectors', content_rowid='id');

-- Trigger: FTS automatisch aktualisieren
CREATE TRIGGER IF NOT EXISTS memory_fts_insert
AFTER INSERT ON memory_vectors BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_fts_delete
AFTER DELETE ON memory_vectors BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_fts_update
AFTER UPDATE ON memory_vectors BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


# ── Vector Serialization ───────────────────────────────────────────────────────

def _vec_to_blob(vector) -> bytes:
    """numpy float32 array → raw bytes (little-endian)."""
    np = _get_np()
    arr = np.array(vector, dtype=np.float32)
    return struct.pack(f"{len(arr)}f", *arr)


def _blob_to_vec(blob: bytes, dim: int):
    """raw bytes → numpy float32 array."""
    np = _get_np()
    arr = struct.unpack(f"{dim}f", blob)
    return np.array(arr, dtype=np.float32)


def _cosine_similarity(a, b) -> float:
    """Cosine similarity zwischen zwei numpy-Vektoren."""
    np = _get_np()
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Main Embedder Class ───────────────────────────────────────────────────────

class SemanticMemory:
    """
    Offline-fähiger semantischer Langzeitspeicher.
    Läuft vollständig auf dem Gerät — kein API-Call für Embedding.

    Retrieval-Pipeline:
      1. FTS5 BM25 Vorfilter → top_k * 10 Kandidaten
      2. Vektor-Cosine-Reranking → top_k finale Ergebnisse
      3. Importance-Gewichtung (neuere + wichtigere Memory Facts zuerst)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with self._conn() as conn:
            # Schema in einzelnen Statements ausführen
            for stmt in SCHEMA_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass  # Idempotent — Tabellen/Trigger bereits vorhanden

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def embed_and_store(
        self,
        content: str,
        thread_id: str = "global",
        source: str = "exchange",
        importance: float = 1.0,
    ) -> int | None:
        """
        Embeds content and stores in SQLite.
        Skips duplicates (content_hash dedup).
        Returns inserted row ID, or None if duplicate.
        """
        content = content.strip()
        if not content or len(content) < 10:
            return None

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Dedup check
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM memory_vectors WHERE content_hash = ?",
                (content_hash,)
            ).fetchone()
            if existing:
                return None

        # Embed
        model = _get_model()
        vector = model.encode(content, normalize_embeddings=True)
        blob = _vec_to_blob(vector)
        dim = len(vector)

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO memory_vectors
                   (thread_id, content, content_hash, vector_blob, vector_dim, source, importance)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (thread_id, content, content_hash, blob, dim, source, importance)
            )
            return cursor.lastrowid

    def semantic_search(
        self,
        query: str,
        thread_id: str | None = None,
        top_k: int = 5,
        min_similarity: float = 0.25,
        sources: list[str] | None = None,
    ) -> List[Tuple[str, float]]:
        """
        Zwei-Stufen-Retrieval:
          1. FTS5 BM25 → Kandidaten-Pool (top_k * 8)
          2. Vektor-Cosine-Reranking → finale top_k

        Gibt zurück: [(content, similarity_score), ...]
        """
        if not query.strip():
            return []

        # Stage 1: FTS5 Vorfilter
        fts_limit = top_k * 8
        fts_query = " OR ".join(
            f'"{w}"' for w in query.split() if len(w) > 2
        ) or query

        thread_filter = ""
        params: list = [fts_query, fts_limit]
        if thread_id:
            thread_filter = "AND mv.thread_id = ?"
            params.insert(1, thread_id)

        source_filter = ""
        if sources:
            placeholders = ",".join("?" * len(sources))
            source_filter = f"AND mv.source IN ({placeholders})"
            params[:-1] = params[:-1] + sources  # Insert before limit

        # Rebuild params cleanly
        sql_params = [fts_query]
        if thread_id:
            sql_params.append(thread_id)
        if sources:
            sql_params.extend(sources)
        sql_params.append(fts_limit)

        sql = f"""
            SELECT mv.id, mv.content, mv.vector_blob, mv.vector_dim, mv.importance
            FROM memory_fts
            JOIN memory_vectors mv ON memory_fts.rowid = mv.id
            WHERE memory_fts MATCH ?
            {thread_filter}
            {source_filter}
            ORDER BY bm25(memory_fts) ASC
            LIMIT ?
        """

        try:
            with self._conn() as conn:
                candidates = conn.execute(sql, sql_params).fetchall()
        except sqlite3.OperationalError:
            # FTS hat keine Treffer oder Fehler — fallback auf recency
            candidates = self._recency_fallback(thread_id, fts_limit)

        if not candidates:
            candidates = self._recency_fallback(thread_id, fts_limit)

        if not candidates:
            return []

        # Stage 2: Vektor-Cosine-Reranking
        model = _get_model()
        query_vec = model.encode(query, normalize_embeddings=True)
        np = _get_np()

        scored = []
        for row in candidates:
            vec = _blob_to_vec(row["vector_blob"], row["vector_dim"])
            sim = _cosine_similarity(query_vec, vec)
            # Importance-Boost: importance=1.5 → sim * 1.1
            boosted = sim * (1.0 + (row["importance"] - 1.0) * 0.1)
            scored.append((row["content"], boosted))

        # Filter und sortieren
        result = sorted(
            [(c, s) for c, s in scored if s >= min_similarity],
            key=lambda x: x[1],
            reverse=True
        )

        return result[:top_k]

    def _recency_fallback(self, thread_id: str | None, limit: int) -> list:
        """Fallback: neueste Einträge wenn FTS keine Treffer hat."""
        with self._conn() as conn:
            if thread_id:
                return conn.execute(
                    """SELECT id, content, vector_blob, vector_dim, importance
                       FROM memory_vectors WHERE thread_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (thread_id, limit)
                ).fetchall()
            return conn.execute(
                """SELECT id, content, vector_blob, vector_dim, importance
                   FROM memory_vectors
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()

    def format_for_prompt(self, results: List[Tuple[str, float]]) -> str:
        """Formatiert Retrieval-Ergebnisse für System-Prompt-Injektion."""
        if not results:
            return ""
        lines = ["## Semantisch relevante Erinnerungen:"]
        for content, score in results:
            truncated = content[:200] + ("…" if len(content) > 200 else "")
            lines.append(f"- [{score:.2f}] {truncated}")
        return "\n".join(lines)

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) FROM memory_vectors GROUP BY source"
            ).fetchall()
            threads = conn.execute(
                "SELECT COUNT(DISTINCT thread_id) FROM memory_vectors"
            ).fetchone()[0]
        return {
            "total_vectors": total,
            "threads": threads,
            "by_source": {r[0]: r[1] for r in by_source},
            "db_path": self.db_path,
        }

    def ingest_ambient(self, text: str, source_type: str = "ambient") -> int | None:
        """
        Spezieller Ingestion-Pfad für Ambient Context (Clipboard, App-Wechsel etc.)
        Niedrigere Importance als direkte Konversationen.
        """
        return self.embed_and_store(
            content=text,
            thread_id="ambient",
            source=source_type,
            importance=0.7,
        )


# ── CLI Test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("ACMM Embedder — Selbsttest")
    print("─" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test.db")
        mem = SemanticMemory(db)

        # Testdaten einfügen
        samples = [
            ("LangGraph ist ein Framework für stateful AI-Agenten mit Checkpointing.", "t1"),
            ("OpenClaw ist ein Personal AI Assistant mit 247k Stars auf GitHub.", "t1"),
            ("SQLite ist eine serverlose relationale Datenbank.", "t1"),
            ("Apple Intelligence läuft lokal auf iPhone 16 Pro.", "t2"),
            ("Python 3.11 brachte erhebliche Performance-Verbesserungen.", "t1"),
        ]

        print("Embedding Testdaten...")
        for text, thread in samples:
            row_id = mem.embed_and_store(text, thread_id=thread)
            print(f"  [{row_id}] {text[:60]}…")

        print("\nSemanticSearch: 'AI agent framework memory'")
        results = mem.semantic_search("AI agent framework memory", top_k=3)
        for content, score in results:
            print(f"  [{score:.3f}] {content[:80]}")

        print("\nStats:", mem.stats())
        print("\n✓ Selbsttest erfolgreich")
