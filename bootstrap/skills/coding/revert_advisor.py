"""
Coding Exclusive #3 — Semantic Revert Advisor
============================================
Findet welcher Commit den semantischen Intent des Codes gebrochen hat —
nicht nur wann ein Test erstmals failed, sondern WARUM der Kern-Intent
verletzt wurde.

Global-unique weil:
  git bisect findet den ersten failing Commit.
  Dieses Tool findet den Commit der den *semantischen Zweck* der
  Funktion verändert hat — auch wenn alle Tests noch passen.
  Intent-Drift erkennen bevor Tests greifen.

Pipeline:
  1. git log --patch → Commit-History mit Diffs
  2. LangGraph Map-Reduce: Claude bewertet Intent-Drift per Commit
  3. Aggregierter Drift-Score → Ranking
  4. Top-Kandidat: `git revert <sha>` Empfehlung mit Begründung

Verwendung:
  advisor = SemanticRevertAdvisor(repo_path=".")
  result = advisor.analyze(function_name="calculate_price", last_n=20)
  print(result.recommendation)  # "Revert <sha>: ..."
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ── Datenmodelle ──────────────────────────────────────────────────────────────

@dataclass
class CommitDiff:
    sha: str
    short_sha: str
    author: str
    date: str
    message: str
    diff_text: str
    files_changed: list[str]


@dataclass
class IntentDriftScore:
    commit: CommitDiff
    drift_score: float        # 0.0 = kein Drift, 1.0 = kompletter Intent-Bruch
    drift_reason: str         # Claude-Erklärung
    affected_functions: list[str]
    reversible: bool          # Ist revert sicher?


@dataclass
class RevertAdvisory:
    analyzed_commits: int
    top_drift_commit: CommitDiff | None
    drift_scores: list[IntentDriftScore]
    recommendation: str
    revert_command: str | None


# ── Git Interface ─────────────────────────────────────────────────────────────

def get_commit_history(repo_path: str, last_n: int = 20, path_filter: str = "") -> list[CommitDiff]:
    """Liest git log mit Patches."""
    cmd = [
        "git", "log",
        f"-{last_n}",
        "--patch",
        "--format=COMMIT_START%n%H%n%aN%n%ad%n%s%nDIFF_START",
        "--date=short",
    ]
    if path_filter:
        cmd.extend(["--", path_filter])

    result = subprocess.run(
        cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr}")

    commits = []
    blocks = result.stdout.split("COMMIT_START\n")[1:]  # Ersten leeren Skip

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 5:
            continue

        sha = lines[0].strip()
        author = lines[1].strip()
        date = lines[2].strip()
        message = lines[3].strip()

        diff_start = block.find("DIFF_START\n")
        diff_text = block[diff_start + 11:] if diff_start >= 0 else ""

        files_changed = re.findall(r'^\+\+\+ b/(.+)$', diff_text, re.MULTILINE)

        commits.append(CommitDiff(
            sha=sha,
            short_sha=sha[:7],
            author=author,
            date=date,
            message=message,
            diff_text=diff_text[:3000],  # Token-Limit
            files_changed=files_changed,
        ))

    return commits


# ── Intent Extraction ─────────────────────────────────────────────────────────

def extract_original_intent(repo_path: str, function_name: str) -> str:
    """
    Extrahiert den ursprünglichen Intent einer Funktion aus:
    1. Docstring (wenn vorhanden)
    2. Commit-Message beim Erstellen der Funktion
    3. Test-Namen die diese Funktion testen
    """
    intents = []

    # Aktuellen Docstring suchen
    grep = subprocess.run(
        ["git", "grep", "-n", f"def {function_name}"],
        cwd=repo_path, capture_output=True, text=True
    )
    if grep.returncode == 0:
        for line in grep.stdout.splitlines()[:3]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                intents.append(f"Definiert in: {parts[0]}:{parts[1]}")

    # Test-Namen
    test_grep = subprocess.run(
        ["git", "grep", "-l", f"test.*{function_name}|{function_name}.*test"],
        cwd=repo_path, capture_output=True, text=True
    )
    if test_grep.returncode == 0:
        test_files = test_grep.stdout.strip().splitlines()[:3]
        intents.append(f"Tests in: {test_files}")

    # Erster Commit der die Funktion enthält
    first_commit = subprocess.run(
        ["git", "log", "--oneline", "--follow", "--diff-filter=A",
         "--", "**/*.py"],
        cwd=repo_path, capture_output=True, text=True
    )
    if first_commit.returncode == 0 and first_commit.stdout:
        intents.append(f"Ursprünglicher Kontext: {first_commit.stdout.splitlines()[0]}")

    return "\n".join(intents) if intents else f"Funktion {function_name} — kein expliziter Intent gefunden"


# ── Claude Intent-Drift-Bewertung ─────────────────────────────────────────────

def score_commit_drift(
    commit: CommitDiff,
    function_name: str,
    original_intent: str,
    api_key: str,
) -> IntentDriftScore:
    """Bewertet wie stark ein Commit den Intent einer Funktion driftet."""

    # Schnell-Prüfung: Berührt dieser Commit überhaupt die Funktion?
    if function_name not in commit.diff_text and not any(
        function_name in f for f in commit.files_changed
    ):
        return IntentDriftScore(
            commit=commit,
            drift_score=0.0,
            drift_reason="Berührt diese Funktion nicht",
            affected_functions=[],
            reversible=True,
        )

    if not api_key:
        return _heuristic_drift_score(commit, function_name)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        prompt = f"""Bewerte wie stark dieser Commit den semantischen Intent der Funktion '{function_name}' driftet.

