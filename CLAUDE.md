# CLAUDE.md — AI Intelligence Layer
## LangChain `.github` Repository

> **Primäre Instruktionsdatei** für alle KI-Assistenten (Claude Code, OpenClaw Skills, Copilot, Cursor).
> Vollständig lesen, bevor Änderungen gemacht werden.

---

## 1. Repository-Identität

Dies ist das **`langchain-ai/.github`** Organisations-Repository. Es enthält:

| Datei/Verzeichnis | Zweck |
|---|---|
| `profile/README.md` | GitHub-Org-Profil (öffentlich) |
| `CONTRIBUTING.md` | Beitragsrichtlinien für alle LangChain-Repos |
| `SECURITY.md` | Sicherheitsrichtlinie & Bug-Bounty-Programm |
| `CODE_OF_CONDUCT.md` | Community-Standards |
| `CLAUDE.md` | KI-Assistenten-Instruktionen (diese Datei) |
| `bootstrap/` | **One-Click AI-Bootstrapper** (OpenClaw + LangChain + a-Shell) |

**Kein Anwendungscode gehört hier rein.** Nur Org-Metadaten und Tooling-Bootstraps.

---

## 2. System-Architektur: OpenClaw + LangChain + a-Shell

```
┌─────────────────────────────────────────────────────────────┐
│                    REVOLUTIONÄRES AI-SYSTEM                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📱 a-Shell (iOS/iPadOS)                                    │
│     └── openclaw gateway          ← Laufzeitschicht        │
│           ├── Kanal: WebChat UI   ← Browser-Interface      │
│           ├── Kanal: iOS Shortcut ← Siri / Homescreen      │
│           ├── Kanal: Telegram     ← Mobile Messaging       │
│           └── Skill: langchain-dev ← DIESE REPO definiert  │
│                 ├── LangGraph Agent (Stateful)              │
│                 ├── Claude claude-sonnet-4-6 (Intelligenz)  │
│                 ├── LangChain Tools (Web, Code, FS)         │
│                 └── SQLite Memory (persistent)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Warum diese Kombination?

| Schicht | Rolle | Warum |
|---|---|---|
| **OpenClaw** | Gateway / Runtime / Multi-Channel | 247k Stars, Skills-System, iOS-ready, Node 22+ |
| **LangGraph** | Agentenlogik / Stateful Loops | Persistent Memory, bedingte Edges, Human-in-loop |
| **Claude API** | Intelligenz-Engine | Sonnet 4.6 für Reasoning, Haiku 4.5 für Speed |
| **LangChain** | Tool-Integrationen | Web-Search, Code-Execution, Vector-DBs |
| **a-Shell** | iOS Terminal | Einziger echter Unix-Shell auf iOS, hat `node`, `python3` |

### Datenfluß
```
User (Shortcut / Chat / Telegram)
    ↓
OpenClaw Gateway  ws://127.0.0.1:18789
    ↓
Pi Agent Runtime  (RPC-Modus)
    ↓
Skill: langchain-dev
    ↓
LangGraph StateGraph
    ├── Node: think     (Claude claude-sonnet-4-6)
    ├── Node: tools     (LangChain Tools)
    ├── Node: memory    (SQLite Checkpoint)
    └── Node: respond   (formatierte Antwort)
    ↓
Kanal-spezifisches Rendering
```

---

## 3. LangChain Ecosystem-Karte

```
langchain-ai/
├── langchain          # Python: LLM-Integrationen, Chains, Agents
├── langchainjs        # TypeScript: dasselbe für JS/TS
├── langgraph          # Python: Stateful Agent Graphs
├── langgraphjs        # TypeScript: dasselbe
├── deepagents         # Python: Planning-Agents mit Subagents + FS
├── deepagentsjs       # TypeScript: dasselbe
├── langsmith-sdk      # Observability & Tracing
├── langchain-mcp-adapters  # MCP → LangChain Tools Bridge
├── open-swe           # OSS Async Coding Agent
├── open-canvas        # Document+Chat UX
└── .github            # ← DU BIST HIER
```

### Kern-Abstraktionen

- **Runnable** — Universal-Interface: `.invoke()`, `.stream()`, `.batch()`
- **Chain** — Sequenz via LCEL (`|` Operator)
- **Tool** — LLM-aufrufbare Funktion mit Schema-Validierung
- **StateGraph** — LangGraph: Nodes + Edges + Checkpointer
- **Checkpoint** — Persistenz-Schicht (Memory zwischen Sessions)

---

## 4. OpenClaw Integration

### Skills-System Übersicht

OpenClaw Skills werden als Verzeichnisse mit `SKILL.md` gespeichert:

```
bootstrap/skills/langchain-dev/
├── SKILL.md          ← Skill-Metadaten & Instruktionen
├── tools.py          ← LangGraph Agent-Logik
├── memory.py         ← SQLite Checkpoint-Adapter
└── requirements.txt  ← Python-Abhängigkeiten
```

### SKILL.md Format

```markdown
---
name: langchain-dev
version: 1.0.0
description: LangChain + LangGraph development assistant
author: langchain-ai
requires:
  - python3
  - pip
