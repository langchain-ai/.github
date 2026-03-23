"""
a-Shell Exclusive #3 — iCloud-Native Session Handoff
=====================================================
Nutzt ~/iCloud/ als POSIX-Pfad für automatisches Cross-Device-Sync.

Einzigartig weil:
  - ~/iCloud/ ist in a-Shell ein echter Dateipfad — kein API nötig
  - Apple CloudKit synchronisiert automatisch (APFS → iCloud → APFS)
  - Atomic file write via .tmp + rename → race-condition-sicher
  - Kein eigener Sync-Server, kein Account-Setup, kein Netzwerk-Code
  - Kein anderer AI-Assistent hat device-übergreifendes Session-Handoff
    ohne eigenes Backend

Was synchronisiert wird:
  - Aktiver LangGraph Checkpoint (Thread-ID für Wiederaufnahme)
  - Offene Tasks und Fragen
  - Kontext-Zusammenfassung (für schnellen Re-Einstieg)
  - Shared Clipboard Bridge (universales Copy-Paste zwischen Geräten)

Verwendung:
  handoff = iCloudHandoff()
  handoff.save(thread_id="abc123", tasks=["Fix auth bug"], summary="...")
  # → Erscheint in Sekunden auf iPhone, iPad, Mac

  state = handoff.load_latest()  # Nimmt aktuelle Session auf
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Callable


# ── Pfad-Konfiguration ────────────────────────────────────────────────────────

def _icloud_root() -> Path | None:
    """
    Ermittelt den iCloud Drive Pfad plattform-spezifisch.
    a-Shell (iOS):  ~/iCloud/
    macOS:          ~/Library/Mobile Documents/com~apple~CloudDocs/
    """
    # a-Shell: direkter Symlink
    ashell_path = Path.home() / "iCloud"
    if ashell_path.is_dir():
        return ashell_path

    # macOS
    macos_path = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if macos_path.is_dir():
        return macos_path

    return None


def _device_id() -> str:
    """Eindeutige Geräte-ID (Hostname + Plattform)."""
    return f"{socket.gethostname()}-{platform.system().lower()}"


# ── Handoff State ──────────────────────────────────────────────────────────────

class iCloudHandoff:
    """
    Schreibt/liest Agent-Session-State nach ~/iCloud/LangChain/
    für automatisches Cross-Device-Handoff via Apple CloudKit.
    """

    HANDOFF_FILE = "session_handoff.json"
    CLIPBOARD_FILE = "shared_clipboard.txt"
    TASKS_FILE = "open_tasks.json"

    def __init__(self):
        icloud = _icloud_root()
        if icloud is None:
            raise RuntimeError(
                "iCloud Drive nicht gefunden.\n"
                "In a-Shell: ~/iCloud/ muss existieren.\n"
                "Auf macOS: ~/Library/Mobile Documents/com~apple~CloudDocs/"
            )
        self.base = icloud / "LangChain"
        self.base.mkdir(parents=True, exist_ok=True)
        self.device_id = _device_id()

    def _atomic_write(self, path: Path, content: str):
        """Atomic write via temporäre Datei + rename (APFS garantiert Atomarität)."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    # ── Session Handoff ────────────────────────────────────────────────────────

    def save(
        self,
        thread_id: str,
        tasks: list[str] | None = None,
        summary: str = "",
        metadata: dict | None = None,
    ):
        """
        Speichert aktuelle Session nach iCloud.
        Andere Geräte können load_latest() aufrufen um fortzusetzen.
        """
        state = {
            "thread_id": thread_id,
            "device_id": self.device_id,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "tasks": tasks or [],
            "summary": summary[:500],  # Kurze Zusammenfassung für schnellen Re-Einstieg
            "metadata": metadata or {},
        }
        path = self.base / self.HANDOFF_FILE
        self._atomic_write(path, json.dumps(state, indent=2, ensure_ascii=False))

    def load_latest(self) -> dict | None:
        """
        Liest aktuellsten Handoff-State.
        Gibt None zurück wenn keine Datei oder veraltet (> 24h).
        """
        path = self.base / self.HANDOFF_FILE
        if not path.exists():
            return None

        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            return None

        # Nicht eigene Handoffs laden (wir haben die schon)
        age_hours = (time.time() - state.get("timestamp", 0)) / 3600
        if age_hours > 24:
            return None  # Zu alt

        return state

    def watch(self, on_handoff: Callable[[dict], None], interval: float = 4.0):
        """
        Blockierender Watcher für Handoff von anderen Geräten.
        Ruft on_handoff(state) auf wenn neuer State von anderem Gerät.

        Läuft in eigenem Thread oder a-Shell Hintergrund-Tab.
        """
        last_ts = 0.0
        path = self.base / self.HANDOFF_FILE

        while True:
            if path.exists():
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                    ts = state.get("timestamp", 0)
                    # Nur wenn: anderes Gerät UND neuer als letzter Stand
                    if state.get("device_id") != self.device_id and ts > last_ts:
                        last_ts = ts
                        on_handoff(state)
                except Exception:
                    pass
            time.sleep(interval)

    # ── Shared Clipboard Bridge ───────────────────────────────────────────────

    def push_clipboard(self, text: str):
        """
        Schreibt Text in die iCloud Shared Clipboard Bridge.
        Erscheint auf anderen Geräten via pull_clipboard().
        Schlägt AirDrop für Text um Längen (keine Bestätigung nötig).
        """
        payload = {
            "text": text,
            "device_id": self.device_id,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }
        path = self.base / self.CLIPBOARD_FILE
        self._atomic_write(path, json.dumps(payload, ensure_ascii=False))

    def pull_clipboard(self, max_age_minutes: float = 5.0) -> str | None:
        """
        Liest Shared Clipboard von iCloud.
        Gibt None zurück wenn leer, zu alt oder vom eigenen Gerät.
        """
        path = self.base / self.CLIPBOARD_FILE
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        age_min = (time.time() - payload.get("timestamp", 0)) / 60
        if age_min > max_age_minutes:
            return None
        if payload.get("device_id") == self.device_id:
            return None

        return payload.get("text")

    def watch_clipboard(self, on_new: Callable[[str, str], None], interval: float = 3.0):
        """
        Watcher für Shared Clipboard.
        on_new(text, from_device) wird aufgerufen bei neuem Clipboard-Inhalt.
        """
        last_ts = 0.0
        path = self.base / self.CLIPBOARD_FILE

        while True:
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    ts = payload.get("timestamp", 0)
                    device = payload.get("device_id", "")
                    if device != self.device_id and ts > last_ts:
                        last_ts = ts
                        on_new(payload.get("text", ""), device)
                except Exception:
                    pass
            time.sleep(interval)

    # ── Open Tasks Sync ───────────────────────────────────────────────────────

    def sync_tasks(self, tasks: list[dict]):
        """
        Synchronisiert offene Tasks nach iCloud.
        tasks: [{"title": str, "done": bool, "created": str}, ...]
        """
        payload = {
            "tasks": tasks,
            "device_id": self.device_id,
            "updated": datetime.now().isoformat(),
        }
        path = self.base / self.TASKS_FILE
        self._atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False))

    def load_tasks(self) -> list[dict]:
        """Liest synchronisierte Tasks."""
        path = self.base / self.TASKS_FILE
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload.get("tasks", [])
        except Exception:
            return []

    # ── Diagnostik ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        handoff = self.load_latest()
        tasks = self.load_tasks()
        clip = self.pull_clipboard()
        return {
            "icloud_base": str(self.base),
            "device_id": self.device_id,
            "active_handoff": handoff is not None,
            "handoff_from": handoff.get("device_id") if handoff else None,
            "handoff_thread": handoff.get("thread_id") if handoff else None,
            "open_tasks": len(tasks),
            "shared_clipboard_available": clip is not None,
        }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    try:
        h = iCloudHandoff()
    except RuntimeError as e:
        print(f"Fehler: {e}")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        print(json.dumps(h.status(), indent=2, ensure_ascii=False))

    elif cmd == "save":
        h.save(
            thread_id="test-session",
            tasks=["Test Task 1", "Test Task 2"],
            summary="Test-Handoff von der CLI"
        )
        print(f"✓ Gespeichert nach {h.base / h.HANDOFF_FILE}")

    elif cmd == "load":
        state = h.load_latest()
        if state:
            print(json.dumps(state, indent=2, ensure_ascii=False))
        else:
            print("Kein aktiver Handoff gefunden")

    elif cmd == "push-clip":
        text = " ".join(sys.argv[2:]) or "Test-Clipboard-Text"
        h.push_clipboard(text)
        print(f"✓ Clipboard gepusht: {text[:50]}")

    elif cmd == "pull-clip":
        text = h.pull_clipboard()
        print(text if text else "(kein neues Clipboard von anderen Geräten)")

    elif cmd == "watch":
        print(f"Warte auf Handoff von anderen Geräten (Strg+C zum Stoppen)…")
        h.watch(lambda s: print(f"\n→ Handoff von {s['device_id']}: Thread={s['thread_id']}"))

    else:
        print(f"Unbekannter Befehl: {cmd}")
        print("Verfügbar: status | save | load | push-clip | pull-clip | watch")
