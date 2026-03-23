"""
ACMM — Proactive Scheduler
===========================
Macht den Agenten erstmals PROAKTIV — er initiiert Nachrichten,
anstatt nur zu reagieren.

Jobs:
  1. morning_briefing     — täglich 08:00: offene Loops aus Memory zusammenfassen
  2. ambient_compress     — täglich 23:00: Ambient-Signale komprimieren
  3. memory_maintenance   — wöchentlich: alte Duplicate-Vectors bereinigen
  4. auto_compress        — nach je N Exchanges: Thread-Kompression

Laufzeitumgebung:
  - APScheduler (in-process, kein separater Daemon)
  - Wird von OpenClaw Pi-Agent beim Skill-Start automatisch gestartet
  - Auf a-Shell: läuft im Hintergrund-Tab
"""

from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from embedder import SemanticMemory
from compressor import MemoryCompressor

logger = logging.getLogger(__name__)

# ── Scheduler Setup ───────────────────────────────────────────────────────────

class ACMMScheduler:
    """
    Proaktiver Hintergrund-Scheduler für Memory-Maintenance und Briefings.

    Integration mit OpenClaw:
      scheduler.set_message_callback(openclaw_send_fn)
      → Ermöglicht proaktive Nachrichten an den User via OpenClaw Gateway
    """

    def __init__(
        self,
        db_path: str,
        semantic_memory: SemanticMemory,
        compressor: MemoryCompressor,
    ):
        self.db_path = db_path
        self.sem = semantic_memory
        self.compressor = compressor
        self._message_callback: Callable[[str], None] | None = None
        self._scheduler = BackgroundScheduler(timezone="local")
        self._setup_jobs()

    def set_message_callback(self, fn: Callable[[str], None]):
        """
        Registriert eine Callback-Funktion um proaktive Nachrichten zu senden.
        In OpenClaw: openclaw_send = lambda msg: openclaw.message.send(msg)
        """
        self._message_callback = fn

    def _send(self, message: str):
        """Sendet proaktive Nachricht via Callback oder loggt sie."""
        if self._message_callback:
            try:
                self._message_callback(message)
            except Exception as e:
                logger.error(f"Message callback failed: {e}")
        else:
            logger.info(f"[PROACTIVE] {message}")

    def _setup_jobs(self):
        # Morning briefing: täglich 08:00 Lokalzeit
        self._scheduler.add_job(
            self._morning_briefing,
            CronTrigger(hour=8, minute=0),
            id="morning_briefing",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Ambient compression: täglich 23:00
        self._scheduler.add_job(
            self._ambient_compress,
            CronTrigger(hour=23, minute=0),
            id="ambient_compress",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Memory maintenance: jeden Sonntag 02:00
        self._scheduler.add_job(
            self._memory_maintenance,
            CronTrigger(day_of_week="sun", hour=2, minute=0),
            id="memory_maintenance",
            replace_existing=True,
        )

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("ACMM Scheduler started")

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ── Job Implementations ────────────────────────────────────────────────────

    def _morning_briefing(self):
        """
        Täglich 08:00: Was hat der Agent über den User gelernt?
        Offene Loops und unerledigte Punkte aus dem letzten Tag.
        """
        logger.info("Running morning briefing job")

        # Gestern's Facts abrufen
        yesterday_facts = self._get_recent_facts(hours=24, source="fact")
        ambient_facts = self._get_recent_facts(hours=24, source="ambient_summary")

        if not yesterday_facts and not ambient_facts:
            return  # Nichts zu berichten

        lines = ["☀️ **Guten Morgen — was ich gestern gelernt habe:**\n"]

        if yesterday_facts:
            lines.append("**Aus deinen Gesprächen:**")
            for fact in yesterday_facts[:5]:
                lines.append(f"- {fact}")

        if ambient_facts:
            lines.append("\n**Aus deinem Kontext:**")
            for fact in ambient_facts[:3]:
                lines.append(f"- {fact}")

        lines.append("\n_Tippe eine Frage oder schreib `/new` für eine neue Session._")

        self._send("\n".join(lines))

    def _ambient_compress(self):
        """Täglich 23:00: Ambient-Signale des Tages komprimieren."""
        logger.info("Running ambient compress job")

        signals = self._get_ambient_signals_today()
        if signals:
            summary = self.compressor.compress_ambient(signals)
            if summary:
                logger.info(f"Ambient compressed: {summary[:100]}")

    def _memory_maintenance(self):
        """Wöchentlich: Bereinigung und Stats-Logging."""
        logger.info("Running memory maintenance")
        stats = self.sem.stats()
        logger.info(f"Memory stats: {stats}")

        # Alte Ambient-Signale nach 30 Tagen löschen (Facts bleiben)
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                """DELETE FROM memory_vectors
                   WHERE source = 'ambient'
                   AND created_at < datetime('now', '-30 days')"""
            ).rowcount
            if deleted:
                logger.info(f"Cleaned {deleted} old ambient vectors")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_recent_facts(self, hours: int = 24, source: str = "fact") -> list[str]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """SELECT content FROM memory_vectors
                       WHERE source = ?
                       AND created_at > datetime('now', ? || ' hours')
                       ORDER BY importance DESC, created_at DESC
                       LIMIT 10""",
                    (source, f"-{hours}")
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _get_ambient_signals_today(self) -> list[str]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """SELECT content FROM memory_vectors
                       WHERE source = 'ambient'
                       AND created_at > datetime('now', '-1 day')
                       ORDER BY created_at ASC""",
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def trigger_now(self, job_id: str):
        """Manueller Trigger für Tests und Debugging."""
        job_map = {
            "morning_briefing": self._morning_briefing,
            "ambient_compress": self._ambient_compress,
            "memory_maintenance": self._memory_maintenance,
        }
        if job_id in job_map:
            job_map[job_id]()
        else:
            raise ValueError(f"Unknown job: {job_id}. Available: {list(job_map.keys())}")
