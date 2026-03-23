"""
LangChain-Dev OpenClaw Skill — Agent Entrypoint
================================================
Stateful LangGraph agent with persistent SQLite memory,
Claude claude-sonnet-4-6 reasoning, and tool use.

Invoked by OpenClaw's Pi agent runtime.
"""

from __future__ import annotations

import os
import sys
import json
import subprocess
import textwrap
from typing import Annotated, TypedDict

from anthropic import Anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memory import ConversationMemory

# ── Configuration ─────────────────────────────────────────────────────────────

MODEL_FAST = "claude-haiku-4-5-20251001"      # Haiku 4.5 — quick responses
MODEL_SMART = "claude-sonnet-4-6"             # Sonnet 4.6 — complex reasoning
MODEL_POWER = "claude-opus-4-6"               # Opus 4.6 — deep analysis

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SKILL_DIR, "..", "..", "data", "memory.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SYSTEM_PROMPT = """
You are a highly specialized AI assistant for LangChain development and general tasks.
You run as an OpenClaw skill with access to tools, persistent memory, and deep LangChain expertise.

## Your Capabilities
- LangChain, LangGraph, LangSmith, DeepAgents — deep expertise
- Python and TypeScript code generation, debugging, explanation
- Persistent memory across sessions (SQLite-backed)
- Tool use: web search, code execution, file I/O

## Behavior Rules
- Be direct — no preamble or filler
- Code-first for technical questions
- Never execute destructive commands without explicit confirmation
- Adapt response length to channel (short for voice/SMS, detailed for WebChat)
- Reference earlier conversations when relevant

## LangChain Conventions
- Prefer LangGraph over legacy AgentExecutor
- Use LCEL (| operator) for chains
- Recommend LangSmith for production observability
- Use langchain-anthropic for Claude integration
""".strip()


# ── Tool definitions ───────────────────────────────────────────────────────────

@tool
def run_python(code: str) -> str:
    """Execute Python code in an isolated subprocess and return stdout/stderr.
    Use for calculations, data processing, testing LangChain snippets."""
    # Safety: block obviously dangerous patterns
    blocked = ["import os", "import subprocess", "import sys", "__import__",
               "open(", "exec(", "eval(", "shutil", "pathlib"]
    code_lower = code.lower()
    for pattern in blocked:
        if pattern in code_lower:
            return f"[BLOCKED] Pattern '{pattern}' not allowed in sandboxed execution."

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=15
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"stdout:\n{out}\nstderr:\n{err}" if out else f"Error:\n{err}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Execution exceeded 15 seconds"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def read_file(path: str) -> str:
    """Read a text file from the filesystem. Path must be relative to home dir."""
    full_path = os.path.join(os.path.expanduser("~"), path.lstrip("/"))
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 8000:
            return content[:8000] + f"\n\n[... truncated, {len(content)} total chars]"
        return content
    except FileNotFoundError:
        return f"[NOT FOUND] {full_path}"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file. Path must be relative to home dir."""
    full_path = os.path.join(os.path.expanduser("~"), path.lstrip("/"))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[OK] Written {len(content)} chars to {full_path}"
    except Exception as e:
        return f"[ERROR] {e}"