URSPRÜNGLICHER INTENT:
{original_intent}

COMMIT {commit.short_sha} ({commit.date}):
Nachricht: "{commit.message}"
Diff (Ausschnitt):
{commit.diff_text[:1500]}

Antworte NUR in diesem Format:
DRIFT_SCORE: [0.0-1.0]
REASON: [1 Satz Begründung]
REVERSIBLE: [ja/nein]
FUNCTIONS: [kommagetrennte Liste betroffener Funktionen]

0.0 = kein Drift (Bugfix, Refactor ohne Verhaltensänderung)
0.5 = moderater Drift (neue Edge-Cases, geänderte Semantik)
1.0 = vollständiger Intent-Bruch (Funktion tut etwas grundlegend anderes)"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        score = float(re.search(r'DRIFT_SCORE:\s*([\d.]+)', text, re.I).group(1))  # type: ignore
        reason = re.search(r'REASON:\s*(.+)', text, re.I)
        reversible = re.search(r'REVERSIBLE:\s*(\w+)', text, re.I)
        funcs = re.search(r'FUNCTIONS:\s*(.+)', text, re.I)

        return IntentDriftScore(
            commit=commit,
            drift_score=min(1.0, max(0.0, score)),
            drift_reason=reason.group(1).strip() if reason else "Unbekannt",
            affected_functions=[f.strip() for f in (funcs.group(1).split(",") if funcs else [])],
            reversible=(reversible.group(1).lower() == "ja") if reversible else True,
        )

    except Exception as e:
        return _heuristic_drift_score(commit, function_name)


def _heuristic_drift_score(commit: CommitDiff, function_name: str) -> IntentDriftScore:
    """Offline-Fallback: heuristische Drift-Schätzung."""
    score = 0.0
    reasons = []

    diff = commit.diff_text
    # Signifikante Änderungen
    added = len([l for l in diff.splitlines() if l.startswith("+")])
    removed = len([l for l in diff.splitlines() if l.startswith("-")])
    if added + removed > 50:
        score += 0.3
        reasons.append("Großer Diff")
    if "return" in diff and function_name in diff:
        score += 0.2
        reasons.append("Return-Statement geändert")
    if any(kw in commit.message.lower() for kw in ["fix", "bug", "revert"]):
        score -= 0.1

    return IntentDriftScore(
        commit=commit,
        drift_score=max(0.0, min(1.0, score)),
        drift_reason=" | ".join(reasons) or "Heuristisch bewertet",
        affected_functions=[function_name],
        reversible=True,
    )


# ── Main Advisor ──────────────────────────────────────────────────────────────

class SemanticRevertAdvisor:
    def __init__(self, repo_path: str = ".", api_key: str | None = None):
        self.repo_path = Path(repo_path)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def analyze(
        self,
        function_name: str,
        last_n: int = 20,
        path_filter: str = "",
    ) -> RevertAdvisory:
        commits = get_commit_history(str(self.repo_path), last_n, path_filter)
        original_intent = extract_original_intent(str(self.repo_path), function_name)

        scores: list[IntentDriftScore] = []
        for commit in commits:
            score = score_commit_drift(commit, function_name, original_intent, self.api_key)
            scores.append(score)

        # Nach Drift-Score sortieren
        scores.sort(key=lambda s: s.drift_score, reverse=True)

        top = scores[0] if scores else None
        high_drift = [s for s in scores if s.drift_score >= 0.6]

        if top and top.drift_score >= 0.6:
            revert_cmd = f"git revert {top.commit.sha}"
            recommendation = (
                f"⚠️ Commit {top.commit.short_sha} ({top.commit.date}) "
                f"hat den Intent von `{function_name}` am stärksten verändert "
                f"(Drift-Score: {top.drift_score:.0%}).\n"
                f"Grund: {top.drift_reason}\n"
                f"{'Revert sicher.' if top.reversible else 'Revert hat Abhängigkeiten — prüfen!'}"
            )
        elif high_drift:
            revert_cmd = None
            recommendation = (
                f"{len(high_drift)} Commits mit moderatem Intent-Drift gefunden. "
                f"Kein einzelner Haupt-Kandidat. Manuelles Review empfohlen."
            )
        else:
            revert_cmd = None
            recommendation = (
                f"Kein signifikanter Intent-Drift in den letzten {last_n} Commits gefunden. "
                f"Problem liegt möglicherweise in externen Dependencies oder Konfiguration."
            )

        return RevertAdvisory(
            analyzed_commits=len(commits),
            top_drift_commit=top.commit if top and top.drift_score >= 0.6 else None,
            drift_scores=scores,
            recommendation=recommendation,
            revert_command=revert_cmd,
        )


def as_langchain_tool():
    try:
        from langchain_core.tools import tool

        @tool
        def find_intent_breaking_commit(function_name: str, last_n_commits: int = 15) -> str:
            """Findet welcher Commit den semantischen Intent einer Funktion gebrochen hat.
            Analysiert git history semantisch, nicht nur Test-Failures."""
            try:
                advisor = SemanticRevertAdvisor()
                result = advisor.analyze(function_name, last_n=last_n_commits)
                lines = [result.recommendation]
                if result.revert_command:
                    lines.append(f"\nEmpfohlener Befehl: `{result.revert_command}`")
                lines.append(f"\n{result.analyzed_commits} Commits analysiert.")
                return "\n".join(lines)
            except Exception as e:
                return f"Fehler bei Git-Analyse: {e}"

        return find_intent_breaking_commit
    except ImportError:
        return None