env:
  - ANTHROPIC_API_KEY
  - LANGSMITH_API_KEY (optional)
---

# Skill Instructions für den Agent
...
```

### Wichtige OpenClaw CLI-Befehle

```bash
openclaw onboard                    # Ersteinrichtung
openclaw gateway                    # Gateway starten
openclaw agent                      # Agent starten
openclaw message send "text"        # Nachricht senden (für Shortcuts)
openclaw doctor                     # Diagnose
openclaw update --channel stable    # Update
```

### Chat-Befehle im OpenClaw Interface

```
/status     → System-Status
/new        → Neue Session
/reset      → Session zurücksetzen
/think      → Thinking-Level (off|minimal|low|medium|high|xhigh)
/compact    → Kontext komprimieren
/usage      → Token-Verbrauch
```

---

## 5. Entwicklungs-Konventionen

### Commit-Nachrichten
```
<typ>(<scope>): <kurze Beschreibung>

Typen: feat | fix | docs | chore | security | refactor | skill
Scope: profile | contributing | security | bootstrap | claude | skill

Beispiele:
  feat(skill): add LangGraph memory persistence to langchain-dev
  docs(claude): update OpenClaw integration architecture
  fix(bootstrap): correct Node version check in install.sh
```

### Branch-Naming
```
claude/<beschreibung>-<id>   # KI-assistierte Branches
fix/<issue-nr>-<desc>        # Bug-Fixes
feat/<name>                  # Neue Features
skill/<skill-name>           # Skill-Entwicklung
```

### PR-Regeln (werden durchgesetzt)
1. Muss auf genehmigtes Issue/Discussion verlinken
2. PR-Template vollständig ausfüllen
3. Keine automatisierten Massen-PRs
4. Low-effort PRs werden kommentarlos geschlossen

---

## 6. KI-Assistenten Direktiven

### `profile/README.md` bearbeiten
- LangChain-Branding-Div-Struktur beibehalten
- Badge-Reihenfolge: X/Twitter → LinkedIn → YouTube
- Sektionen: Core OSS → Commercial → Extensions → Learn more
- SVGs sind theme-aware — nie einzelne URL hardcoden

### `CONTRIBUTING.md` bearbeiten
- "muss auf genehmigtes Issue verlinken" NIE abschwächen
- Anti-Spam-Sprache über Low-Effort-PRs beibehalten
- Ton: einladend aber bestimmt

### `SECURITY.md` bearbeiten
- Bounty-Beträge NIE ohne explizite menschliche Genehmigung senken
- LangSmith-Scope von OSS-Scope getrennt halten

### `bootstrap/` bearbeiten
- Immer idempotent: Skripte müssen mehrfach sicher ausführbar sein
- a-Shell Kompatibilität prüfen: kein `brew`, kein `apt`, nur `pkg`
- Secrets NIEMALS in Skripte hardcoden — immer `read -s` oder env

### Allgemeine Regeln
- Keine neuen Dateien ohne explizite Anfrage
- Kein Anwendungscode im Root
- Alle Änderungen via PR — kein direkter Push auf `main`
- Markdown: keine trailing spaces, konsistente Heading-Level

---

## 7. Dateien die NICHT von KI ohne menschliche Prüfung geändert werden dürfen

- `SECURITY.md` (Bounty-Beträge, rechtliche Sprache)
- `CODE_OF_CONDUCT.md` (Community-Standards)
- `CONTRIBUTING.md` (Beitrags-Gate-Anforderungen)
- `bootstrap/install.sh` (wird per `curl | sh` ausgeführt — sicherheitskritisch)
- Alles in `.git/`

---

## 8. Quick-Reference für häufige Aufgaben

### Neues Projekt zum Org-Profil hinzufügen
```markdown
# In profile/README.md, zur passenden Sektion hinzufügen:
- [`Projektname`](https://github.com/langchain-ai/projektname) – Kurzbeschreibung (Sprache)
```

### Neuen OpenClaw Skill entwickeln
```bash
# Skill-Verzeichnis erstellen
mkdir -p bootstrap/skills/mein-skill

# SKILL.md erstellen (Metadaten + Instruktionen)
# tools.py erstellen (Logik)
# requirements.txt erstellen

# Lokal testen
openclaw gateway &
openclaw agent --skill ./bootstrap/skills/mein-skill
```

### a-Shell One-Click-Install
```bash
# In a-Shell auf iOS:
curl -fsSL https://raw.githubusercontent.com/langchain-ai/.github/main/bootstrap/install.sh | sh
```

---

## 9. Umgebungs-Setup

```bash
# Für Bootstrap-Entwicklung (macOS/Linux):
node --version          # Muss 22.16+ oder 24+
python3 --version       # Muss 3.11+

# Dependencies
npm install -g openclaw
python3 -m pip install anthropic langgraph langchain-community langchain-anthropic

# a-Shell (iOS) — automatisch via bootstrap/install.sh
```

---

*Zuletzt aktualisiert: 2026-03-23 — LangChain AI Team + Claude Code + OpenClaw Integration*

Sources:
- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Website](https://openclaw.ai/)
- [LangGraph Docs](https://github.com/langchain-ai/langgraph)
