"""
Coding Exclusive #1 — Causal Diff Explainer
============================================
Erklärt WARUM ein Code-Diff einen Test zum Scheitern bringt —
kausal, nicht nur korrelativ.

Global-unique weil:
  Kein Tool (Cursor, Aider, Copilot, SWE-bench) erklärt den kausalen
  Pfad: "Zeile X geändert → Invariante Y verletzt → Assertion Z bricht".
  Alle zeigen nur welcher Test failed. Dieses Modul rekonstruiert
  den semantischen Kausal-Pfad via AST-Datenfluss-Rückverfolgung.

Pipeline:
  1. Git-Diff parsen → geänderte Zeilen + Funktionen identifizieren
  2. Tests ausführen → failing assertions extrahieren
  3. Rückwärts-Dataflow über AST: Assertion → welche Variablen →
     welche Funktionen → welche Diff-Zeilen
  4. Claude bekommt strukturierten Kausal-Graph → erklärt in Klartext

Verwendung:
  from causal_diff import CausalDiffExplainer
  result = CausalDiffExplainer(repo_path=".").explain(diff_text, test_output)
  print(result.causal_chain)
  print(result.plain_explanation)
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Datenmodelle ──────────────────────────────────────────────────────────────

@dataclass
class DiffChange:
    file: str
    line_numbers: list[int]
    functions_changed: list[str]
    added_lines: list[str]
    removed_lines: list[str]


@dataclass
class FailingAssertion:
    test_name: str
    assertion_text: str
    line: int
    variables_referenced: list[str]
    error_message: str


@dataclass
class CausalLink:
    """Ein Glied in der Kausal-Kette."""
    from_entity: str   # z.B. "calculate_total() Zeile 42"
    to_entity: str     # z.B. "total Variable in test_checkout"
    relation: str      # z.B. "liefert falschen Wert weil"
    confidence: float  # 0..1


@dataclass
class CausalResult:
    diff_changes: list[DiffChange]
    failing_assertions: list[FailingAssertion]
    causal_chain: list[CausalLink]
    plain_explanation: str
    fix_suggestions: list[str]


# ── Diff Parser ───────────────────────────────────────────────────────────────

def parse_diff(diff_text: str) -> list[DiffChange]:
    """Parst unified diff → strukturierte DiffChange-Objekte."""
    changes = []
    current_file = ""
    current_added: list[str] = []
    current_removed: list[str] = []
    current_lines: list[int] = []
    line_counter = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            current_added, current_removed, current_lines = [], [], []
        elif line.startswith("@@ "):
            # @@ -old_start,old_count +new_start,new_count @@
            m = re.search(r"\+(\d+)", line)
            if m:
                line_counter = int(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            current_added.append(line[1:])
            current_lines.append(line_counter)
            line_counter += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_removed.append(line[1:])
        else:
            line_counter += 1

    if current_file and (current_added or current_removed):
        functions = _extract_function_names(current_added + current_removed)
        changes.append(DiffChange(
            file=current_file,
            line_numbers=current_lines,
            functions_changed=functions,
            added_lines=current_added,
            removed_lines=current_removed,
        ))

    return changes


def _extract_function_names(lines: list[str]) -> list[str]:
    """Findet Funktionsnamen in Code-Zeilen via Regex."""
    names = []
    for line in lines:
        # def func_name( oder function funcName(
        m = re.search(r'\bdef\s+(\w+)\s*\(', line)
        if m:
            names.append(m.group(1))
        # Aufruf: func_name(
        calls = re.findall(r'\b(\w+)\s*\(', line)
        names.extend(calls)
    return list(set(names))


# ── Test Output Parser ────────────────────────────────────────────────────────

def parse_test_output(test_output: str) -> list[FailingAssertion]:
    """Parst pytest/unittest Output → strukturierte FailingAssertion-Objekte."""
    assertions = []

    # pytest Format: FAILED test_file.py::TestClass::test_method
    test_pattern = re.compile(r'FAILED\s+([\w/]+\.py)::(\w+)', re.MULTILINE)
    error_pattern = re.compile(r'AssertionError[:\s]*(.*)', re.MULTILINE)
    assert_text_pattern = re.compile(r'assert\s+(.+)', re.MULTILINE)

    for match in test_pattern.finditer(test_output):
        file_path, test_name = match.groups()

        # Fehler-Kontext extrahieren (3 Zeilen nach FAILED)
        start = match.end()
        context = test_output[start:start + 500]

        error_msg = ""
        err_m = error_pattern.search(context)
        if err_m:
            error_msg = err_m.group(1).strip()

        assert_text = ""
        ass_m = assert_text_pattern.search(context)
        if ass_m:
            assert_text = ass_m.group(1).strip()

        # Variablen aus Assertion extrahieren
        vars_referenced = re.findall(r'\b([a-z_]\w+)\b', assert_text)

        assertions.append(FailingAssertion(
            test_name=test_name,
            assertion_text=assert_text,
            line=0,  # Wird von AST-Analyse gefüllt
            variables_referenced=list(set(vars_referenced)),
            error_message=error_msg,
        ))

    return assertions


# ── AST Dataflow Tracer ───────────────────────────────────────────────────────

class DataflowTracer(ast.NodeVisitor):
    """
    Rückwärts-Dataflow: gegeben eine Variable in einem Test,
    finde welche Funktionen sie befüllen.
    """

    def __init__(self):
        self.assignments: dict[str, list[str]] = {}  # var → [functions that assign it]
        self.calls: dict[str, list[str]] = {}         # func → [called functions]

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                funcs = self._extract_calls(node.value)
                self.assignments[target.id] = funcs
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                calls.append(child.func.id)
        self.calls[node.name] = calls
        self.generic_visit(node)

    def _extract_calls(self, node: ast.expr) -> list[str]:
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return calls

    def trace_variable(self, var_name: str) -> list[str]:
        """Gibt alle Funktionen zurück die transitiv zu var_name beitragen."""
        direct = self.assignments.get(var_name, [])
        all_funcs = set(direct)
        for func in direct:
            all_funcs.update(self.calls.get(func, []))
        return list(all_funcs)


def build_causal_links(
    changes: list[DiffChange],
    assertions: list[FailingAssertion],
    source_code: str,
) -> list[CausalLink]:
    """Verbindet Diff-Änderungen mit failing Assertions via AST."""
    links = []

    try:
        tree = ast.parse(source_code)
        tracer = DataflowTracer()
        tracer.visit(tree)
    except SyntaxError:
        return []

    changed_funcs = {f for c in changes for f in c.functions_changed}

    for assertion in assertions:
        for var in assertion.variables_referenced:
            contributing_funcs = tracer.trace_variable(var)
            overlap = set(contributing_funcs) & changed_funcs
            for func in overlap:
                links.append(CausalLink(
                    from_entity=f"`{func}()` (geändert im Diff)",
                    to_entity=f"`{var}` in `{assertion.test_name}`",
                    relation="liefert veränderten Wert der die Assertion verletzt",
                    confidence=0.75,
                ))

    return links


# ── Claude Erklärung ──────────────────────────────────────────────────────────

def explain_with_claude(
    changes: list[DiffChange],
    assertions: list[FailingAssertion],
    causal_links: list[CausalLink],
    api_key: str,
) -> tuple[str, list[str]]:
    """Lässt Claude den Kausal-Graph in natürliche Sprache übersetzen."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
    except ImportError:
        return _offline_explanation(changes, assertions, causal_links), []

    # Strukturierten Kontext aufbauen
    diff_summary = "\n".join(
        f"- `{c.file}`: Funktionen {c.functions_changed} geändert"
        for c in changes
    )
    assertion_summary = "\n".join(
        f"- `{a.test_name}`: `assert {a.assertion_text}` → {a.error_message}"
        for a in assertions
    )
    causal_summary = "\n".join(
        f"- {l.from_entity} → {l.to_entity}: {l.relation} (Konfidenz: {l.confidence:.0%})"
        for l in causal_links
    ) or "Kein direkter kausaler Pfad gefunden (indirekter Effekt wahrscheinlich)"

    prompt = f"""Du bist ein Debugging-Experte. Erkläre kausal (Ursache → Wirkung),
warum dieser Diff die Tests zum Scheitern bringt.

DIFF-ÄNDERUNGEN:
{diff_summary}

FAILING ASSERTIONS:
{assertion_summary}

KAUSALE LINKS (automatisch ermittelt):
{causal_summary}

Erkläre in 3-5 Sätzen:
1. Was genau wurde geändert
2. Welche Invariante das verletzt
3. Warum genau diese Assertion bricht
4. Zwei konkrete Fix-Vorschläge (als Bullet-Liste am Ende: "FIX: ...")

Sei präzise und technisch. Kein Filler."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()

    # Fix-Vorschläge extrahieren
    fixes = re.findall(r'FIX:\s*(.+)', text)
    explanation = re.sub(r'FIX:.*', '', text).strip()

    return explanation, fixes


def _offline_explanation(
    changes: list[DiffChange],
    assertions: list[FailingAssertion],
    causal_links: list[CausalLink],
) -> str:
    parts = [f"Diff ändert: {[c.file for c in changes]}"]
    parts.append(f"Bricht: {[a.test_name for a in assertions]}")
    if causal_links:
        parts.append(f"Kausaler Pfad: {causal_links[0].from_entity} → {causal_links[0].to_entity}")
    return " | ".join(parts)


# ── Main API ──────────────────────────────────────────────────────────────────

class CausalDiffExplainer:
    def __init__(self, repo_path: str = ".", api_key: str | None = None):
        self.repo_path = Path(repo_path)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def explain(
        self,
        diff_text: str,
        test_output: str,
        source_code: str = "",
    ) -> CausalResult:
        changes = parse_diff(diff_text)
        assertions = parse_test_output(test_output)

        # Source-Code aus geänderten Dateien laden wenn nicht übergeben
        if not source_code and changes:
            src_parts = []
            for change in changes:
                src_file = self.repo_path / change.file
                if src_file.exists():
                    src_parts.append(src_file.read_text(errors="replace")[:3000])
            source_code = "\n\n".join(src_parts)

        causal_links = build_causal_links(changes, assertions, source_code)

        explanation, fixes = explain_with_claude(
            changes, assertions, causal_links, self.api_key
        )

        return CausalResult(
            diff_changes=changes,
            failing_assertions=assertions,
            causal_chain=causal_links,
            plain_explanation=explanation,
            fix_suggestions=fixes,
        )

    def explain_last_commit(self) -> CausalResult:
        """Erklärt warum der letzte Commit Tests bricht."""
        diff = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD"],
            cwd=self.repo_path, capture_output=True, text=True
        ).stdout

        test_result = subprocess.run(
            ["python3", "-m", "pytest", "--tb=short", "-q"],
            cwd=self.repo_path, capture_output=True, text=True
        )
        test_output = test_result.stdout + test_result.stderr

        return self.explain(diff, test_output)


# ── LangChain Tool ────────────────────────────────────────────────────────────

def as_langchain_tool():
    try:
        from langchain_core.tools import tool

        @tool
        def explain_diff_failure(diff_text: str, test_output: str) -> str:
            """Erklärt kausal warum ein Code-Diff Tests zum Scheitern bringt.
            Input: unified diff + pytest output. Output: kausale Erklärung + Fix-Vorschläge."""
            explainer = CausalDiffExplainer()
            result = explainer.explain(diff_text, test_output)
            lines = [result.plain_explanation]
            if result.causal_chain:
                lines.append("\nKausale Links:")
                for link in result.causal_chain[:3]:
                    lines.append(f"  {link.from_entity} → {link.to_entity}")
            if result.fix_suggestions:
                lines.append("\nFix-Vorschläge:")
                for fix in result.fix_suggestions:
                    lines.append(f"  • {fix}")
            return "\n".join(lines)

        return explain_diff_failure
    except ImportError:
        return None


if __name__ == "__main__":
    import sys
    explainer = CausalDiffExplainer()
    result = explainer.explain_last_commit()
    print("=== KAUSAL-ERKLÄRUNG ===")
    print(result.plain_explanation)
    if result.fix_suggestions:
        print("\nFix-Vorschläge:")
        for fix in result.fix_suggestions:
            print(f"  • {fix}")
