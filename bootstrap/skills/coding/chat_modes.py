"""
Chat + Coding #6 — Conversation State Machine
============================================
Explizite Chat-Modi mit eigenen System-Prompts, Tool-Sets und
Memory-Strategien. Der Agent wechselt Modi basierend auf Intent.

Global-unique weil:
  Kein Chat-Interface (ChatGPT, Claude.ai, Copilot Chat) hat explizite
  Modi als First-Class-Feature mit unterschiedlichen Tool-Inventars,
  Memory-Retrieval-Strategien und Rendering-Regeln pro Modus.
  Das hier ist ein echter Konversations-Zustandsautomat.

Modi:
  CHAT          — Allgemeiner Austausch, kurze Antworten, wenig Tools
  CODING        — Deep-Coding: alle Code-Tools aktiv, ausführliche Antworten
  DEBUGGING     — CausalDiff + SmellMemory aktiv, strukturierter Output
  ARCHITECTURE  — Kein Code-Execution, konzeptuelle Diskussion, Diagramme
  PAIR_PROGRAM  — Turn-by-Turn Code-Negotiation, TTS-Review aktiv
  REVIEW        — Code-Review mit SmellMemory + CausalDiff + TTS
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ── Mode-Definition ───────────────────────────────────────────────────────────

class ChatMode(str, Enum):
    CHAT         = "chat"
    CODING       = "coding"
    DEBUGGING    = "debugging"
    ARCHITECTURE = "architecture"
    PAIR_PROGRAM = "pair_programming"
    REVIEW       = "review"


@dataclass
class ModeConfig:
    mode: ChatMode
    display_name: str
    emoji: str
    system_prompt_addendum: str
    active_tools: list[str]           # Tool-Namen die in diesem Modus aktiv sind
    memory_retrieval_strategy: str    # "semantic" | "recency" | "smell_aware"
    max_response_tokens: int
    tts_severity_map: dict[str, str]  # Tool-Output → TTS-Severity
    trigger_keywords: list[str]       # Keywords die diesen Modus aktivieren


# ── Mode-Konfigurationen ──────────────────────────────────────────────────────

MODE_CONFIGS: dict[ChatMode, ModeConfig] = {

    ChatMode.CHAT: ModeConfig(
        mode=ChatMode.CHAT,
        display_name="Chat",
        emoji="💬",
        system_prompt_addendum="""
Du bist im CHAT-Modus. Antworte kurz und direkt.
Kein unnötiger Code, keine langen Erklärungen.
Nutze Tools nur wenn explizit nötig.
""".strip(),
        active_tools=["shell_safe", "read_file"],
        memory_retrieval_strategy="recency",
        max_response_tokens=512,
        tts_severity_map={},
        trigger_keywords=["hey", "was ist", "erkläre", "wie funktioniert", "was bedeutet"],
    ),

    ChatMode.CODING: ModeConfig(
        mode=ChatMode.CODING,
        display_name="Coding Session",
        emoji="⌨️",
        system_prompt_addendum="""
Du bist im CODING-Modus. Deep-Coding-Assistent.
- Zeige immer vollständigen, lauffähigen Code
- Nutze run_python um Code zu testen bevor du ihn zeigst
- Prüfe auf Code-Smells via analyze_smells
- Bei Refactoring: verify_refactor einsetzen
- Ausführliche Erklärungen erlaubt
- Syntax-Highlighting und Code-Blöcke immer verwenden
""".strip(),
        active_tools=[
            "run_python", "read_file", "write_file", "shell_safe",
            "analyze_smells", "verify_refactor", "mine_invariants",
        ],
        memory_retrieval_strategy="semantic",
        max_response_tokens=2048,
        tts_severity_map={"error": "critical", "warning": "warning"},
        trigger_keywords=["schreib", "implementier", "code", "funktion", "klasse", "script"],
    ),

    ChatMode.DEBUGGING: ModeConfig(
        mode=ChatMode.DEBUGGING,
        display_name="Debugging",
        emoji="🐛",
        system_prompt_addendum="""
Du bist im DEBUGGING-Modus. Strukturierte Fehleranalyse.
IMMER dieser Struktur folgen:
1. **Root Cause**: Was ist der eigentliche Fehler?
2. **Kausal-Pfad**: Wie kommt es zu diesem Fehler?
3. **Fix**: Konkreter Code-Fix
4. **Verification**: Wie prüfe ich ob der Fix funktioniert?

