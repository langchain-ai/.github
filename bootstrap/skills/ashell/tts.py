"""
a-Shell Exclusive #2 — iOS Text-to-Speech Rückkanal
=====================================================
Nutzt `say -v [voice] -r [rate]` für multimodale Agent-Ausgabe.

Einzigartig weil:
  - iOS AVSpeechSynthesizer mit 60+ Stimmen direkt aus Shell
  - Keine App-Entitlement, keine Microphone-Permission nötig
  - Kognitive Modalitäts-Trennung: HÖREN während LESEN
  - Pair-Programming-Feeling: Reviewer spricht, Developer scrollt
  - Kein anderer AI-Code-Reviewer hat diesen auditiven Rückkanal

Verwendung:
  from tts import speak, code_review_speak, announce

  speak("Analyse abgeschlossen", severity="info")
  code_review_speak(findings)
  announce("Neue Nachricht von LangChain")
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Literal

# ── Stimmen-Konfiguration (iOS built-in voices) ───────────────────────────────
#
# Deutsche Stimmen: Anna (de-DE), Helena (de-DE), Martin (de-DE)
# Englische Stimmen: Samantha, Karen, Daniel, Moira, Rishi, Nora
# Automatisch nach System-Sprache wählen oder via ENV überschreiben

import os
_LANG = os.environ.get("ACMM_TTS_LANG", "auto")

# Stimmen-Profile nach Severity
VOICES_EN = {
    "critical":  {"voice": "Samantha", "rate": 158, "desc": "klar, direkt"},
    "warning":   {"voice": "Karen",    "rate": 142, "desc": "ruhig, präzise"},
    "info":      {"voice": "Daniel",   "rate": 148, "desc": "freundlich"},
    "positive":  {"voice": "Moira",    "rate": 150, "desc": "warm"},
    "announce":  {"voice": "Rishi",    "rate": 145, "desc": "neutral"},
    "whisper":   {"voice": "Nora",     "rate": 135, "desc": "leise Hinweise"},
}

VOICES_DE = {
    "critical":  {"voice": "Anna",    "rate": 155, "desc": "klar"},
    "warning":   {"voice": "Helena",  "rate": 140, "desc": "ruhig"},
    "info":      {"voice": "Martin",  "rate": 145, "desc": "freundlich"},
    "positive":  {"voice": "Anna",    "rate": 150, "desc": "warm"},
    "announce":  {"voice": "Martin",  "rate": 148, "desc": "neutral"},
    "whisper":   {"voice": "Helena",  "rate": 130, "desc": "leise"},
}

Severity = Literal["critical", "warning", "info", "positive", "announce", "whisper"]


def _is_ashell() -> bool:
    """Prüft ob wir in a-Shell laufen."""
    return (
        os.environ.get("A_SHELL_SESSION") is not None
        or os.path.isdir("/private/var/mobile")
        or subprocess.run(
            ["which", "say"], capture_output=True
        ).returncode == 0
    )


def _get_voices() -> dict:
    lang = _LANG
    if lang == "auto":
        # System-Sprache ermitteln
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True, text=True, timeout=2
            )
            lang = "de" if '"de"' in result.stdout else "en"
        except Exception:
            lang = "en"
    return VOICES_DE if lang == "de" else VOICES_EN


# ── Core speak() ──────────────────────────────────────────────────────────────

def speak(
    text: str,
    severity: Severity = "info",
    blocking: bool = True,
    max_chars: int = 300,
) -> bool:
    """
    Spricht Text via iOS `say` Befehl.

    Args:
        text:     Zu sprechender Text (Markdown wird bereinigt)
        severity: Stimmen-Profil
        blocking: True = wartet bis Sprache fertig, False = async
        max_chars: Maximale Textlänge (Rest wird abgeschnitten)

    Returns:
        True bei Erfolg, False wenn say nicht verfügbar
    """
    if not _is_ashell():
        print(f"[TTS:{severity}] {text}")  # Fallback für Nicht-iOS
        return False

    # Markdown bereinigen
    clean = (
        text.replace("**", "").replace("*", "").replace("`", "")
        .replace("#", "").replace("|", ",").replace("→", "zu")
        .replace("←", "von").replace("✓", "OK").replace("✗", "Fehler")
    )

    if len(clean) > max_chars:
        clean = clean[:max_chars] + "."

    voices = _get_voices()
    profile = voices.get(severity, voices["info"])

    cmd = ["say", "-v", profile["voice"], "-r", str(profile["rate"]), clean]

    try:
        if blocking:
            subprocess.run(cmd, timeout=60)
        else:
            subprocess.Popen(cmd)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def pause(seconds: float = 0.8):
    """Kurze Pause zwischen Sprachausgaben — natürlicheres Timing."""
    time.sleep(seconds)


# ── Code Review Voice Output ──────────────────────────────────────────────────

@dataclass
class ReviewFinding:
    message: str
    severity: Severity
    line: int | None = None
    file: str | None = None


def code_review_speak(findings: list[ReviewFinding], intro: bool = True):
    """
    Spricht Code-Review-Findings in priorisierter Reihenfolge.
    Kritische Issues zuerst, dann Warnings, dann Info.

    Der Developer liest den Code, während der Agent die Review spricht.
    Kognitive Modalitäts-Trennung — einzigartig auf a-Shell iOS.
    """
    if not findings:
        speak("Keine Probleme gefunden. Code sieht gut aus.", "positive")
        return

    # Sortieren: critical → warning → info → positive
    priority_order = {"critical": 0, "warning": 1, "info": 2, "positive": 3, "whisper": 4}
    sorted_findings = sorted(findings, key=lambda f: priority_order.get(f.severity, 5))

    # Zähler
    n_critical = sum(1 for f in findings if f.severity == "critical")
    n_warning = sum(1 for f in findings if f.severity == "warning")

    if intro:
        total = len(findings)
        if n_critical:
            speak(
                f"Code-Review: {total} Findings, davon {n_critical} kritisch.",
                "critical"
            )
        else:
            speak(f"Code-Review: {total} Findings.", "info")
        pause(1.2)

    for finding in sorted_findings:
        # Standort-Prefix
        location = ""
        if finding.file:
            location += finding.file.split("/")[-1]  # Nur Dateiname
        if finding.line:
            location += f" Zeile {finding.line}"

        text = f"{location}: {finding.message}" if location else finding.message
        speak(text, finding.severity, blocking=True)
        pause(0.9)


# ── Announce — für proaktive Nachrichten ─────────────────────────────────────

def announce(message: str, chime: bool = False):
    """
    Proaktive Ankündigung vom Agenten (Morning Briefing, fertige Tasks etc.)
    Optionaler Chime-Ton davor via system sound.
    """
    if chime:
        try:
            # a-Shell hat afplay für System-Sounds
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Ping.aiff"],
                capture_output=True, timeout=3
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        pause(0.5)

    speak(message, "announce", blocking=True)


# ── LangChain Tool Wrapper ────────────────────────────────────────────────────
# Kann direkt als LangChain @tool registriert werden

def as_langchain_tool():
    """
    Gibt eine @tool-kompatible Funktion zurück die in agent.py registriert werden kann.
    Nur aktiviert wenn a-Shell erkannt wird.
    """
    if not _is_ashell():
        return None

    try:
        from langchain_core.tools import tool

        @tool
        def speak_aloud(text: str, severity: str = "info") -> str:
            """
            Spricht Text via iOS Text-to-Speech aus.
            Verwende dies für Ergebnisse die der User hören soll während er liest.
            severity: 'critical' | 'warning' | 'info' | 'positive' | 'announce'
            """
            sev: Severity = severity if severity in VOICES_EN else "info"  # type: ignore
            success = speak(text, sev, blocking=False)
            return "✓ Gesprochen" if success else "TTS nicht verfügbar"

        return speak_aloud
    except ImportError:
        return None


# ── CLI Selbsttest ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("a-Shell TTS — Selbsttest")
    print(f"a-Shell erkannt: {_is_ashell()}")
    print(f"Sprache: {'DE' if _get_voices() is VOICES_DE else 'EN'}")
    print()

    if "--demo" in sys.argv:
        print("Spreche Demo-Findings…")
        findings = [
            ReviewFinding("SQL Injection Risiko in Zeile 42 — User-Input wird nicht sanitisiert.", "critical", 42),
            ReviewFinding("Fehlende Fehlerbehandlung bei Netzwerk-Request.", "warning", 87),
            ReviewFinding("Diese Funktion könnte mit List Comprehension vereinfacht werden.", "info", 23),
            ReviewFinding("Gute Nutzung von Type Hints durchgehend.", "positive"),
        ]
        code_review_speak(findings)
    else:
        speak("Text-to-Speech Test erfolgreich.", "positive")
        print("Gesprochen: 'Text-to-Speech Test erfolgreich'")
        print("Starte mit --demo für vollständige Code-Review Demo")
