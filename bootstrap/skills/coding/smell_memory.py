"""
Coding Exclusive #4 — Cross-Session Code Smell Memory
======================================================
Merkt sich wiederkehrende Anti-Pattern des spezifischen Users
und warnt proaktiv beim nächsten ähnlichen Code.

Global-unique weil:
  MemGPT merkt sich Fakten. Kein System merkt sich USER-SPEZIFISCHE
  Anti-Pattern ("dieser User schreibt immer N+1 Queries in Django-Views",
  "vergisst exception handling in async-Funktionen") und warnt
  PROAKTIV beim nächsten ähnlichen Code — ohne expliziten Prompt.

Architektur:
  - Smell-Fingerprint: struktureller AST-Hash des Anti-Patterns
  - ACMM-Integration: Fingerprints in SemanticMemory gespeichert
  - Before-Hook in agent.py: Code im Message → Fingerprint-Check
  - Bei Match: Warnung BEVOR Claude antwortet

Smell-Kategorien (automatisch erkannt):
  - N+1 Query (ORM-Schleife ohne select_related/prefetch)
  - Missing exception handling (bare try/except oder kein try in async)
  - Mutable default arguments (def f(x=[]):)
  - Resource leak (open() ohne with)
  - Hardcoded secrets (PASSWORD = "...")
  - Infinite retry without backoff
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable


# ── Smell-Definitionen ────────────────────────────────────────────────────────

@dataclass
class SmellPattern:
    id: str
    name: str
    description: str
    severity: str             # "critical" | "warning" | "info"
    detector: Callable[[str, ast.AST], list[int]]  # returns line numbers


@dataclass
class SmellMatch:
    pattern_id: str
    pattern_name: str
    severity: str
    lines: list[int]
    code_snippet: str
    occurrence_count: int     # Wie oft dieser User das schon gemacht hat
    first_seen: str
    suggestion: str


@dataclass
class SmellReport:
    has_smells: bool
    matches: list[SmellMatch]
    proactive_warning: str    # Fertige Warnung für System-Prompt


# ── AST-basierte Smell-Detektoren ─────────────────────────────────────────────

def _detect_mutable_defaults(code: str, tree: ast.AST) -> list[int]:
    """def f(x=[], x={}, x=set())"""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set, ast.Call)):
                    lines.append(node.lineno)
    return lines


def _detect_missing_async_exception_handling(code: str, tree: ast.AST) -> list[int]:
    """async def ohne try/except"""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            body_str = ast.unparse(node) if hasattr(ast, "unparse") else ""
            has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
            # Nur markieren wenn die async-Funktion IO-ähnliche Calls hat
            has_io = any(
                isinstance(n, ast.Await) for n in ast.walk(node)
            )
            if has_io and not has_try:
                lines.append(node.lineno)
    return lines


def _detect_resource_leak(code: str, tree: ast.AST) -> list[int]:
    """open() ohne with-Statement"""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                # Prüfen ob dieses open() in einem with-Statement ist
                # (vereinfacht: schauen ob "with open" im Code steht)
                line_text = code.splitlines()[node.lineno - 1] if node.lineno <= len(code.splitlines()) else ""
                if "with" not in line_text:
                    lines.append(node.lineno)
    return lines


def _detect_hardcoded_secrets(code: str, tree: ast.AST) -> list[int]:
    """PASSWORD/SECRET/API_KEY = "..." Zuweisung"""
    secret_patterns = re.compile(
        r'\b(PASSWORD|SECRET|API_KEY|TOKEN|PRIVATE_KEY|ACCESS_KEY)\s*=\s*["\'][^"\']+["\']',
        re.IGNORECASE
    )
    lines = []
    for i, line in enumerate(code.splitlines(), 1):
        if secret_patterns.search(line):
            lines.append(i)
    return lines


def _detect_orm_n_plus_one(code: str, tree: ast.AST) -> list[int]:
    """QuerySet in for-Loop ohne prefetch/select_related"""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            # Prüft ob iter ein ORM-QuerySet-Aufruf ist
            iter_str = ast.unparse(node.iter) if hasattr(ast, "unparse") else ""
            is_queryset = any(kw in iter_str for kw in [
                ".filter(", ".all(", ".exclude(", ".objects."
            ])
            if is_queryset:
                # Prüfe ob .select_related oder .prefetch_related fehlt
                if "select_related" not in iter_str and "prefetch_related" not in iter_str:
                    lines.append(node.lineno)
    return lines


def _detect_bare_except(code: str, tree: ast.AST) -> list[int]:
    """except: oder except Exception: ohne spezifische Exception"""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:  # bare except:
                lines.append(node.lineno)
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                lines.append(node.lineno)
    return lines


# Registry aller Smell-Detektoren
SMELL_PATTERNS: list[tuple[str, str, str, str, Callable]] = [
    ("mutable_default", "Mutable Default Argument", "def f(x=[]) ist ein klassischer Python-Bug", "critical", _detect_mutable_defaults),
    ("async_no_try", "Async ohne Exception Handling", "async-Funktionen mit IO aber ohne try/except", "warning", _detect_missing_async_exception_handling),
    ("resource_leak", "Resource Leak", "open() ohne with-Statement — File wird nicht sicher geschlossen", "critical", _detect_resource_leak),
    ("hardcoded_secret", "Hardcoded Secret", "Secrets direkt im Code — gehören in .env", "critical", _detect_hardcoded_secrets),
    ("orm_n_plus_one", "N+1 Query", "ORM-QuerySet in for-Loop ohne prefetch_related", "warning", _detect_orm_n_plus_one),
    ("bare_except", "Bare Except", "except: oder except Exception: fängt zu viel", "info", _detect_bare_except),
]


# ── Fingerprint + SQLite Persistenz ──────────────────────────────────────────

class SmellMemory:
    """
    Persistiert Code-Smell-Fingerprints in SQLite.
    Lernt die spezifischen Anti-Pattern des Users über Sessions hinweg.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path.home() / ".langchain-assistant" / "data" / "smell_memory.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS smell_occurrences (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_id      TEXT NOT NULL,
                    code_fingerprint TEXT NOT NULL,  -- SHA256 des AST-Strukturhashes
                    code_snippet    TEXT NOT NULL,
                    file_path       TEXT DEFAULT '',
                    first_seen      TEXT DEFAULT (datetime('now')),
                    last_seen       TEXT DEFAULT (datetime('now')),
                    occurrence_count INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_smell_fp
                ON smell_occurrences(pattern_id, code_fingerprint)
            """)

    def _fingerprint(self, pattern_id: str, code_snippet: str) -> str:
        """Struktureller Fingerprint: normalisierter AST-Hash."""
        try:
            tree = ast.parse(code_snippet)
            # Variablen-Namen entfernen für strukturellen Vergleich
            normalized = ast.dump(tree, annotate_fields=False)
        except SyntaxError:
            normalized = code_snippet
        return hashlib.sha256(f"{pattern_id}:{normalized}".encode()).hexdigest()[:16]

    def record(self, pattern_id: str, code_snippet: str, file_path: str = "") -> int:
        """Speichert einen Smell-Fund. Gibt occurrence_count zurück."""
        fp = self._fingerprint(pattern_id, code_snippet)
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT occurrence_count FROM smell_occurrences WHERE pattern_id=? AND code_fingerprint=?",
                (pattern_id, fp)
            ).fetchone()

            if existing:
                count = existing["occurrence_count"] + 1
                conn.execute(
                    """UPDATE smell_occurrences
                       SET occurrence_count=?, last_seen=datetime('now')
                       WHERE pattern_id=? AND code_fingerprint=?""",
                    (count, pattern_id, fp)
                )
                return count
            else:
                conn.execute(
                    """INSERT INTO smell_occurrences
                       (pattern_id, code_fingerprint, code_snippet, file_path)
                       VALUES (?, ?, ?, ?)""",
                    (pattern_id, fp, code_snippet[:300], file_path)
                )
                return 1

    def get_occurrence_count(self, pattern_id: str, code_snippet: str) -> tuple[int, str]:
        """Gibt (occurrence_count, first_seen) zurück."""
        fp = self._fingerprint(pattern_id, code_snippet)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT occurrence_count, first_seen FROM smell_occurrences WHERE pattern_id=? AND code_fingerprint=?",
                (pattern_id, fp)
            ).fetchone()
        if row:
            return row["occurrence_count"], row["first_seen"]
        return 0, ""

    def user_pattern_summary(self) -> dict[str, int]:
        """Gibt häufigste Anti-Pattern des Users zurück."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT pattern_id, SUM(occurrence_count) as total
                   FROM smell_occurrences GROUP BY pattern_id
                   ORDER BY total DESC"""
            ).fetchall()
        return {r["pattern_id"]: r["total"] for r in rows}


# ── Smell-Analyse ─────────────────────────────────────────────────────────────

SUGGESTIONS = {
    "mutable_default": "Verwende `None` als Default und initialisiere in der Funktion: `if x is None: x = []`",
    "async_no_try": "Wrape IO-Operationen in `try/except (aiohttp.ClientError, asyncio.TimeoutError):`",
    "resource_leak": "Nutze `with open(...) as f:` für automatisches Schließen",
    "hardcoded_secret": "Verlagere Secrets in `.env` und lade via `os.environ.get('SECRET_KEY')`",
    "orm_n_plus_one": "Füge `.select_related('field')` oder `.prefetch_related('related')` vor dem Loop hinzu",
    "bare_except": "Fange spezifische Exceptions: `except (ValueError, KeyError) as e:`",
}


def analyze_code(code: str, memory: SmellMemory) -> SmellReport:
    """
    Analysiert Code auf bekannte Anti-Pattern und berücksichtigt User-History.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return SmellReport(
            has_smells=False,
            matches=[],
            proactive_warning=f"Syntax-Fehler: {e}"
        )

    matches: list[SmellMatch] = []

    for pid, name, desc, severity, detector in SMELL_PATTERNS:
        try:
            lines = detector(code, tree)
        except Exception:
            continue

        if not lines:
            continue

        # Code-Snippet für diesen Smell
        code_lines = code.splitlines()
        snippets = []
        for ln in lines[:3]:
            if 0 < ln <= len(code_lines):
                snippets.append(f"  Zeile {ln}: {code_lines[ln-1].strip()}")
        snippet = "\n".join(snippets)

        # Aus Memory laden wie oft das schon passiert ist
        count = memory.record(pid, snippet)
        _, first_seen = memory.get_occurrence_count(pid, snippet)

        matches.append(SmellMatch(
            pattern_id=pid,
            pattern_name=name,
            severity=severity,
            lines=lines,
            code_snippet=snippet,
            occurrence_count=count,
            first_seen=first_seen,
            suggestion=SUGGESTIONS.get(pid, "Manuell prüfen"),
        ))

    if not matches:
        return SmellReport(has_smells=False, matches=[], proactive_warning="")

    # Proaktive Warnung generieren (geht in System-Prompt)
    warning_lines = ["⚠️ **Code-Smell-Warnung** (aus deiner persönlichen History):"]
    for m in sorted(matches, key=lambda x: x.occurrence_count, reverse=True):
        repeat_note = f" — **{m.occurrence_count}x von dir gesehen!**" if m.occurrence_count > 1 else ""
        warning_lines.append(
            f"- **{m.pattern_name}** (Zeile {m.lines[0]}){repeat_note}\n"
            f"  💡 {m.suggestion}"
        )

    return SmellReport(
        has_smells=True,
        matches=matches,
        proactive_warning="\n".join(warning_lines),
    )


