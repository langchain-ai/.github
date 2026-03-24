"""
agent_free.py — Multi-Provider Free-Tier Agent mit Infinite Rotary
====================================================================
Rotiert automatisch durch kostenlose KI-Anbieter:
  Groq → OpenRouter → Gemini → Mistral → Anthropic (falls Credits)

Nur stdlib (urllib, json, os, sqlite3) — keine pip-Abhängigkeiten.
Läuft auf a-Shell (iOS), Termux (Android), jedem Python 3.11+.

API-Keys per Env-Variable setzen (alle optional, vorhandene werden genutzt):
  export GROQ_API_KEY=...         groq.com          — kostenlos, kein Kreditkarte
  export OPENROUTER_API_KEY=...   openrouter.ai     — kostenlos mit :free Modellen
  export GEMINI_API_KEY=...       aistudio.google.com — kostenlos, 1M Kontext
  export MISTRAL_API_KEY=...      console.mistral.ai  — kostenloser Trial
  export ANTHROPIC_API_KEY=...    console.anthropic.com — kostenpflichtig (Fallback)

Kompatibel mit handle_message(payload) Interface von agent.py / agent_mini.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ── Provider-Registry ─────────────────────────────────────────────────────────

PROVIDERS: list[dict] = [
    # ① Groq — Schnellste Inferenz, großzügiges kostenloses Tier
    {
        "name": "Groq / llama-3.3-70b",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
        "format": "openai",
    },
    {
        "name": "Groq / mixtral-8x7b",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "mixtral-8x7b-32768",
        "format": "openai",
    },
    {
        "name": "Groq / gemma2-9b",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "gemma2-9b-it",
        "format": "openai",
    },
    {
        "name": "Groq / llama-3.1-8b",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "llama-3.1-8b-instant",
        "format": "openai",
    },
    # ② OpenRouter — Kostenlose Modelle mit :free Suffix
    {
        "name": "OpenRouter / llama-3.3-70b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "format": "openai",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/langchain-ai/.github",
            "X-Title": "LangChain Free Agent",
        },
    },
    {
        "name": "OpenRouter / gemma-3-27b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model": "google/gemma-3-27b-it:free",
        "format": "openai",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/langchain-ai/.github",
            "X-Title": "LangChain Free Agent",
        },
    },
    {
        "name": "OpenRouter / qwen-2.5-72b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model": "qwen/qwen-2.5-72b-instruct:free",
        "format": "openai",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/langchain-ai/.github",
            "X-Title": "LangChain Free Agent",
        },
    },
    {
        "name": "OpenRouter / mistral-7b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model": "mistralai/mistral-7b-instruct:free",
        "format": "openai",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/langchain-ai/.github",
            "X-Title": "LangChain Free Agent",
        },
    },
    {
        "name": "OpenRouter / deepseek-r1:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model": "deepseek/deepseek-r1:free",
        "format": "openai",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/langchain-ai/.github",
            "X-Title": "LangChain Free Agent",
        },
    },
    # ③ Google Gemini — Kostenloses Tier via AI Studio (kein Kreditkarte)
    {
        "name": "Gemini / gemini-2.0-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
        "format": "openai",
    },
    {
        "name": "Gemini / gemini-1.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-1.5-flash",
        "format": "openai",
    },
    {
        "name": "Gemini / gemini-2.0-flash-lite",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash-lite",
        "format": "openai",
    },
    # ④ Mistral AI — Kostenloser Trial auf la plateforme
    {
        "name": "Mistral / mistral-small",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key_env": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
        "format": "openai",
    },
    {
        "name": "Mistral / open-mistral-7b",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key_env": "MISTRAL_API_KEY",
        "model": "open-mistral-7b",
        "format": "openai",
    },
    # ⑤ Anthropic Claude — Kostenpflichtig, letzter Fallback
    {
        "name": "Anthropic / claude-3-5-sonnet",
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "model": "claude-3-5-sonnet-20241022",
        "format": "anthropic",
    },
]


# ── HTTP Request Helpers ───────────────────────────────────────────────────────

def _call_openai(provider: dict, messages: list[dict]) -> str:
    """OpenAI-kompatibler API-Call (Groq, OpenRouter, Gemini, Mistral)."""
    key = os.environ.get(provider["key_env"], "")
    if not key:
        raise ValueError(f"Key {provider['key_env']} nicht gesetzt — überspringe")

    payload = json.dumps({
        "model": provider["model"],
        "messages": messages,
        "max_tokens": 1024,
    }).encode()

    headers: dict[str, str] = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    headers.update(provider.get("extra_headers", {}))

    req = Request(provider["url"], data=payload, headers=headers)
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_anthropic(provider: dict, messages: list[dict]) -> str:
    """Anthropic Messages API (spezielles Format)."""
    key = os.environ.get(provider["key_env"], "")
    if not key:
        raise ValueError(f"Key {provider['key_env']} nicht gesetzt — überspringe")

    payload = json.dumps({
        "model": provider["model"],
        "messages": messages,
        "max_tokens": 1024,
    }).encode()

    req = Request(
        provider["url"],
        data=payload,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


def _call_provider(provider: dict, messages: list[dict]) -> str:
    if provider["format"] == "anthropic":
        return _call_anthropic(provider, messages)
    return _call_openai(provider, messages)


# ── Infinite Rotary ────────────────────────────────────────────────────────────

def ask(
    messages: list[dict],
    start_idx: int = 0,
    verbose: bool = True,
) -> tuple[str, int]:
    """
    Rotiert durch ALLE Provider — beginnt bei start_idx, probiert jeden genau einmal.
    Gibt (Antwort, letzter_erfolgreicher_idx) zurück.
    Wirft RuntimeError wenn alle Provider fehlschlagen.

    Rotation-Logik:
      - Fehlender Key → leise überspringen
      - HTTP-Fehler (Rate-Limit, Quota) → nächster Provider
      - Netzwerkfehler / Timeout → nächster Provider
      - Erfolg → gibt Antwort + verwendeten Index zurück
    """
    n = len(PROVIDERS)
    errors: list[str] = []

    for i in range(n):
        idx = (start_idx + i) % n
        p = PROVIDERS[idx]

        try:
            response = _call_provider(p, messages)
            if verbose:
                print(f"  ✓ {p['name']}")
            return response, idx

        except ValueError as e:
            # Kein Key — leise überspringen, kein Output
            errors.append(f"{p['name']}: {e}")

        except HTTPError as e:
            body = ""
            try:
                body = ": " + e.read().decode(errors="replace")[:120]
            except Exception:
                pass
            msg = f"{p['name']}: HTTP {e.code}{body}"
            errors.append(msg)
            if verbose:
                print(f"  ✗ {p['name']}: HTTP {e.code} — nächster...")

        except Exception as e:
            msg = f"{p['name']}: {type(e).__name__}: {e}"
            errors.append(msg)
            if verbose:
                print(f"  ✗ {p['name']}: {e} — nächster...")

    detail = "\n".join(f"  • {e}" for e in errors)
    raise RuntimeError(f"Alle {n} Provider fehlgeschlagen:\n{detail}")


# ── SQLite Memory ──────────────────────────────────────────────────────────────

_DOCS = Path.home() / "Documents"
_DB_PATH = _DOCS / ".langchain-assistant" / "agent_free.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exchanges (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  TEXT NOT NULL,
            human      TEXT NOT NULL,
            assistant  TEXT NOT NULL,
            provider   TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_t ON exchanges(thread_id, id DESC)")
    conn.commit()
    return conn


def _load_history(thread_id: str, limit: int = 8) -> list[dict]:
    """Lädt letzte N Austausche als OpenAI-Messages-Liste."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT human, assistant FROM exchanges WHERE thread_id=? ORDER BY id DESC LIMIT ?",
            (thread_id, limit),
        ).fetchall()
    messages: list[dict] = []
    for human, assistant in reversed(rows):
        messages.append({"role": "user", "content": human})
        messages.append({"role": "assistant", "content": assistant})
    return messages


