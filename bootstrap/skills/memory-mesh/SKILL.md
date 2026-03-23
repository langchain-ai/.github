---
name: memory-mesh
version: 0.1.0
description: >
  Ambient Context Memory Mesh (ACMM) — weltweit erste OSS-Implementierung
  eines passiven, offline-fähigen, semantischen Langzeitgedächtnisses
  für iOS (a-Shell) + OpenClaw + LangGraph. Kein Vektordatenbank-Server.
  Kein Embedding-API. 100% lokal, 100% privat.
author: langchain-ai
license: MIT
requires:
  runtime: python3
  node: ">=22.16.0"
env:
  required:
    - ANTHROPIC_API_KEY
  optional:
    - ACMM_MODEL          # sentence-transformer Modell (default: all-MiniLM-L6-v2)
    - ACMM_DB_PATH        # SQLite-Pfad (default: ~/.langchain-assistant/data/memory.db)
entrypoint: null          # Kein eigener Entrypoint — wird von langchain-dev importiert
---

# memory-mesh Skill

## Was ist das?

Das **Ambient Context Memory Mesh (ACMM)** ist ein passives Gedächtnissystem
das kontinuierlich lernt — auch wenn du nichts fragst.

**Kern-Innovation:** Alle anderen AI-Assistenten haben Session-Memory oder
einfaches chronologisches Memory. ACMM kombiniert:

1. **Semantisches Retrieval** statt chronologischer Suche
2. **Offline-Embeddings** (sentence-transformers, kein API-Call)
3. **Automatische Kompression** via Haiku (teuer → destilliert → dauerhaft)
4. **Ambient Capture** von iOS-Kontext via Shortcuts
5. **Proaktive Briefings** (Agent initiiert, nicht nur antwortet)

## Architektur

```
iOS Shortcuts (Clipboard, App-Wechsel, Focus-Mode)
    ↓ [passiv, kein User-Eingriff]
OpenClaw Ambient Ingestion
    ↓
embedder.SemanticMemory.ingest_ambient()
    ↓ [sentence-transformers, lokal, offline]
SQLite (FTS5 + Vektor-BLOBs)
    ↓
compressor.MemoryCompressor (Haiku, täglich 23:00)
    ↓ [Signale → kompakte Facts]
scheduler.ACMMScheduler (täglich 08:00)
    ↓ [proaktives Morning Briefing]
OpenClaw Message → User
```

## Datei-Übersicht

| Datei | Funktion |
|---|---|
| `embedder.py` | Offline-Embeddings + SQLite FTS5 + Cosine-Retrieval |
| `compressor.py` | Haiku-basierte Memory-Kompression zu Facts |
| `scheduler.py` | APScheduler: Morning Briefing, Ambient Compress, Maintenance |

## iOS Shortcuts Integration

Erstelle diese Shortcuts in der iOS Shortcuts-App:

### 1. Clipboard Monitor
```
Auslöser: Clipboard-Inhalt geändert (Automatisierung)
Aktion: a-Shell
  Befehl: openclaw message send "[AMBIENT:clipboard] $(pbpaste | head -c 200)"
```

### 2. App Focus Tracker
```
Auslöser: Bestimmte App wird geöffnet (Safari, Xcode, Notes, ...)
Aktion: a-Shell
  Befehl: openclaw message send "[AMBIENT:app] Geöffnet: [App Name]"
```

### 3. Focus Mode Wechsel
```
Auslöser: Focus aktiviert/deaktiviert
Aktion: a-Shell
  Befehl: openclaw message send "[AMBIENT:focus] [Focus Name] aktiviert"
```

## Retrieval-Qualität

| System | Retrieval | Offline | iOS | Proaktiv |
|---|---|---|---|---|
| **ACMM** | Semantisch + FTS5 | ✓ | ✓ | ✓ |
| MemGPT/Letta | Semantisch | ✗ | ✗ | ✗ |
| Rewind.ai | Keyword | ✓ | ✗ | ✗ |
| Vanilla ChatGPT | Chronologisch | ✗ | Teilweise | ✗ |

## Datenschutz

- Alle Daten verbleiben auf dem Gerät (`~/.langchain-assistant/data/`)
- Embeddings werden lokal berechnet (keine API-Calls)
- Nur Memory-Kompression via Haiku ist API-abhängig
- Offline-Modus: Kompression wird verzögert bis API verfügbar
