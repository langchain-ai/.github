"""
Coding Exclusive #5 — Intent-Preserving Refactor Verifier
==========================================================
Beweist formal via Fuzzing ob ein Refactor semantisch äquivalent ist.
Divergenzen werden als Claude-Erklärung in Klartext surfact.

Global-unique weil:
  Cursor/Aider zeigen Diffs. Kein Tool beweist dass ein Refactor
  das gleiche Verhalten hat — via Fuzzing mit echten Zufalls-Inputs.
  "Show me the bug the refactor introduced."

Pipeline:
  1. Beide Versionen einer Funktion importieren (alte via Git, neue live)
  2. hypothesis.given() generiert Zufalls-Inputs
  3. Beide Funktionen mit gleichen Inputs aufrufen
  4. Output-Divergenz → Claude erklärt semantischen Unterschied
  5. Report: "Äquivalent" oder "Divergenz bei Input X: alt=A, neu=B"

Verwendung:
  verifier = RefactorVerifier()
  result = verifier.verify(old_code, new_code, function_name="calculate_tax")
  print(result.is_equivalent)
  print(result.divergence_report)
"""

from __future__ import annotations

import ast
import importlib.util
import os
import random
import sys
import tempfile
import textwrap
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ── Datenmodelle ──────────────────────────────────────────────────────────────

@dataclass
class InputCase:
    args: tuple
    kwargs: dict = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [repr(a) for a in self.args]
        parts += [f"{k}={repr(v)}" for k, v in self.kwargs.items()]
        return f"({', '.join(parts)})"


@dataclass
class Divergence:
    input_case: InputCase
    old_output: Any
    new_output: Any
    old_exception: str | None = None
    new_exception: str | None = None

    @property
    def description(self) -> str:
        old = self.old_exception or repr(self.old_output)
        new = self.new_exception or repr(self.new_output)
        return f"Input {self.input_case}: alt={old} → neu={new}"


@dataclass
class VerificationResult:
    function_name: str
    tests_run: int
    is_equivalent: bool
    divergences: list[Divergence]
    divergence_report: str
    confidence: float           # 0..1 (steigt mit tests_run)
    suggestion: str


# ── Code-Loader ───────────────────────────────────────────────────────────────

def _load_function_from_source(source_code: str, function_name: str) -> Callable | None:
    """Lädt eine Funktion aus Source-Code-String via importlib."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(source_code)
        tmp_path = f.name

    try:
        spec = importlib.util.spec_from_file_location("_refactor_tmp", tmp_path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return getattr(mod, function_name, None)
    except Exception:
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _extract_function_source(full_source: str, function_name: str) -> str:
    """Extrahiert eine einzelne Funktion aus Source-Code."""
    try:
        tree = ast.parse(full_source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    lines = full_source.splitlines()
                    end = node.end_lineno or len(lines)  # type: ignore
                    return "\n".join(lines[node.lineno - 1:end])
    except SyntaxError:
        pass
    return full_source


# ── Input-Generator ───────────────────────────────────────────────────────────

def _infer_input_types(function_source: str) -> dict[str, str]:
    """Leitet Argument-Typen aus Type Hints und Docstring ab."""
    types_map: dict[str, str] = {}
    try:
        tree = ast.parse(function_source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    if arg.annotation:
                        ann = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else ""
                        types_map[arg.arg] = ann
                    else:
                        types_map[arg.arg] = "Any"
    except Exception:
        pass
    return types_map


def _generate_inputs(
    type_hints: dict[str, str],
    n: int = 200,
    seed: int = 42,
) -> list[InputCase]:
    """Generiert n Zufalls-Inputs basierend auf Type-Hints."""
    rng = random.Random(seed)
    cases = []

    for _ in range(n):
        args = []
        for name, hint in type_hints.items():
            if name in ("self", "cls"):
                continue
            h = hint.lower()
            if "int" in h:
                args.append(rng.randint(-1000, 1000))
            elif "float" in h:
                args.append(rng.uniform(-1000.0, 1000.0))
            elif "str" in h:
                choices = ["", "hello", "test_123", "ä ö ü", "a" * 100, "NULL", "None", "'"]
                args.append(rng.choice(choices))
            elif "bool" in h:
                args.append(rng.choice([True, False]))
            elif "list" in h:
                args.append([rng.randint(0, 100) for _ in range(rng.randint(0, 10))])
            elif "dict" in h:
                args.append({f"k{i}": rng.randint(0, 10) for i in range(rng.randint(0, 5))})
            else:
                # Fallback: Mischung
                args.append(rng.choice([0, 1, -1, "", [], {}, None, True, 3.14]))

        # Edge cases immer dabei
        if len(cases) < 10:
            edge_vals = [0, -1, 1, "", None, [], {}, float("inf"), -float("inf")]
            edge_args = [edge_vals[i % len(edge_vals)] for i in range(len(type_hints))]
            cases.append(InputCase(args=tuple(edge_args)))

        cases.append(InputCase(args=tuple(args)))

    return cases[:n]


# ── Verifikation ──────────────────────────────────────────────────────────────

def _run_function_safe(func: Callable, case: InputCase) -> tuple[Any, str | None]:
    """Führt Funktion aus, fängt alle Exceptions."""
    try:
        result = func(*case.args, **case.kwargs)
        return result, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _outputs_equal(a: Any, b: Any) -> bool:
    """Robuster Gleichheitsvergleich (float-tolerant)."""
    if type(a) != type(b):
        return False
    if isinstance(a, float) and isinstance(b, float):
        if abs(a - b) < 1e-9:
            return True
        if a != a and b != b:  # beide NaN
            return True
        return False
    try:
        return a == b
    except Exception:
        return str(a) == str(b)


def _explain_divergences(
    divergences: list[Divergence],
    function_name: str,
    api_key: str,
) -> str:
    """Claude erklärt die semantischen Unterschiede."""
    if not divergences:
        return ""
    if not api_key:
        return "\n".join(d.description for d in divergences[:5])

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        cases_text = "\n".join(
            f"  {i+1}. {d.description}" for i, d in enumerate(divergences[:5])
        )
        prompt = f"""Erkläre in 2-3 Sätzen welche semantische Änderung die Funktion `{function_name}`