def _save_exchange(thread_id: str, human: str, assistant: str, provider_name: str) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO exchanges (thread_id, human, assistant, provider) VALUES (?,?,?,?)",
            (thread_id, human[:2000], assistant[:4000], provider_name),
        )
        # Max 200 Einträge pro Thread behalten
        conn.execute(
            """DELETE FROM exchanges WHERE thread_id=? AND id NOT IN
               (SELECT id FROM exchanges WHERE thread_id=? ORDER BY id DESC LIMIT 200)""",
            (thread_id, thread_id),
        )
        conn.commit()


# ── Main Agent ─────────────────────────────────────────────────────────────────

def run_agent(
    user_message: str,
    thread_id: str = "default",
    start_provider_idx: int = 0,
    verbose: bool = True,
) -> tuple[str, int]:
    """
    Führt eine Anfrage durch den Rotary durch.
    Gibt (Antwort, nächster_provider_idx) zurück.
    Den nächsten Index beim nächsten Aufruf als start_provider_idx übergeben
    für gleichmäßige Round-Robin-Verteilung.
    """
    history = _load_history(thread_id, limit=6)
    messages = history + [{"role": "user", "content": user_message}]

    response, used_idx = ask(messages, start_idx=start_provider_idx, verbose=verbose)
    _save_exchange(thread_id, user_message, response, PROVIDERS[used_idx]["name"])

    next_idx = (used_idx + 1) % len(PROVIDERS)
    return response, next_idx