Nutze explain_diff_failure und find_intent_breaking_commit aktiv.
Frage nach Traceback und Reproduktionsschritten wenn nicht vorhanden.
""".strip(),
        active_tools=[
            "run_python", "shell_safe", "read_file",
            "explain_diff_failure", "find_intent_breaking_commit", "analyze_smells",
        ],
        memory_retrieval_strategy="smell_aware",
        max_response_tokens=1024,
        tts_severity_map={"critical": "critical", "fix": "positive"},
        trigger_keywords=["fehler", "error", "bug", "traceback", "exception", "bricht", "kaputt", "warum funktioniert"],
    ),

    ChatMode.ARCHITECTURE: ModeConfig(
        mode=ChatMode.ARCHITECTURE,
        display_name="Architecture Review",
        emoji="🏗️",
        system_prompt_addendum="""
Du bist im ARCHITECTURE-Modus. Konzeptuelle Systemdiskussion.
- Kein Code-Execution
- Fokus auf Trade-offs, Patterns, Skalierbarkeit
- ASCII-Diagramme für Architektur-Visualisierung
- Verweise auf bekannte Patterns (CQRS, Event Sourcing, etc.)
- LangGraph/LangChain-spezifische Architektur-Empfehlungen
- Halte Antworten strukturiert: Problem → Options → Empfehlung
""".strip(),
        active_tools=["read_file", "shell_safe"],
        memory_retrieval_strategy="semantic",
        max_response_tokens=1536,
        tts_severity_map={},
        trigger_keywords=["architektur", "design", "system", "skalier", "pattern", "struktur", "wie soll ich"],
    ),

    ChatMode.PAIR_PROGRAM: ModeConfig(
        mode=ChatMode.PAIR_PROGRAM,
        display_name="Pair Programming",
        emoji="👥",
        system_prompt_addendum="""
Du bist im PAIR-PROGRAMMING-Modus. Turn-by-Turn Code-Kollaboration.
REGELN:
- Schreibe IMMER nur den nächsten kleinen Schritt — nicht die komplette Lösung
- Erkläre jeden Schritt in 1-2 Sätzen (du bist der Navigator, User ist der Driver)
- Frage nach Bestätigung bevor du weitergehst: "Soll ich so weitermachen?"
- Bei Fehlern: sofort stoppen und gemeinsam analysieren
- Nutze TTS speak_aloud für Review-Kommentare
- Baue Tests parallel zum Code

Du führst den User, der User implementiert. Pair-Mentality.
""".strip(),
        active_tools=[
            "run_python", "read_file", "write_file",
            "speak_aloud", "analyze_smells",
        ],
        memory_retrieval_strategy="semantic",
        max_response_tokens=768,
        tts_severity_map={"review": "info", "success": "positive", "problem": "warning"},
        trigger_keywords=["pair", "zusammen", "gemeinsam schreiben", "zeig mir schritt", "walk me through"],
    ),

    ChatMode.REVIEW: ModeConfig(
        mode=ChatMode.REVIEW,
        display_name="Code Review",
        emoji="🔍",
        system_prompt_addendum="""
Du bist im CODE-REVIEW-Modus. Vollständige Review mit Priorisierung.

STRUKTUR jeder Review:
## 🔴 Kritisch (muss gefixt werden)
## 🟡 Warnung (sollte gefixt werden)
## 🟢 Info (nice to have)
## ✅ Positiv (was gut ist)

