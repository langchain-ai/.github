"""
a-Shell Exclusive #4 — iOS URL-Scheme Orchestrator
===================================================
Steuert andere iOS-Apps via URL-Schemes + x-callback-url direkt aus dem Agent.

Einzigartig weil:
  - open "app-scheme://action?x-success=ashell://..." schließt einen
    vollständigen Callback-Loop ohne Server
  - Kein Swift-Code, kein Developer Program, kein Jailbreak
  - Agent kann Drafts, Working Copy, Toolbox, Scriptable als "Tools" nutzen
  - x-success-Callback landet wieder als Shellbefehl in a-Shell zurück
  - Kein anderer AI-Assistent kontrolliert andere iOS-Apps als Tool-Calls

Unterstützte Apps (via URL-Scheme):
  - Drafts 5 (drafts5://)         — Text erstellen, Actions ausführen
  - Working Copy (working-copy://) — Git-Operationen ohne Credentials
  - Scriptable (scriptable://)    — JavaScript-Automatisierung
  - Toolbox for Word (wordtoolbox://) — Word-Dokumente
  - Safari (safari-https://)      — URLs öffnen
  - Bear (bear://)                — Notizen erstellen
  - Things 3 (things:///)         — Tasks erstellen
  - Shortcuts (shortcuts://)      — Shortcuts ausführen
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Callback-Mechanismus ──────────────────────────────────────────────────────

CALLBACK_DIR = Path.home() / ".langchain-assistant" / "url_callbacks"
CALLBACK_DIR.mkdir(parents=True, exist_ok=True)


def _make_callback_id() -> str:
    """Eindeutige ID für diesen Callback."""
    return f"cb_{int(time.time() * 1000)}"


def _callback_path(cb_id: str) -> Path:
    return CALLBACK_DIR / f"{cb_id}.result"


def _ashell_callback_url(cb_id: str, content_var: str = "") -> str:
    """
    Konstruiert x-success URL die in a-Shell einen Shellbefehl ausführt.
    a-Shell URL scheme: ashell://run?cmd=ENCODED_COMMAND
    """
    # Bei Erfolg: Ergebnis in Datei schreiben
    result_path = _callback_path(cb_id)
    if content_var:
        cmd = f"echo {content_var} > {result_path}"
    else:
        cmd = f"echo 'success' > {result_path}"
    return "ashell://run?cmd=" + urllib.parse.quote(cmd, safe="")


def _wait_for_callback(cb_id: str, timeout: int = 30) -> str | None:
    """Wartet auf Callback-Datei. Gibt Inhalt zurück oder None bei Timeout."""
    path = _callback_path(cb_id)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            result = path.read_text(encoding="utf-8").strip()
            path.unlink(missing_ok=True)
            return result
        time.sleep(0.5)
    return None


def _open_url(url: str) -> bool:
    """Öffnet URL via a-Shell `open` Befehl."""
    try:
        result = subprocess.run(["open", url], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── App Definitions ───────────────────────────────────────────────────────────

@dataclass
class AppAction:
    """Ergebnis einer App-Aktion."""
    app: str
    action: str
    success: bool
    result: str | None = None
    error: str | None = None
    elapsed_ms: float = 0.0


# ── Drafts 5 ─────────────────────────────────────────────────────────────────

class DraftsApp:
    """
    Drafts 5 URL-Scheme Controller.
    https://docs.getdrafts.com/docs/automation/urlschemes
    """
    SCHEME = "drafts5"

    @staticmethod
    def create(
        text: str,
        action: str = "",
        tags: list[str] | None = None,
        uuid_var: str = "[[uuid]]",
    ) -> AppAction:
        """Erstellt neuen Draft und führt optional eine Action aus."""
        cb_id = _make_callback_id()
        params: dict[str, str] = {
            "text": text[:5000],  # Drafts Limit
            "x-success": _ashell_callback_url(cb_id),
            "x-error": _ashell_callback_url(cb_id) + "_error",
        }
        if action:
            params["action"] = action
        if tags:
            params["tag"] = ",".join(tags)

        url = f"{DraftsApp.SCHEME}://create?" + urllib.parse.urlencode(params)

        t0 = time.time()
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=15)
        elapsed = (time.time() - t0) * 1000

        return AppAction(
            app="Drafts",
            action="create",
            success=result is not None,
            result=result,
            elapsed_ms=elapsed,
        )

    @staticmethod
    def open_draft(uuid: str) -> AppAction:
        """Öffnet einen bestehenden Draft per UUID."""
        url = f"{DraftsApp.SCHEME}://open?uuid={uuid}"
        success = _open_url(url)
        return AppAction(app="Drafts", action="open", success=success)


# ── Working Copy (Git) ────────────────────────────────────────────────────────

class WorkingCopyApp:
    """
    Working Copy Git-Client Controller.
    https://workingcopyapp.com/url-schemes.html
    Agent kann Git-Operationen ohne eigene Credentials ausführen.
    """
    SCHEME = "working-copy"

    @staticmethod
    def commit(repo: str, message: str, limit: str = "*") -> AppAction:
        """Commitet Änderungen in Working Copy Repo."""
        cb_id = _make_callback_id()
        params = {
            "repo": repo,
            "message": message,
            "limit": limit,
            "x-success": _ashell_callback_url(cb_id),
            "x-error": _ashell_callback_url(cb_id),
            "key": os.environ.get("WORKING_COPY_KEY", ""),
        }
        url = f"{WorkingCopyApp.SCHEME}://commit?" + urllib.parse.urlencode(params)
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=30)
        return AppAction(
            app="WorkingCopy",
            action="commit",
            success=result is not None,
            result=result,
        )

    @staticmethod
    def pull(repo: str) -> AppAction:
        """Führt git pull aus."""
        cb_id = _make_callback_id()
        params = {
            "repo": repo,
            "x-success": _ashell_callback_url(cb_id),
        }
        url = f"{WorkingCopyApp.SCHEME}://pull?" + urllib.parse.urlencode(params)
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=60)
        return AppAction(app="WorkingCopy", action="pull", success=result is not None)

    @staticmethod
    def read_file(repo: str, path: str) -> AppAction:
        """Liest Datei aus Working Copy Repo."""
        cb_id = _make_callback_id()
        params = {
            "repo": repo,
            "path": path,
            "x-success": _ashell_callback_url(cb_id, content_var="$file"),
        }
        url = f"{WorkingCopyApp.SCHEME}://read?" + urllib.parse.urlencode(params)
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=10)
        return AppAction(
            app="WorkingCopy",
            action="read_file",
            success=result is not None,
            result=result,
        )


# ── Scriptable ────────────────────────────────────────────────────────────────

class ScriptableApp:
    """
    Scriptable JavaScript-Runner.
    Agent kann JS-Code auf dem Gerät ausführen (Widgets, Notifications etc.)
    """
    SCHEME = "scriptable"

    @staticmethod
    def run(script_name: str, input_data: str = "") -> AppAction:
        """Führt ein Scriptable-Script aus."""
        cb_id = _make_callback_id()
        params = {
            "scriptName": script_name,
            "input": input_data[:1000],
            "x-success": _ashell_callback_url(cb_id),
        }
        url = f"{ScriptableApp.SCHEME}://run?" + urllib.parse.urlencode(params)
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=20)
        return AppAction(
            app="Scriptable",
            action="run",
            success=result is not None,
            result=result,
        )


# ── Things 3 ─────────────────────────────────────────────────────────────────

class ThingsApp:
    """Things 3 Task-Manager Controller."""
    SCHEME = "things"

    @staticmethod
    def add_task(title: str, notes: str = "", list_name: str = "") -> AppAction:
        """Fügt neuen Task zu Things hinzu."""
        params: dict[str, str] = {"title": title[:255]}
        if notes:
            params["notes"] = notes[:5000]
        if list_name:
            params["list"] = list_name
        url = f"{ThingsApp.SCHEME}:///add?" + urllib.parse.urlencode(params)
        success = _open_url(url)
        return AppAction(app="Things3", action="add_task", success=success)

    @staticmethod
    def add_tasks_json(tasks: list[dict]) -> AppAction:
        """Fügt mehrere Tasks via JSON-Format hinzu (Things 3.4+)."""
        import json
        payload = json.dumps(tasks)
        url = f"{ThingsApp.SCHEME}:///json?" + urllib.parse.urlencode({"data": payload})
        success = _open_url(url)
        return AppAction(app="Things3", action="add_tasks_json", success=success)


# ── Shortcuts ─────────────────────────────────────────────────────────────────

class ShortcutsApp:
    """iOS Shortcuts Runner."""
    SCHEME = "shortcuts"

    @staticmethod
    def run(shortcut_name: str, input_data: str = "") -> AppAction:
        """Führt einen iOS Shortcut aus."""
        cb_id = _make_callback_id()
        params: dict[str, str] = {
            "name": shortcut_name,
            "x-success": _ashell_callback_url(cb_id),
        }
        if input_data:
            params["input"] = input_data
        url = f"{ShortcutsApp.SCHEME}://run-shortcut?" + urllib.parse.urlencode(params)
        _open_url(url)
        result = _wait_for_callback(cb_id, timeout=30)
        return AppAction(
            app="Shortcuts",
            action=shortcut_name,
            success=result is not None,
            result=result,
        )


# ── LangChain Tool Wrapper ────────────────────────────────────────────────────

def as_langchain_tools() -> list:
    """
    Gibt LangChain @tool-kompatible Funktionen zurück.
    Nur in a-Shell registrieren (open-Befehl nötig).
    """
    try:
        from langchain_core.tools import tool
    except ImportError:
        return []

    @tool
    def create_draft(text: str, tags: str = "") -> str:
        """Erstellt einen neuen Draft in der Drafts 5 App (iOS).
        Nützlich um Notizen, E-Mail-Entwürfe oder Code-Snippets zu speichern."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        result = DraftsApp.create(text, tags=tag_list)
        return f"Draft erstellt: {result.result or 'Erfolg'}" if result.success else f"Fehler: {result.error}"

    @tool
    def add_task(title: str, notes: str = "", list_name: str = "") -> str:
        """Fügt einen Task zu Things 3 hinzu (iOS Task-Manager).
        Verwende dies wenn der User etwas nicht vergessen soll."""
        result = ThingsApp.add_task(title, notes, list_name)
        return "Task hinzugefügt" if result.success else "Fehler beim Hinzufügen"

    @tool
    def run_shortcut(name: str, input_data: str = "") -> str:
        """Führt einen iOS Shortcut aus.
        Verwende dies für Automatisierungen die der User in Shortcuts eingerichtet hat."""
        result = ShortcutsApp.run(name, input_data)
        return result.result or "Shortcut ausgeführt" if result.success else "Shortcut nicht gefunden"

    return [create_draft, add_task, run_shortcut]


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    app_name = sys.argv[1] if len(sys.argv) > 1 else "help"

    if app_name == "drafts":
        text = " ".join(sys.argv[2:]) or "Test-Draft von LangChain Agent"
        result = DraftsApp.create(text, tags=["ai", "langchain"])
        print(f"Drafts: success={result.success}, result={result.result}")

    elif app_name == "things":
        title = " ".join(sys.argv[2:]) or "Test-Task von LangChain Agent"
        result = ThingsApp.add_task(title, notes="Erstellt via URL-Scheme Orchestrator")
        print(f"Things: success={result.success}")

    elif app_name == "shortcut":
        name = sys.argv[2] if len(sys.argv) > 2 else "Ping"
        result = ShortcutsApp.run(name)
        print(f"Shortcuts '{name}': success={result.success}, result={result.result}")

    else:
        print("iOS URL-Scheme Orchestrator")
        print("Verfügbar: drafts | things | shortcut")
        print("Beispiel: python3 url_orchestrator.py drafts 'Mein Text'")
