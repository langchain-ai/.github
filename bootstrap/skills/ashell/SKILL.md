---
name: ashell
version: 1.0.0
description: >
  a-Shell Exclusive AI Layer — Fünf global-unique Funktionen die
  ausschließlich auf a-Shell (iOS/iPadOS) möglich sind. Kein macOS,
  kein Linux, kein Android kann diese Kombination replizieren.
author: langchain-ai
license: MIT
platform: a-Shell (iOS/iPadOS) only
requires:
  runtime: python3
  apps_optional:
    - Drafts 5 (drafts5://)
    - Working Copy (working-copy://)
    - Scriptable (scriptable://)
    - Things 3 (things:///)
env:
  optional:
    - ANTHROPIC_API_KEY      # Für sensor_briefing.py Haiku-Kompression
    - ACMM_TTS_LANG          # 'de' oder 'en' (default: auto-detect)
    - WORKING_COPY_KEY       # API-Key für Working Copy Git-Aktionen
entrypoint: null             # Modulares Skill — wird von agent.py importiert
---

# ashell — a-Shell Exclusive AI Layer

## Die 5 global-unique Funktionen

### 1. Clipboard-Diff-Intelligence (`clipboard_daemon.py`)
```bash
# Starten (Tab 2 in a-Shell):
python3 bootstrap/skills/ashell/clipboard_daemon.py
```
- Pollt iOS-Clipboard via `pbpaste` alle 3 Sekunden
- Klassifiziert: `code` | `url` | `json` | `numbers` | `prose`
- Bei Code: automatische Analyse-Anfrage an Agent
- Läuft im Hintergrund während User andere Apps nutzt
- **Einzigartig**: Background-Execution + Clipboard-Zugriff ohne Permission

### 2. Voice Code Review (`tts.py`)
```python
from tts import code_review_speak, ReviewFinding, speak
findings = [
    ReviewFinding("SQL Injection in Zeile 42", "critical", 42),
    ReviewFinding("Fehlende Fehlerbehandlung", "warning", 87),
]
code_review_speak(findings)
```
- Verschiedene iOS-Stimmen per Severity (Samantha=kritisch, Karen=Warnung)
- Developer liest Code, Agent spricht Review gleichzeitig
- Kognitive Modalitäts-Trennung: HÖREN + LESEN parallel
- **Einzigartig**: AVSpeechSynthesizer ohne Entitlement aus Shell-Prozess

### 3. iCloud Session Handoff (`icloud_handoff.py`)
```python
from icloud_handoff import iCloudHandoff
h = iCloudHandoff()
h.save(thread_id="abc", tasks=["Bug fix"], summary="Arbeite an Auth")
# → Erscheint in Sekunden auf iPhone/iPad/Mac in ~/iCloud/LangChain/
```
- `~/iCloud/` = POSIX-Pfad in a-Shell → Apple CloudKit übernimmt Sync
- Atomic write (APFS): kein Datenverlust bei Abbruch
- Shared Clipboard Bridge: ersetzt AirDrop für Text
- Watcher für automatisches Handoff-Pickup
- **Einzigartig**: Kein AI-System hat Cross-Device-Sync ohne eigenen Server

### 4. iOS App-Orchestrator (`url_orchestrator.py`)
```python
from url_orchestrator import DraftsApp, ThingsApp, ShortcutsApp
DraftsApp.create("AI-generierter Text", tags=["ai"])
ThingsApp.add_task("Bug fixen", list_name="Arbeit")
ShortcutsApp.run("Mein Shortcut", input_data="Parameter")
```
- `open "app://action?x-success=ashell://run?cmd=..."` = vollständiger Callback
- Unterstützt: Drafts, Working Copy, Scriptable, Things 3, Shortcuts
- Agent kann Git-Commits via Working Copy ohne eigene Credentials machen
- LangChain `@tool`-kompatibel — direkt in agent.py registrierbar
- **Einzigartig**: x-callback-url Callback-Loop in Shell ohne Server

### 5. Sensor-fused Briefing (`sensor_briefing.py`)
```bash
python3 bootstrap/skills/ashell/sensor_briefing.py run
```
7 Signalquellen → ein personalisiertes Briefing:
1. ⏰ Uhrzeit + Wochentag (immer)
2. 📋 iOS Clipboard (`pbpaste`, a-Shell exklusiv)
3. 🎯 Focus-Mode (via Signal-Datei aus Shortcuts)
4. 📁 iCloud-Dateien heute geändert (`~/iCloud/` POSIX)
5. ✅ Offene Tasks (local JSON)
6. 💡 ACMM Memory Facts (letzte 48h)
7. 🔄 Haiku-Kompression → natürliche Sprache (offline: regelbasiert)

**Einzigartig**: Einzige OSS-Lösung die alle 7 Signale kombiniert.

## Vergleichstabelle

| Funktion | a-Shell | macOS | Linux | Android | ChatGPT App |
|---|:---:|:---:|:---:|:---:|:---:|
| `pbpaste` Background-Daemon | **✓** | ✓¹ | ✗ | ✗ | ✗ |
| iOS TTS ohne Entitlement | **✓** | ✗ | ✗ | ✗ | ✗ |
| `~/iCloud/` als POSIX-Pfad | **✓** | ✓¹ | ✗ | ✗ | ✗ |
| URL-Scheme Callback-Loop | **✓** | ✗ | ✗ | ✗ | ✗ |
| Focus-Mode + Clipboard + iCloud kombiniert | **✓** | ✗ | ✗ | ✗ | ✗ |

¹ Auf macOS verfügbar, aber ohne persistente Background-AI-Session

## Setup

```bash
# iOS Shortcuts für Focus-Mode Tracking:
# Auslöser: Focus aktiviert/deaktiviert
# Aktion: a-Shell
#   Befehl: echo "[Focus Name]" > ~/Documents/.current_focus

# Clipboard-Daemon starten (Tab 2):
python3 ~/.langchain-assistant/skills/ashell/clipboard_daemon.py

# Sensor-Briefing testen:
python3 ~/.langchain-assistant/skills/ashell/sensor_briefing.py offline
```
