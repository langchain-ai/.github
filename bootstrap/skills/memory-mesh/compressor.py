"""
ACMM — Memory Compressor
=========================
Komprimiert akkumulierte Exchanges zu dauerhaften "Memory Facts"
via Claude Haiku 4.5 (schnell + günstig).

Warum Kompression?
  Nach 10k+ Exchanges wird chronologisches Memory nutzlos.
  Kompression destilliert "was weiß der Agent?" in Facts die:
    - Semantisch suchbar sind
    - Nicht wachsen (bounded storage)
    - Offline rekonstruierbar sind

Modus:
  - Automatisch: nach je 20 neuen Exchanges pro Thread
  - Manuell: compressor.compress_thread(thread_id)
  - Ambient: komprimiert passive Kontextsignale täglich
"""

from __future__ import annotations

import os
import sqlite3
from typing import List

from anthropic import Anthropic

from embedder import SemanticMemory


# ── Komprimierungs-Prompts ────────────────────────────────────────────────────

COMPRESS_PROMPT = """Du bist ein Gedächtnis-Destillations-System.

Dir werden {n} Konversations-Exchanges gegeben. Extrahiere daraus die
wichtigsten dauerhaften Facts — Dinge die in zukünftigen Konversationen
relevant sein könnten.

FORMAT — gib NUR eine nummerierte Liste zurück, keine Erklärungen:
1. [Konkretes Fact über den User oder ihr Projekt]
2. [Konkretes Fact über verwendete Technologien oder Präferenzen]
3. [Konkretes Fact über offene Probleme oder nächste Schritte]
...

REGELN:
- Maximal 10 Facts
- Jedes Fact: 1-2 Sätze, konkret und spezifisch
- Keine generischen Aussagen ("Der User mag Python")
- Lieber leer als unspezifisch

EXCHANGES:
{exchanges}"""

AMBIENT_COMPRESS_PROMPT = """Du bist ein Kontext-Analyse-System für einen AI-Assistenten.

Dir werden passive Kontext-Signale vom iOS-Gerät des Users gegeben
(App-Wechsel, Clipboard-Inhalt, Focus-Mode-Änderungen etc.).

Extrahiere daraus eine kompakte Zusammenfassung des aktuellen Nutzungskontexts.
1-3 Sätze. Konkret. Nützlich für einen Assistenten der gleich gefragt wird.

KONTEXT-SIGNALE:
{signals}"""


# ── Compressor ────────────────────────────────────────────────────────────────

class MemoryCompressor:
    """
    Haiku-basierter Memory-Kompressor.
    Läuft automatisch wenn COMPRESS_AFTER neue Exchanges in einem Thread.
    """

    COMPRESS_AFTER = 20  # Exchanges bis zur Kompression
    MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, db_path: str, semantic_memory: SemanticMemory):
        self.db_path = db_path
        self.sem = semantic_memory
        self._client: Anthropic | None = None

    def _get_client(self) -> Anthropic:
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt")
            self._client = Anthropic(api_key=api_key)
        return self._client

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def check_and_compress(self, thread_id: str) -> bool:
        """
        Prüft ob der Thread komprimiert werden soll.
        Gibt True zurück wenn Kompression durchgeführt wurde.
        """
        with self._conn() as conn:
            # Exchanges seit letzter Kompression
            last_compress = conn.execute(
                """SELECT created_at FROM exchanges
                   WHERE thread_id = ? AND human LIKE '[COMPRESSED%'
                   ORDER BY created_at DESC LIMIT 1""",
                (thread_id,)
            ).fetchone()

            if last_compress:
                since_sql = "AND created_at > ?"
                since_params = [thread_id, last_compress[0]]
            else:
                since_sql = ""
                since_params = [thread_id]

            count = conn.execute(
                f"""SELECT COUNT(*) FROM exchanges
                    WHERE thread_id = ? {since_sql}
                    AND human NOT LIKE '[COMPRESSED%'""",
                since_params
            ).fetchone()[0]

        if count >= self.COMPRESS_AFTER:
            self.compress_thread(thread_id)
            return True
        return False

    def compress_thread(self, thread_id: str) -> List[str]:
        """
        Liest neueste N Exchanges, komprimiert zu Facts,
        speichert Facts in SemanticMemory, markiert Exchanges als komprimiert.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT human, assistant FROM exchanges
                   WHERE thread_id = ?
                   AND human NOT LIKE '[COMPRESSED%'
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (thread_id, self.COMPRESS_AFTER)
            ).fetchall()

        if not rows:
            return []

        exchanges_text = "\n".join(
            f"User: {h}\nAssistant: {a}" for h, a in rows
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": COMPRESS_PROMPT.format(
                        n=len(rows),
                        exchanges=exchanges_text[:6000]  # Token-Limit
                    )
                }]
            )
            facts_text = response.content[0].text.strip()
        except Exception as e:
            return [f"[COMPRESSION ERROR] {e}"]

        # Facts parsen und in SemanticMemory speichern
        facts = []
        for line in facts_text.splitlines():
            line = line.strip()
            # Nummern wie "1." "2." entfernen
            if line and line[0].isdigit():
                fact = line.split(".", 1)[-1].strip()
                if len(fact) > 20:
                    facts.append(fact)
                    self.sem.embed_and_store(
                        content=fact,
                        thread_id=thread_id,
                        source="fact",
                        importance=1.5,  # Facts haben höhere Importance
                    )

        # Original-Exchanges als komprimiert markieren (nicht löschen — auditierbar)
        if facts:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO exchanges (thread_id, human, assistant)
                       VALUES (?, ?, ?)""",
                    (
                        thread_id,
                        f"[COMPRESSED {len(rows)} exchanges]",
                        "\n".join(f"- {f}" for f in facts)
                    )
                )

        return facts

    def compress_ambient(self, signals: List[str]) -> str | None:
        """
        Komprimiert passive Ambient-Signale zu einer Kontext-Zusammenfassung.
        Wird täglich vom Scheduler aufgerufen.
        """
        if not signals:
            return None

        signals_text = "\n".join(f"- {s}" for s in signals[-50:])  # Max 50 Signale

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.MODEL,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": AMBIENT_COMPRESS_PROMPT.format(signals=signals_text)
                }]
            )
            summary = response.content[0].text.strip()
        except Exception as e:
            return None

        # Als Ambient-Fact speichern
        self.sem.embed_and_store(
            content=summary,
            thread_id="ambient",
            source="ambient_summary",
            importance=1.2,
        )

        return summary