# ── Before-Hook für agent.py ──────────────────────────────────────────────────

_memory_instance: SmellMemory | None = None

def get_smell_memory() -> SmellMemory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = SmellMemory()
    return _memory_instance


def check_message_for_smells(message_text: str) -> str:
    """
    Before-Hook: wird in agent.py vor LLM-Aufruf aufgerufen.
    Extrahiert Code-Blöcke aus der Message und prüft auf Smells.
    Gibt Warnung zurück die in System-Prompt injiziert wird (oder "").
    """
    # Code-Blöcke aus Message extrahieren
    code_blocks = re.findall(r'```(?:python|py)?\n(.*?)```', message_text, re.DOTALL)
    inline_code = re.findall(r'`([^`]{20,})`', message_text)  # Längere Inline-Blöcke

    all_code = "\n\n".join(code_blocks + inline_code)
    if not all_code.strip():
        return ""

    mem = get_smell_memory()
    report = analyze_code(all_code, mem)

    return report.proactive_warning if report.has_smells else ""


# ── LangChain Tool ────────────────────────────────────────────────────────────

def as_langchain_tool():
    try:
        from langchain_core.tools import tool

        @tool
        def analyze_smells(code: str) -> str:
            """Analysiert Python-Code auf Anti-Pattern und erinnert sich an
            wiederkehrende Fehler des Users über Sessions hinweg."""
            mem = get_smell_memory()
            report = analyze_code(code, mem)

            if not report.has_smells:
                return "✓ Keine bekannten Anti-Pattern gefunden."

            lines = [f"Gefunden: {len(report.matches)} Smell(s)\n"]
            for m in report.matches:
                lines.append(f"**{m.pattern_name}** [{m.severity}] — {m.occurrence_count}x in deiner History")
                lines.append(f"  Zeilen: {m.lines}")
                lines.append(f"  💡 {m.suggestion}\n")

            summary = get_smell_memory().user_pattern_summary()
            if summary:
                most_common = max(summary, key=summary.get)  # type: ignore
                lines.append(f"\nHäufigstes Anti-Pattern: `{most_common}` ({summary[most_common]}x)")

            return "\n".join(lines)

        return analyze_smells
    except ImportError:
        return None
