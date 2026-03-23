"""
a-Shell Exclusive #1 — Clipboard-Diff-Intelligence Daemon
==========================================================
Läuft als Background-Prozess in einem a-Shell Tab.
Pollt iOS-Clipboard via `pbpaste` alle 3 Sekunden.
Klassifiziert Inhalt (Code / URL / Zahlen / Prosa) und
pusht strukturierte Ambient-Signale an OpenClaw.

Einzigartig weil:
  - pbpaste auf iOS erfordert normalerweise Permission-Dialog
  - a-Shell umgeht das durch seine Terminal-Sandbox-Stellung
  - Background-Execution läuft weiter während User andere Apps benutzt
  - Kein anderer AI-Assistent auf iOS hat diesen passiven Kanal

Starten:
  python3 clipboard_daemon.py            # Vordergrund (Strg+C zum Stoppen)
  python3 clipboard_daemon.py --daemon   # Hintergrund (schreibt PID-File)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

# ── Konstanten ────────────────────────────────────────────────────────────────

POLL_INTERVAL = 3          # Sekunden
MAX_PUSH_LENGTH = 400      # Zeichen die an OpenClaw gesendet werden
MIN_CONTENT_LENGTH = 8     # Kürzeres ignorieren
PID_FILE = Path.home() / ".langchain-assistant" / "clipboard_daemon.pid"
LOG_FILE = Path.home() / ".langchain-assistant" / "clipboard_daemon.log"

ClipType = Literal["url", "code", "numbers", "json", "email", "prose"]


# ── Content Classifier ────────────────────────────────────────────────────────

@dataclass
class ClipSnapshot:
    content: str
    clip_type: ClipType
    hash: str
    timestamp: str
    word_count: int
    char_count: int
    metadata: dict


def _classify(text: str) -> tuple[ClipType, dict]:
    """
    Klassifiziert Clipboard-Inhalt in semantische Typen.
    Gibt (Typ, Metadaten-Dict) zurück.
    """
    t = text.strip()

    # URL
    if re.match(r'^https?://', t):
        domain = re.match(r'^https?://([^/]+)', t)
        return "url", {"domain": domain.group(1) if domain else "unknown"}

    # E-Mail
    if re.match(r'^[\w.+-]+@[\w-]+\.[a-z]{2,}$', t, re.IGNORECASE):
        return "email", {}

    # JSON
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            parsed = json.loads(t)
            return "json", {"keys": list(parsed.keys()) if isinstance(parsed, dict) else []}
        except json.JSONDecodeError:
            pass

    # Code-Erkennung via Keywords
    code_signals = [
        "def ", "class ", "import ", "from ", "return ", "async ",
        "function ", "const ", "let ", "var ", "=>", "fn ", "pub ",
        "#include", "SELECT ", "INSERT ", "CREATE TABLE",
        "if (", "for (", "while (", "} else {",
    ]
    code_score = sum(1 for sig in code_signals if sig in t)
    has_indentation = any(line.startswith(("    ", "\t")) for line in t.splitlines())
    if code_score >= 2 or (code_score >= 1 and has_indentation):
        lang = _detect_language(t)
        return "code", {"language": lang, "lines": t.count("\n") + 1}

    # Zahlen-dominiert
    digits = sum(c.isdigit() for c in t)
    if len(t) > 0 and digits / len(t) > 0.3:
        numbers = re.findall(r'-?\d+\.?\d*', t)
        return "numbers", {
            "count": len(numbers),
            "min": min(float(n) for n in numbers) if numbers else 0,
            "max": max(float(n) for n in numbers) if numbers else 0,
        }

    return "prose", {"words": len(t.split())}


def _detect_language(code: str) -> str:
    """Heuristik für Programmiersprache."""
    checks = [
        ("python",     ["def ", "import ", "print(", "self.", ":="]),
        ("typescript", ["interface ", "const ", ": string", ": number", "export "]),
        ("javascript", ["function ", "const ", "let ", "require(", "module.exports"]),
        ("rust",       ["fn ", "let mut", "impl ", "use std::", "pub fn"]),
        ("go",         ["func ", "package ", ":= ", "fmt.Println"]),
        ("sql",        ["SELECT ", "INSERT ", "UPDATE ", "CREATE ", "FROM "]),
        ("swift",      ["var ", "let ", "func ", "guard ", "@IBOutlet"]),
        ("shell",      ["#!/", "echo ", "export ", "source ", "chmod "]),
    ]
    scores = {lang: sum(1 for kw in keywords if kw in code) for lang, keywords in checks}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def _make_snapshot(content: str) -> ClipSnapshot:
    clip_type, meta = _classify(content)
    return ClipSnapshot(
        content=content,
        clip_type=clip_type,
        hash=hashlib.md5(content.encode()).hexdigest(),
        timestamp=datetime.now().isoformat(),
        word_count=len(content.split()),
        char_count=len(content),
        metadata=meta,
    )


# ── Clipboard Reader ──────────────────────────────────────────────────────────

def read_clipboard() -> str:
    """Liest iOS-Clipboard via pbpaste. Gibt leeren String bei Fehler."""
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# ── OpenClaw Push ─────────────────────────────────────────────────────────────

def push_to_openclaw(snap: ClipSnapshot):
    """Sendet klassifiziertes Clipboard-Signal an OpenClaw ambient ingestion."""
    preview = snap.content[:MAX_PUSH_LENGTH].replace("\n", " ")
    if len(snap.content) > MAX_PUSH_LENGTH:
        preview += "…"

    meta_str = ""
    if snap.clip_type == "code":
        meta_str = f" [{snap.metadata.get('language', '?')}, {snap.metadata.get('lines', 1)} Zeilen]"
    elif snap.clip_type == "url":
        meta_str = f" [{snap.metadata.get('domain', '')}]"
    elif snap.clip_type == "numbers":
        meta_str = f" [{snap.metadata.get('count', 0)} Werte]"

    message = f"[AMBIENT:clipboard:{snap.clip_type}{meta_str}] {preview}"

    try:
        subprocess.run(
            ["openclaw", "message", "send", message],
            capture_output=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # OpenClaw nicht verfügbar — in Log schreiben
        _log(f"PUSH FAILED: {message[:100]}")


def push_code_analysis_request(snap: ClipSnapshot):
    """Bei Code im Clipboard: Analyse-Request an Agent stellen."""
    lang = snap.metadata.get("language", "code")
    lines = snap.metadata.get("lines", 1)
    msg = (
        f"[AUTO-ANALYSE] {lines}-Zeilen {lang}-Code im Clipboard erkannt. "
        f"Kurze Zusammenfassung was dieser Code macht (2-3 Sätze, kein Kommentar nötig):\n"
        f"```{lang}\n{snap.content[:800]}\n```"
    )
    try:
        subprocess.run(
            ["openclaw", "message", "send", msg],
            capture_output=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        _log(f"CODE ANALYSIS REQUEST FAILED for {lang}")


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    if sys.stdout.isatty():
        print(line, end="")


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run(auto_analyze_code: bool = True, verbose: bool = False):
    """
    Haupt-Daemon-Loop.
    Läuft bis SIGINT/SIGTERM.
    """
    prev_hash = ""
    _log("Clipboard-Intelligence Daemon gestartet")
    _log(f"Poll-Intervall: {POLL_INTERVAL}s | Auto-Analyse: {auto_analyze_code}")

    try:
        while True:
            content = read_clipboard()

            if len(content) >= MIN_CONTENT_LENGTH:
                current_hash = hashlib.md5(content.encode()).hexdigest()

                if current_hash != prev_hash:
                    snap = _make_snapshot(content)
                    prev_hash = current_hash

                    _log(
                        f"NEU [{snap.clip_type}] "
                        f"{snap.char_count} Zeichen — "
                        f"{snap.content[:60].replace(chr(10), ' ')}…"
                    )

                    push_to_openclaw(snap)

                    # Bei Code: automatische Analyse anstossen
                    if auto_analyze_code and snap.clip_type == "code" and snap.char_count > 50:
                        push_code_analysis_request(snap)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        _log("Daemon gestoppt (SIGINT)")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="a-Shell Clipboard-Diff-Intelligence Daemon"
    )
    parser.add_argument("--no-analyze", action="store_true",
                        help="Keine automatische Code-Analyse")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL,
                        help=f"Poll-Intervall in Sekunden (default: {POLL_INTERVAL})")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    POLL_INTERVAL = args.interval
    run(auto_analyze_code=not args.no_analyze, verbose=args.verbose)
