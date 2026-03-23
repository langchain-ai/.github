---
name: coding
version: 1.0.0
description: >
  High-end Chat + Coding Intelligence Layer — 6 global-unique Features
  die weder Cursor, Copilot, Aider, ChatGPT noch SWE-bench-Agenten
  in dieser Kombination implementiert haben.
author: langchain-ai
license: MIT
requires:
  runtime: python3>=3.11
  packages:
    - hypothesis>=6.0.0
    - anthropic>=0.40.0
env:
  optional:
    - ANTHROPIC_API_KEY   # Für Claude-Erklärungen (Haiku)
entrypoint: null          # Modulares Skill — via agent.py importiert
---

# coding — High-End Chat + Coding Intelligence

## Die 6 global-unique Features

### 1. Causal Diff Explainer (`causal_diff.py`)
```python
from causal_diff import CausalDiffExplainer
result = CausalDiffExplainer().explain(diff_text, pytest_output)
print(result.plain_explanation)   # "calculate_price() gibt falschen Wert..."
print(result.fix_suggestions)     # ["Füge Steuer-Multiplikator hinzu...", ...]
```
**Einzigartig**: Kein Tool erklärt den *kausalen Pfad* warum ein Diff
einen Test bricht — nur korrelativ ("Test X ist rot"). Dieses Modul
rekonstruiert via AST-Dataflow-Rückverfolgung: "Funktion A → Variable B
→ Assertion C bricht *weil Invariante D verletzt*".

### 2. Live Invariant Miner (`invariant_miner.py`)
```python
from invariant_miner import InvariantMiner
miner = InvariantMiner()
miner.trace(my_function, inputs=[(1, 2), (3, 4), (-1, 0)])
miner.mine_and_write("tests/invariants/")  # Schreibt Hypothesis-Tests
```
**Einzigartig**: Beobachtet echte Laufzeitwerte via `sys.settrace()`,
leitet Wertebereiche/Typen/Invarianten ab und schreibt vollständige
`@hypothesis.given()`-Tests zurück. Wächst mit jeder Session.

### 3. Semantic Revert Advisor (`revert_advisor.py`)
```python
from revert_advisor import SemanticRevertAdvisor
result = SemanticRevertAdvisor().analyze("calculate_price", last_n=20)
print(result.recommendation)   # "Revert abc1234: Intent gebrochen weil..."
print(result.revert_command)   # "git revert abc1234"
```
**Einzigartig**: `git bisect` findet *wann* Tests brachen. Dieses Tool
findet *welcher Commit den semantischen Intent* gebrochen hat —
auch bevor Tests greifen. Intent-Drift-Score per Commit via Haiku.

### 4. Cross-Session Code Smell Memory (`smell_memory.py`)
```python
from smell_memory import analyze_code, SmellMemory, check_message_for_smells
warning = check_message_for_smells(user_message)  # Before-Hook in agent.py
# → "⚠️ N+1 Query — 4x von dir gesehen! 💡 Nutze .prefetch_related()"
```
**Einzigartig**: Merkt sich *user-spezifische* Anti-Pattern über Sessions.
"Du schreibst immer N+1 Queries" — 4. Mal dieselbe Warnung, aber mit
"4x von dir gesehen!" Kontext. Fingerprinting via normalisiertem AST-Hash.

### 5. Intent-Preserving Refactor Verifier (`refactor_verifier.py`)
```python
from refactor_verifier import RefactorVerifier
result = RefactorVerifier().verify(old_src, new_src, "calculate_tax", n_tests=200)
print(result.is_equivalent)       # True/False
print(result.divergence_report)   # "Input (0, -1): alt=0.0 → neu=None"
```
**Einzigartig**: Beweist formal via Fuzzing ob ein Refactor semantisch
äquivalent ist. 200 Zufalls-Inputs, Claude erklärt Divergenzen.
Kein Cursor/Aider/Copilot macht das.

### 6. Conversation State Machine (`chat_modes.py`)
```
💬 [Chat]         — Kurze Antworten, minimale Tools
⌨️ [Coding]       — Alle Code-Tools, vollständige Implementierungen
🐛 [Debugging]    — Strukturierte Kausal-Analyse, CausalDiff aktiv
🏗️ [Architecture] — Konzeptuell, ASCII-Diagramme, Trade-offs
👥 [Pair Program] — Turn-by-Turn Kollaboration, TTS-Review
🔍 [Review]       — SmellMemory + CausalDiff + strukturierter Output
```
**Einzigartig**: Explizite Konversations-Modi mit verschiedenen Tool-Inventars,
Memory-Strategien und Rendering-Regeln. Automatische Intent-Erkennung.
`/coding`, `/debug`, `/review` für manuellen Wechsel.

## Wirkungsgrad-Vergleich

| Feature | Cursor | Aider | Copilot Chat | SWE-Bench | **coding/** |
|---|:---:|:---:|:---:|:---:|:---:|
| Kausaler Diff-Erklärer | ✗ | ✗ | ✗ | ✗ | **✓** |
| Invariant Mining | ✗ | ✗ | ✗ | ✗ | **✓** |
| Semantic Revert Advisor | ✗ | ✗ | ✗ | ✗ | **✓** |
| User-spezifische Smell-History | ✗ | ✗ | ✗ | ✗ | **✓** |
| Fuzzing-basierter Refactor-Verifier | ✗ | ✗ | ✗ | ✗ | **✓** |
| Konversations-Zustandsautomat | ✗ | ✗ | ✗ | ✗ | **✓** |
| Code ausführen | ✗ | ✓ | ✗ | ✓ | ✓ |
| Diff-Editing | ✓ | ✓ | ✗ | ✓ | ✓ |

## Chat-Modus Wechseln

```
/coding      — Aktiviert Coding-Modus
/debug       — Aktiviert Debugging-Modus
/review      — Aktiviert Code-Review-Modus
/arch        — Aktiviert Architecture-Modus
/pair        — Aktiviert Pair-Programming-Modus
/chat        — Zurück zu normalem Chat
```

Oder automatisch durch Message-Intent (Traceback → Debug-Modus etc.)
