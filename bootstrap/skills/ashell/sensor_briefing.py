"""
a-Shell Exclusive #5 — Sensor-fused Ambient Briefing
=====================================================
Kombiniert alle verfügbaren a-Shell-Signale zu einem personalisierten
Kontext-Briefing — ohne Internet, ohne Backend, ohne Server.

Signalquellen (alle optional, graceful degradation):
  1. Uhrzeit + Wochentag          → immer verfügbar
  2. iOS Clipboard (pbpaste)       → a-Shell exklusiv
  3. Focus-Mode                    → via Signal-Datei (Shortcuts-Trigger)
  4. iCloud-Dateien (heute geändert) → ~/iCloud/ POSIX-Pfad
  5. Offene Tasks                  → ~/.langchain-assistant/open_tasks.json
  6. Letzter Agent-Kontext         → ACMM memory-mesh
  7. Ambient-Memory Signals        → ACMM SQLite

Einzigartig weil:
  - Kombiniert 7 Signalquellen die auf KEINER anderen Plattform gleichzeitig
    verfügbar sind (iOS-exklusiv: pbpaste, iCloud-POSIX, Focus-Mode)
  - Läuft vollständig offline (kein API-Call für Signalsammlung)
  - Nur Haiku-Kompression ist API-abhängig (und graceful offline degradiert)
  - Proaktiv: Agent sendet Briefing ohne User-Anfrage (via scheduler.py)
  - Keine andere OSS-Lösung kombiniert diese 7 Quellen

Verwendung:
  briefing = SensorBriefing()
  state = briefing.gather()          # Alle Signale sammeln (offline)
  text = await briefing.compile(state)  # Via Haiku zu Briefing komprimieren
  briefing.deliver(text)             # Via TTS + OpenClaw pushen
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional


# ── Signal State ──────────────────────────────────────────────────────────────

@dataclass
class SensorState:
    """Container für alle gesammelten Ambient-Signale."""
    # Immer verfügbar
    time_str: str = ""
    weekday: str = ""
    hour: int = 0

    # a-Shell exklusiv
    clipboard_text: str = ""
    clipboard_type: str = ""

    # Via Signal-Datei (Shortcuts-Trigger)
    focus_mode: str = ""

    # iCloud-Dateisystem
    icloud_recent_files: list[str] = field(default_factory=list)
    icloud_available: bool = False

    # Tasks
    open_tasks: list[str] = field(default_factory=list)

    # ACMM Memory
    recent_memory_facts: list[str] = field(default_factory=list)
    acmm_available: bool = False

    # Meta
    signals_count: int = 0
    gathered_at: str = ""


# ── Signal Collectors ─────────────────────────────────────────────────────────

def _collect_time() -> dict:
    now = datetime.now()
    return {
        "time_str": now.strftime("%H:%M"),
        "weekday": now.strftime("%A"),   # English weekday name
        "hour": now.hour,
    }


def _collect_clipboard() -> dict:
    """pbpaste — a-Shell exklusiv."""
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        )
        text = result.stdout.strip()
        if len(text) < 8:
            return {}

        # Typ-Klassifikation (vereinfacht)
        if text.startswith(("http://", "https://")):
            clip_type = "url"
        elif any(kw in text for kw in ["def ", "class ", "function ", "const ", "import "]):
            clip_type = "code"
        else:
            clip_type = "text"

        return {
            "clipboard_text": text[:300],
            "clipboard_type": clip_type,
        }
    except Exception:
        return {}


def _collect_focus() -> dict:
    """Focus-Mode via Signal-Datei die ein iOS Shortcut schreibt."""
    focus_file = Path.home() / "Documents" / ".current_focus"
    if focus_file.exists():
        try:
            age_minutes = (time.time() - focus_file.stat().st_mtime) / 60
            if age_minutes < 60:  # Nur wenn aktuell (< 1h)
                return {"focus_mode": focus_file.read_text().strip()}
        except Exception:
            pass
    return {}


def _collect_icloud_files() -> dict:
    """Heute in iCloud geänderte Dateien."""
    icloud_candidates = [
        Path.home() / "iCloud",
        Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
    ]

    icloud = next((p for p in icloud_candidates if p.is_dir()), None)
    if not icloud:
        return {"icloud_available": False}

    today = date.today()
    recent = []

    try:
        for p in icloud.rglob("*"):
            if not p.is_file():
                continue
            # Versteckte Dateien und iCloud-Meta überspringen
            if any(part.startswith(".") for part in p.parts):
                continue
            if p.suffix in (".icloud", ".tmp"):
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                if mtime.date() == today:
                    # Nur Dateiname + direktes Elternverzeichnis
                    rel = p.relative_to(icloud)
                    recent.append(str(rel))
                    if len(recent) >= 15:
                        break
            except (OSError, PermissionError):
                continue
    except Exception:
        pass

    return {
        "icloud_available": True,
        "icloud_recent_files": recent,
    }


def _collect_open_tasks() -> dict:
    """Offene Tasks aus lokalem JSON (von icloud_handoff.py oder direkt)."""
    task_sources = [
        Path.home() / ".langchain-assistant" / "open_tasks.json",
        Path.home() / "iCloud" / "LangChain" / "open_tasks.json",
    ]

    for task_file in task_sources:
        if task_file.exists():
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                tasks = data.get("tasks", data if isinstance(data, list) else [])
                open_tasks = [
                    t.get("title", str(t)) for t in tasks
                    if not t.get("done", False)
                ]
                if open_tasks:
                    return {"open_tasks": open_tasks[:10]}
            except Exception:
                continue
    return {}


def _collect_acmm_facts() -> dict:
    """Letzte Memory Facts aus ACMM (memory-mesh Skill)."""
    import sys
    skill_root = Path(__file__).parent.parent
    mesh_path = skill_root / "memory-mesh"

    if not mesh_path.is_dir():
        return {"acmm_available": False}

    if str(mesh_path) not in sys.path:
        sys.path.insert(0, str(mesh_path))

    try:
        from embedder import SemanticMemory

        db_path = Path.home() / ".langchain-assistant" / "data" / "memory.db"
        if not db_path.exists():
            return {"acmm_available": True, "recent_memory_facts": []}

        mem = SemanticMemory(str(db_path))
        # Facts der letzten 48h mit hoher Importance
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                """SELECT content FROM memory_vectors
                   WHERE source = 'fact'
                   AND created_at > datetime('now', '-48 hours')
                   ORDER BY importance DESC, created_at DESC
                   LIMIT 5"""
            ).fetchall()
        facts = [r[0][:200] for r in rows]
        return {"acmm_available": True, "recent_memory_facts": facts}
    except Exception:
        return {"acmm_available": False}


# ── Main Briefing Engine ──────────────────────────────────────────────────────

class SensorBriefing:
    """
    Sensor-fused Ambient Briefing Engine.
    Sammelt alle verfügbaren a-Shell-Signale und destilliert sie
    via Claude Haiku zu einem personalisierten Kontext-Briefing.
    """

    def __init__(self):
        self.db_path = Path.home() / ".langchain-assistant" / "data" / "memory.db"

    def gather(self) -> SensorState:
        """
        Sammelt alle Signale. OFFLINE — kein API-Call.
        Graceful Degradation: fehlende Quellen werden übersprungen.
        """
        state = SensorState()
        signals_found = 0

        collectors = [
            ("time", _collect_time),
            ("clipboard", _collect_clipboard),
            ("focus", _collect_focus),
            ("icloud", _collect_icloud_files),
            ("tasks", _collect_open_tasks),
            ("acmm", _collect_acmm_facts),
        ]

        for name, collector in collectors:
            try:
                data = collector()
                for key, value in data.items():
                    if hasattr(state, key):
                        setattr(state, key, value)
                if data:
                    signals_found += 1
            except Exception:
                pass  # Jede Quelle kann ausfallen

        state.signals_count = signals_found
        state.gathered_at = datetime.now().isoformat()
        return state

    def compile_offline(self, state: SensorState) -> str:
        """
        Erstellt Briefing ohne API-Call (regelbasiert).
        Fallback wenn Haiku nicht verfügbar.
        """
        lines = [f"📊 Briefing {state.time_str} ({state.weekday})"]

        if state.focus_mode:
            lines.append(f"🎯 Focus: {state.focus_mode}")

        if state.clipboard_text:
            preview = state.clipboard_text[:80].replace("\n", " ")
            lines.append(f"📋 Clipboard ({state.clipboard_type}): {preview}…")

        if state.icloud_recent_files:
            n = len(state.icloud_recent_files)
            files = ", ".join(state.icloud_recent_files[:3])
            lines.append(f"📁 Heute bearbeitet ({n}): {files}")

        if state.open_tasks:
            n = len(state.open_tasks)
            lines.append(f"✅ Offene Tasks ({n}): {state.open_tasks[0]}" +
                         (" und weitere…" if n > 1 else ""))

        if state.recent_memory_facts:
            lines.append(f"💡 Erinnerung: {state.recent_memory_facts[0]}")

        lines.append(f"\n_{state.signals_count} Signalquellen · {state.gathered_at[:16]}_")
        return "\n".join(lines)

    def compile_with_haiku(self, state: SensorState) -> str:
        """
        Komprimiert Signale via Claude Haiku zu natürlichem Briefing.
        API-abhängig — fällt auf compile_offline() zurück.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return self.compile_offline(state)

        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)

            # Signal-JSON für Haiku vorbereiten
            signal_summary = []
            if state.time_str:
                signal_summary.append(f"Zeit: {state.time_str} ({state.weekday})")
            if state.focus_mode:
                signal_summary.append(f"iOS Focus: {state.focus_mode}")
            if state.clipboard_text:
                signal_summary.append(
                    f"Clipboard ({state.clipboard_type}): {state.clipboard_text[:200]}"
                )
            if state.icloud_recent_files:
                signal_summary.append(
                    f"Heute in iCloud geändert: {', '.join(state.icloud_recent_files[:5])}"
                )
            if state.open_tasks:
                signal_summary.append(
                    f"Offene Tasks: {'; '.join(state.open_tasks[:3])}"
                )
            if state.recent_memory_facts:
                signal_summary.append(
                    f"Letzte Erkenntnisse: {'; '.join(state.recent_memory_facts[:2])}"
                )

            prompt = (
                "Du bist ein persönlicher AI-Assistent. "
                "Erstelle aus diesen iOS-Kontext-Signalen ein natürliches, "
                "freundliches 2-3 Satz Morgen-Briefing auf Deutsch. "
                "Sage was relevant scheint und was der User jetzt brauchen könnte. "
                "Keine Listen, kein Markdown — nur natürliche Sprache.\n\n"
                "Signale:\n" + "\n".join(f"- {s}" for s in signal_summary)
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception:
            return self.compile_offline(state)

    def deliver(self, briefing_text: str, use_tts: bool = True):
        """
        Liefert Briefing via:
          1. TTS (say) — wenn a-Shell und use_tts=True
          2. OpenClaw Message — in den Chat
        """
        if use_tts:
            try:
                from tts import announce
                announce(briefing_text, chime=True)
            except ImportError:
                pass

        # In OpenClaw-Chat pushen
        try:
            subprocess.run(
                ["openclaw", "message", "send", briefing_text],
                capture_output=True, timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"\n[BRIEFING]\n{briefing_text}\n")

    def run_briefing(self, use_tts: bool = True) -> str:
        """Vollständiger Briefing-Durchlauf: gather → compile → deliver."""
        state = self.gather()

        # Haiku wenn verfügbar, sonst offline
        text = self.compile_with_haiku(state)

        self.deliver(text, use_tts=use_tts)
        return text


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    briefing = SensorBriefing()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "gather":
        state = briefing.gather()
        print(json.dumps(asdict(state), indent=2, ensure_ascii=False))

    elif cmd == "offline":
        state = briefing.gather()
        print(briefing.compile_offline(state))

    elif cmd == "run":
        use_tts = "--no-tts" not in sys.argv
        text = briefing.run_briefing(use_tts=use_tts)
        print(f"\n[Briefing geliefert]\n{text}")

    else:
        print("Sensor Briefing Engine")
        print("Verfügbar: gather | offline | run [--no-tts]")