Nutze analyze_smells VOR der manuellen Review.
Nutze speak_aloud für Top-3-Findings (iOS TTS).
Schließe immer mit konkreten nächsten Schritten ab.
""".strip(),
        active_tools=[
            "read_file", "analyze_smells", "speak_aloud",
            "verify_refactor", "explain_diff_failure",
        ],
        memory_retrieval_strategy="smell_aware",
        max_response_tokens=2048,
        tts_severity_map={"critical": "critical", "warning": "warning", "positive": "positive"},
        trigger_keywords=["review", "prüf", "check", "was ist falsch", "feedback", "beurteile"],
    ),
}


# ── Intent Classifier ─────────────────────────────────────────────────────────

def classify_intent(message: str, current_mode: ChatMode) -> ChatMode:
    """
    Klassifiziert die Intent einer Nachricht → empfohlener Modus.
    Schnell, lokal, kein API-Call.
    """
    msg = message.lower()

    # Explizite Modus-Wechsel (/mode oder !mode)
    explicit = re.search(r'[/!](\w+)', msg)
    if explicit:
        cmd = explicit.group(1)
        for mode in ChatMode:
            if cmd in (mode.value, mode.name.lower()):
                return mode

    # Keyword-basiertes Scoring
    scores: dict[ChatMode, int] = {mode: 0 for mode in ChatMode}

    for mode, config in MODE_CONFIGS.items():
        for kw in config.trigger_keywords:
            if kw in msg:
                scores[mode] += 1

    # Zusätzliche Heuristiken
    if re.search(r'```|def |class |import ', msg):
        scores[ChatMode.CODING] += 2
    if re.search(r'traceback|error|exception|stack trace', msg, re.I):
        scores[ChatMode.DEBUGGING] += 3
    if re.search(r'review|prüf.*code|feedback.*code', msg, re.I):
        scores[ChatMode.REVIEW] += 2
    if re.search(r'architektur|design.*system|wie.*struktur', msg, re.I):
        scores[ChatMode.ARCHITECTURE] += 2

    best = max(scores, key=scores.get)  # type: ignore
    if scores[best] == 0:
        return current_mode  # Kein klarer Intent → Modus beibehalten

    # Hysterese: Modus nur wechseln wenn Score > 1 oder explizit
    if scores[best] >= 2 or best != current_mode:
        return best
    return current_mode


# ── System-Prompt Builder ─────────────────────────────────────────────────────

def build_mode_system_prompt(
    base_prompt: str,
    mode: ChatMode,
    channel: str = "webchat",
) -> str:
    """Baut vollständigen System-Prompt für aktuellen Modus."""
    config = MODE_CONFIGS[mode]

    mode_header = (
        f"\n\n{'='*50}\n"
        f"AKTIVER MODUS: {config.emoji} {config.display_name}\n"
        f"{'='*50}\n"
        f"{config.system_prompt_addendum}"
    )

    channel_override = ""
    if channel in ("siri", "voice"):
        channel_override = "\n\nKanal: Voice — kurze, gesprochene Antworten. Kein Markdown."
    elif channel in ("telegram", "signal"):
        channel_override = "\n\nKanal: Messaging — kompakt, Plain-Text, '-' Bullets."

    return base_prompt + mode_header + channel_override


def get_active_tools_for_mode(mode: ChatMode, all_tools: list) -> list:
    """Filtert Tool-Liste auf die für diesen Modus aktiven Tools."""
    config = MODE_CONFIGS[mode]
    active_names = set(config.active_tools)
    return [t for t in all_tools if getattr(t, "name", "") in active_names]


# ── State für agent.py ────────────────────────────────────────────────────────

class ConversationStateMachine:
    """
    Verwaltet den Modus einer Konversation.
    Wird als Singleton pro thread_id gehalten.
    """
    _instances: dict[str, "ConversationStateMachine"] = {}

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.current_mode = ChatMode.CHAT
        self.mode_history: list[tuple[ChatMode, str]] = []  # (mode, reason)
        self.message_count = 0

    @classmethod
    def for_thread(cls, thread_id: str) -> "ConversationStateMachine":
        if thread_id not in cls._instances:
            cls._instances[thread_id] = cls(thread_id)
        return cls._instances[thread_id]

    def process_message(self, message: str) -> tuple[ChatMode, bool]:
        """
        Verarbeitet eingehende Nachricht → gibt (Modus, hat_gewechselt) zurück.
        """
        self.message_count += 1
        new_mode = classify_intent(message, self.current_mode)

        switched = new_mode != self.current_mode
        if switched:
            self.mode_history.append((self.current_mode, f"Wechsel nach {self.message_count} Nachrichten"))
            self.current_mode = new_mode

        return self.current_mode, switched

    def force_mode(self, mode: ChatMode):
        """Expliziter Modus-Wechsel (via /mode Befehl)."""
        if mode != self.current_mode:
            self.mode_history.append((self.current_mode, "Manuell"))
            self.current_mode = mode

    @property
    def mode_indicator(self) -> str:
        """Kurze Anzeige des aktuellen Modus für UI."""
        config = MODE_CONFIGS[self.current_mode]
        return f"{config.emoji} [{config.display_name}]"

    def status(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "current_mode": self.current_mode.value,
            "message_count": self.message_count,
            "mode_history": [(m.value, r) for m, r in self.mode_history],
        }
