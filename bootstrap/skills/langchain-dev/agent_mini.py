"""
agent_mini.py — a-Shell Native Agent
=====================================
Vollständiger OpenClaw-kompatibler Agent NUR mit:
  - anthropic SDK (pure Python, kein Rust)
  - sqlite3 (Python builtin)
  - subprocess, os, json (builtins)

Kein LangChain, kein LangGraph, kein Pydantic v2.
Läuft auf a-Shell (iOS), Termux (Android), jedem Python 3.11+.

Kompatibel mit handle_message(payload) Interface von agent.py.
OpenClaw ruft handle_message auf — gleiche Signatur.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────────

MODEL      = "claude-sonnet-4-6"
MODEL_FAST = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 8

# Storage in ~/Documents/ (only writable location on a-Shell)
_DOCS = Path.home() / "Documents"
DATA_DIR  = _DOCS / ".langchain-assistant" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "memory.db"

SYSTEM_PROMPT = """You are a highly capable AI assistant for LangChain development and general tasks.
You run on a-Shell (iOS) via OpenClaw. You have tools for code execution, file I/O, and shell commands.

## Capabilities
- LangChain, LangGraph, Python, TypeScript — deep expertise
- Persistent memory across sessions
- Tool use: run_python, read_file, write_file, shell_safe

## Rules
- Be direct — no preamble
- Code-first for technical questions
- Never run destructive commands without confirmation
- Short answers for voice/Siri, detailed for WebChat
""".strip()


# ── SQLite Memory ──────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exchanges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id   TEXT NOT NULL,
            human       TEXT NOT NULL,
            assistant   TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thread ON exchanges(thread_id, id DESC)")
    conn.commit()
    return conn


def load_history(thread_id: str, limit: int = 8) -> list[dict]:
    """Lädt letzte N Austausche als Messages-Liste."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT human, assistant FROM exchanges WHERE thread_id=? ORDER BY id DESC LIMIT ?",
            (thread_id, limit)
        ).fetchall()
    messages = []
    for human, assistant in reversed(rows):
        messages.append({"role": "user",      "content": human})
        messages.append({"role": "assistant", "content": assistant})
    return messages


def save_exchange(thread_id: str, human: str, assistant: str):
    with _db() as conn:
        conn.execute(
            "INSERT INTO exchanges (thread_id, human, assistant) VALUES (?, ?, ?)",
            (thread_id, human[:2000], assistant[:4000])
        )
        conn.commit()
    # Alte Einträge beschneiden (max 200 pro Thread)
    with _db() as conn:
        conn.execute(
            """DELETE FROM exchanges WHERE thread_id=? AND id NOT IN
               (SELECT id FROM exchanges WHERE thread_id=? ORDER BY id DESC LIMIT 200)""",
            (thread_id, thread_id)
        )
        conn.commit()


# ── Tool Definitions ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "run_python",
        "description": "Execute Python code in subprocess. Returns stdout/stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "read_file",
        "description": "Read a text file. Path relative to ~/Documents/",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to ~/Documents/"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Path relative to ~/Documents/",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "File path relative to ~/Documents/"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "shell_safe",
        "description": "Run a safe read-only shell command (ls, pwd, git log, pip list, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"]
        }
    },
]


# ── Tool Execution ─────────────────────────────────────────────────────────────

_BLOCKED_CODE = [
    "__import__", "importlib.import_module", "exec(", "eval(",
    "compile(", "ctypes", "os.system(", "os.popen(",
    "os.execv", "os.fork", "socket", "urllib.request",
    "requests.get", "requests.post",
]

_SAFE_SHELL_PREFIXES = [
    "ls", "pwd", "echo", "cat", "head", "tail", "wc",
    "python3 --version", "node --version", "npm --version",
    "pip list", "pip show", "git log", "git status", "git diff",
    "lg2 log", "lg2 status",
]


def _run_python(code: str) -> str:
    cl = code.lower()
    for pat in _BLOCKED_CODE:
        if pat in cl:
            return f"[BLOCKED] '{pat}' not allowed in sandbox."
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=15
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        if err:
            return f"stdout:\n{out}\nstderr:\n{err}" if out else f"Error:\n{err}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] 15s exceeded"
    except Exception as e:
        return f"[ERROR] {e}"