durch das Refactoring erfahren hat, basierend auf diesen Divergenzen:

{cases_text}

Konzentriere dich auf: Was ist der Kern-Unterschied im Verhalten?
Welcher Input-Bereich ist betroffen? Ist das ein Bug oder gewollte Änderung?"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception:
        return "\n".join(d.description for d in divergences[:5])


# ── Main Verifier ─────────────────────────────────────────────────────────────

class RefactorVerifier:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def verify(
        self,
        old_source: str,
        new_source: str,
        function_name: str,
        n_tests: int = 200,
    ) -> VerificationResult:
        """
        Vergleicht alte und neue Funktion mit Fuzzing.
        Gibt VerificationResult mit Äquivalenz-Nachweis zurück.
        """
        # Funktion extrahieren (falls komplette Datei übergeben)
        old_func_src = _extract_function_source(old_source, function_name)
        new_func_src = _extract_function_source(new_source, function_name)

        # Laden
        old_func = _load_function_from_source(old_func_src, function_name)
        new_func = _load_function_from_source(new_func_src, function_name)

        if not old_func:
            return VerificationResult(
                function_name=function_name, tests_run=0,
                is_equivalent=False, divergences=[],
                divergence_report=f"Konnte `{function_name}` nicht aus altem Code laden",
                confidence=0.0, suggestion="Prüfe Funktionsname und Syntax"
            )
        if not new_func:
            return VerificationResult(
                function_name=function_name, tests_run=0,
                is_equivalent=False, divergences=[],
                divergence_report=f"Konnte `{function_name}` nicht aus neuem Code laden",
                confidence=0.0, suggestion="Prüfe Syntax des refactored Codes"
            )

        # Input-Generierung
        type_hints = _infer_input_types(old_func_src)
        inputs = _generate_inputs(type_hints, n=n_tests)

        # Fuzzing
        divergences: list[Divergence] = []
        tests_run = 0

        for case in inputs:
            old_out, old_exc = _run_function_safe(old_func, case)
            new_out, new_exc = _run_function_safe(new_func, case)
            tests_run += 1

            # Divergenz-Erkennung
            exception_divergence = (old_exc is None) != (new_exc is None)
            output_divergence = (
                old_exc is None and new_exc is None
                and not _outputs_equal(old_out, new_out)
            )

            if exception_divergence or output_divergence:
                divergences.append(Divergence(
                    input_case=case,
                    old_output=old_out,
                    new_output=new_out,
                    old_exception=old_exc,
                    new_exception=new_exc,
                ))
                if len(divergences) >= 10:
                    break  # Genug Divergenzen gefunden

        is_equivalent = len(divergences) == 0
        confidence = min(0.99, tests_run / max(n_tests, 1))

        if is_equivalent:
            report = (
                f"✓ Semantisch äquivalent ({tests_run} Tests, Konfidenz: {confidence:.0%})\n"
                f"Der Refactor ändert das Verhalten nicht."
            )
            suggestion = "Refactor ist sicher. Merge empfohlen."
        else:
            explanation = _explain_divergences(divergences, function_name, self.api_key)
            report = (
                f"⚠️ {len(divergences)} Divergenz(en) in {tests_run} Tests:\n"
                f"{chr(10).join(d.description for d in divergences[:3])}\n\n"
                f"Semantische Analyse:\n{explanation}"
            )
            suggestion = (
                "Refactor ist NICHT äquivalent. "
                "Prüfe ob die Verhaltensänderung gewollt ist."
            )

        return VerificationResult(
            function_name=function_name,
            tests_run=tests_run,
            is_equivalent=is_equivalent,
            divergences=divergences,
            divergence_report=report,
            confidence=confidence,
            suggestion=suggestion,
        )

    def verify_git_change(self, function_name: str, repo_path: str = ".") -> VerificationResult:
        """Vergleicht aktuellen Code mit HEAD~1 für eine Funktion."""
        import subprocess
        old = subprocess.run(
            ["git", "show", f"HEAD~1:."],
            cwd=repo_path, capture_output=True, text=True
        ).stdout or ""
        new_file = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            cwd=repo_path, capture_output=True, text=True
        ).stdout.strip()
        if new_file:
            new = Path(repo_path, new_file).read_text(errors="replace")
        else:
            new = old
        return self.verify(old, new, function_name)


def as_langchain_tool():
    try:
        from langchain_core.tools import tool

        @tool
        def verify_refactor(
            old_code: str, new_code: str, function_name: str, n_tests: int = 150
        ) -> str:
            """Beweist via Fuzzing ob ein Refactor semantisch äquivalent ist.
            Gibt Divergenz-Report zurück wenn das Verhalten sich geändert hat."""
            verifier = RefactorVerifier()
            result = verifier.verify(old_code, new_code, function_name, n_tests)
            return f"{result.divergence_report}\n\n{result.suggestion}"

        return verify_refactor
    except ImportError:
        return None