# ── OpenClaw Entry Point ───────────────────────────────────────────────────────

_oclaw_idx: int = 0  # Globaler Rotation-State für OpenClaw-Aufrufe


def handle_message(payload: dict) -> str:
    """
    OpenClaw Pi agent runtime entry point.
    Gleiche Signatur wie agent.py und agent_mini.py.
    payload: {text, thread_id, channel, thinking_level}
    """
    global _oclaw_idx
    response, _oclaw_idx = run_agent(
        user_message=payload.get("text", ""),
        thread_id=payload.get("thread_id", "default"),
        start_provider_idx=_oclaw_idx,
        verbose=False,
    )
    return response


# ── CLI REPL ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    thread_id = "cli-" + datetime.now().strftime("%Y%m%d")
    provider_idx = 0

    # Verfügbare Provider ermitteln
    available = [p for p in PROVIDERS if os.environ.get(p["key_env"])]

    print("┌──────────────────────────────────────────────────┐")
    print("│   Multi-Provider Agent — Free-Tier Infinite Rotary│")
    print("├──────────────────────────────────────────────────┤")
    if available:
        for p in available:
            line = f"  ✓ {p['name']}"
            print(f"│ {line:<50}│")
    else:
        print("│  ⚠ Keine Keys gesetzt — alle Provider werden      │")
        print("│    getestet bis einer antwortet                   │")
    print("├──────────────────────────────────────────────────┤")
    print(f"│  Keys: GROQ / OPENROUTER / GEMINI / MISTRAL_API_KEY │")
    print(f"│  Memory: {str(_DB_PATH)[-42:]:<42}│")
    print("│  'exit' zum Beenden                               │")
    print("└──────────────────────────────────────────────────┘")
    print()

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTschüss!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "/exit"):
            print("Tschüss!")
            break

        print()
        try:
            response, provider_idx = run_agent(
                user_message=user_input,
                thread_id=thread_id,
                start_provider_idx=provider_idx,
            )
            print(f"Agent: {response}")
        except RuntimeError as e:
            print(f"[FEHLER] {e}")
            print()
            print("Keys setzen (min. einen):")
            print("  export GROQ_API_KEY=gsk_...")
            print("  export OPENROUTER_API_KEY=sk-or-...")
            print("  export GEMINI_API_KEY=AIza...")
            print("  export MISTRAL_API_KEY=...")
        print()