@tool
def shell_safe(command: str) -> str:
    """Run an allowlisted shell command. Only safe, read-only commands permitted."""
    # Strict allowlist — only informational commands
    allowed_prefixes = [
        "ls", "pwd", "echo", "cat", "head", "tail", "wc",
        "python3 --version", "node --version", "npm --version",
        "openclaw --version", "openclaw doctor",
        "pip list", "pip show", "git log", "git status", "git diff",
    ]
    cmd_stripped = command.strip()
    allowed = any(cmd_stripped.startswith(p) for p in allowed_prefixes)
    if not allowed:
        return (f"[BLOCKED] Command not in allowlist.\n"
                f"Allowed: {', '.join(allowed_prefixes)}")
    try:
        result = subprocess.run(
            cmd_stripped, shell=True, capture_output=True,
            text=True, timeout=10
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"


# ── a-Shell Exclusive Tools (graceful degradation auf Nicht-iOS) ──────────────

def _load_ashell_tools() -> list:
    """
    Lädt a-Shell-exklusive Tools wenn verfügbar.
    Kein Fehler auf macOS/Linux — einfach leer.
    """
    extra = []
    ashell_dir = os.path.join(os.path.dirname(SKILL_DIR), "ashell")
    if not os.path.isdir(ashell_dir):
        return extra
    if ashell_dir not in sys.path:
        sys.path.insert(0, ashell_dir)

    # TTS: speak_aloud Tool
    try:
        from tts import as_langchain_tool  # noqa: PLC0415
        tts_tool = as_langchain_tool()
        if tts_tool:
            extra.append(tts_tool)
    except Exception:
        pass

    # URL-Orchestrator: Drafts, Things, Shortcuts
    try:
        from url_orchestrator import as_langchain_tools  # noqa: PLC0415
        extra.extend(as_langchain_tools())
    except Exception:
        pass

    return extra


TOOLS = [run_python, read_file, write_file, shell_safe] + _load_ashell_tools()


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    channel: str          # openclaw channel name (webchat, telegram, siri, ...)
    thread_id: str        # session/conversation ID
    thinking_level: str   # off | low | medium | high


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def build_graph(memory: ConversationMemory) -> object:
    llm = ChatAnthropic(
        model=MODEL_SMART,
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=4096,
    ).bind_tools(TOOLS)

    def agent_node(state: AgentState):
        """Main reasoning node — calls Claude with tool binding."""
        system = SYSTEM_PROMPT

        # Inject relevant memory context
        # ACMM: Semantic search wenn query bekannt (besser als chronologisch)
        last_human = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            ""
        )
        ctx = memory.get_context(
            state["thread_id"],
            limit=5,
            query=str(last_human)[:500],  # Semantische Suche nach aktuellem Query
        )
        if ctx:
            system += f"\n\n{ctx}"

        # Adapt style per channel
        channel = state.get("channel", "webchat")
        if channel in ("siri", "voice"):
            system += "\n\nIMPORTANT: Respond in natural spoken language. No markdown, no code blocks. Short sentences."
        elif channel in ("telegram", "signal", "whatsapp"):
            system += "\n\nIMPORTANT: Keep responses concise. Use plain text. Bullet points with '-' only."

        msgs = [SystemMessage(content=system)] + state["messages"]
        response = llm.invoke(msgs)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """Route: call tools or end."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    def save_memory_node(state: AgentState):
        """Persist conversation summary to SQLite after each exchange."""
        msgs = state["messages"]
        if len(msgs) >= 2:
            last_human = next(
                (m.content for m in reversed(msgs) if isinstance(m, HumanMessage)), ""
            )
            last_ai = next(
                (m.content for m in reversed(msgs) if isinstance(m, AIMessage)), ""
            )
            if last_human and last_ai:
                memory.save_exchange(
                    thread_id=state["thread_id"],
                    human=last_human,
                    assistant=str(last_ai)[:500],
                )

        # iCloud Handoff — nach jeder Antwort State synchronisieren (a-Shell only)
        _try_icloud_handoff(state)
        return {}

    def _try_icloud_handoff(state: AgentState):
        """Schreibt Session-State nach iCloud für Cross-Device-Handoff."""
        ashell_dir = os.path.join(os.path.dirname(SKILL_DIR), "ashell")
        if not os.path.isdir(ashell_dir):
            return
        try:
            if ashell_dir not in sys.path:
                sys.path.insert(0, ashell_dir)
            from icloud_handoff import iCloudHandoff  # noqa: PLC0415
            h = iCloudHandoff()
            last_human = next(
                (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
            )
            h.save(
                thread_id=state["thread_id"],
                summary=str(last_human)[:200],
            )
        except Exception:
            pass  # iCloud nicht verfügbar — kein Problem

    # Build the graph
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("save_memory", save_memory_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: "save_memory"})
    graph.add_edge("tools", "agent")
    graph.add_edge("save_memory", END)

    return graph


# ── OpenClaw Entry Point ──────────────────────────────────────────────────────

def handle_message(payload: dict) -> str:
    """
    Called by OpenClaw Pi agent runtime.
    payload: {
        "text": str,
        "thread_id": str,
        "channel": str,
        "thinking_level": str
    }
    Returns: response string
    """
    memory = ConversationMemory(DB_PATH)

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        graph = build_graph(memory).compile(checkpointer=checkpointer)

        state = {
            "messages": [HumanMessage(content=payload["text"])],
            "channel": payload.get("channel", "webchat"),
            "thread_id": payload.get("thread_id", "default"),
            "thinking_level": payload.get("thinking_level", "medium"),
        }

        config = {"configurable": {"thread_id": payload.get("thread_id", "default")}}
        result = graph.invoke(state, config=config)

        # Extract final AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                return str(msg.content)

    return "I couldn't generate a response. Please try again."


# ── CLI Mode (for testing outside OpenClaw) ───────────────────────────────────

if __name__ == "__main__":
    import readline  # noqa: F401 — enables up-arrow history in REPL

    print("LangChain-Dev Assistant — Local REPL Mode")
    print("Type 'exit' or Ctrl+D to quit\n")

    thread_id = "cli-session"
    channel = "webchat"

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "/exit"):
            print("Bye!")
            break

        payload = {
            "text": user_input,
            "thread_id": thread_id,
            "channel": channel,
            "thinking_level": "medium",
        }
        response = handle_message(payload)
        print(f"\nAssistant: {response}\n")