def _read_file(path: str) -> str:
    full = _DOCS / path.lstrip("/")
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
        if len(content) > 8000:
            return content[:8000] + f"\n[truncated, {len(content)} total chars]"
        return content
    except FileNotFoundError:
        return f"[NOT FOUND] {full}"
    except Exception as e:
        return f"[ERROR] {e}"


def _write_file(path: str, content: str) -> str:
    full = _DOCS / path.lstrip("/")
    full.parent.mkdir(parents=True, exist_ok=True)
    try:
        full.write_text(content, encoding="utf-8")
        return f"[OK] Written {len(content)} chars to {full}"
    except Exception as e:
        return f"[ERROR] {e}"


def _shell_safe(command: str) -> str:
    cmd = command.strip()
    if not any(cmd.startswith(p) for p in _SAFE_SHELL_PREFIXES):
        return f"[BLOCKED] Not in allowlist. Allowed: {', '.join(_SAFE_SHELL_PREFIXES)}"
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return (r.stdout + r.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_tool(name: str, inputs: dict) -> str:
    if name == "run_python":  return _run_python(inputs.get("code", ""))
    if name == "read_file":   return _read_file(inputs.get("path", ""))
    if name == "write_file":  return _write_file(inputs.get("path", ""), inputs.get("content", ""))
    if name == "shell_safe":  return _shell_safe(inputs.get("command", ""))
    return f"[ERROR] Unknown tool: {name}"


# ── Agentic Loop ───────────────────────────────────────────────────────────────

def run_agent(
    user_message: str,
    thread_id: str = "default",
    channel: str = "webchat",
    thinking_level: str = "medium",
    chat_mode: str = "chat",
) -> str:
    """
    Vollständiger Agentic Loop mit Tool-Use.
    Ruft Claude Sonnet 4.6 auf, führt Tools aus, gibt finale Antwort zurück.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return (
            "[FEHLER] ANTHROPIC_API_KEY nicht gesetzt.\n"
            "Führe aus: export ANTHROPIC_API_KEY=sk-ant-DEIN_KEY"
        )

    try:
        from anthropic import Anthropic
    except ImportError:
        return (
            "[FEHLER] anthropic nicht installiert.\n"
            "Führe aus: pip install anthropic --prefer-binary"
        )

    client = Anthropic(api_key=api_key)

    # System-Prompt je nach Channel anpassen
    system = SYSTEM_PROMPT
    if channel in ("siri", "voice"):
        system += "\n\nKanal: Voice. Kurze, gesprochene Antworten. Kein Markdown."
    elif channel in ("telegram", "signal"):
        system += "\n\nKanal: Messaging. Kompakt, kein Markdown außer - Bullets."

    # Memory aus SQLite laden
    history = load_history(thread_id, limit=6)
    messages = history + [{"role": "user", "content": user_message}]

    # Agentic Loop
    for _round in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Antwort in Messages-Liste einfügen
        messages.append({"role": "assistant", "content": response.content})

        # Kein Tool-Call → fertig
        if response.stop_reason != "tool_use":
            break

        # Tool-Calls ausführen
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "user", "content": tool_results})

    # Finale Text-Antwort extrahieren
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    if not final_text:
        final_text = "(Keine Textantwort)"

    # In Memory speichern
    save_exchange(thread_id, user_message, final_text)

    return final_text


# ── OpenClaw Entry Point (gleiche Signatur wie agent.py) ──────────────────────

def handle_message(payload: dict) -> str:
    """
    OpenClaw Pi agent runtime entry point.
    payload: {text, thread_id, channel, thinking_level}
    """
    return run_agent(
        user_message   = payload.get("text", ""),
        thread_id      = payload.get("thread_id", "default"),
        channel        = payload.get("channel", "webchat"),
        thinking_level = payload.get("thinking_level", "medium"),
        chat_mode      = payload.get("chat_mode", "chat"),
    )


# ── CLI REPL (für direkte Tests in a-Shell) ────────────────────────────────────

if __name__ == "__main__":
    import readline  # type: ignore  # up-arrow history

    thread_id = "cli-" + datetime.now().strftime("%Y%m%d")
    print(f"LangChain Mini Agent (a-Shell native)")
    print(f"Modell: {MODEL} | Thread: {thread_id}")
    print(f"Memory: {DB_PATH}")
    print("Ctrl+C oder 'exit' zum Beenden\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bye.")
            break

        print("Agent: ", end="", flush=True)
        response = run_agent(user_input, thread_id=thread_id)
        print(response)
        print()
