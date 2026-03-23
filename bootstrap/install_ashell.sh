#!/bin/sh
# =============================================================================
# LangChain AI Assistant — a-Shell Native Installer
# Nur für: a-Shell (iOS/iPadOS) und Termux (Android)
#
# Installiert OHNE Rust/Maturin/native Compiler:
#   pip install anthropic --prefer-binary  (pure Python SDK)
#
# LangChain/LangGraph werden NICHT installiert — pydantic-core braucht Rust.
# Stattdessen: agent_mini.py (reiner anthropic SDK Agent, vollständig kompatibel)
#
# Verwendung in a-Shell:
#   python3 -c "import urllib.request as u; u.urlretrieve('https://' + 'raw.githubusercontent.com/langchain-ai/.github/main/bootstrap/install_ashell.sh', 'install_ashell.sh'); print('OK')"
#   sh install_ashell.sh
# =============================================================================

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

ok()   { printf "${GREEN}[✓]${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}[!]${RESET} %s\n" "$*"; }
step() { printf "\n${BOLD}${CYAN}── %s ──${RESET}\n" "$*"; }
err()  { printf "${YELLOW}[!]${RESET} %s\n" "$*" >&2; }

printf "\n${BOLD}${CYAN}LangChain Mini Agent — a-Shell Setup${RESET}\n\n"

# ── Pfade (nur ~/Documents/ ist auf iOS schreibbar) ───────────────────────────
DOCS="${HOME}/Documents"
INSTALL_DIR="${DOCS}/.langchain-assistant"
SKILL_DIR="${INSTALL_DIR}/skills/langchain-dev"
DATA_DIR="${INSTALL_DIR}/data"
CONFIG_FILE="${INSTALL_DIR}/config.env"
BIN_DIR="${DOCS}/bin"

mkdir -p "$SKILL_DIR" "$DATA_DIR" "$BIN_DIR"
ok "Verzeichnisse erstellt"

# ── Python prüfen ─────────────────────────────────────────────────────────────
step "Python prüfen"
PYTHON_CMD=""
for py in python3 python3.13 python3.12 python3.11; do
    if command -v "$py" >/dev/null 2>&1; then
        VER="$("$py" --version 2>&1)"
        ok "$VER gefunden"
        PYTHON_CMD="$py"
        break
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    err "Python3 nicht gefunden — führe 'pkg install python' aus"
    exit 1
fi

# ── anthropic installieren (pure Python, kein Rust) ───────────────────────────
step "anthropic SDK installieren"

"$PYTHON_CMD" -m pip install anthropic --prefer-binary --quiet \
    && ok "anthropic installiert" \
    || {
        warn "pip install fehlgeschlagen — versuche mit --no-build-isolation..."
        "$PYTHON_CMD" -m pip install anthropic --prefer-binary --no-build-isolation --quiet \
            && ok "anthropic installiert (fallback)" \
            || { err "anthropic Installation fehlgeschlagen"; exit 1; }
    }

# ── Verifikation ──────────────────────────────────────────────────────────────
"$PYTHON_CMD" -c "from anthropic import Anthropic; print('  SDK import OK')" \
    || { err "anthropic Import fehlgeschlagen"; exit 1; }

# ── git Wrapper (lg2 → git) ────────────────────────────────────────────────────
step "git Wrapper einrichten"

if command -v lg2 >/dev/null 2>&1; then
    # Sicherheit: BIN_DIR als Datei? Entfernen.
    if [ -e "$BIN_DIR" ] && [ ! -d "$BIN_DIR" ]; then
        rm -f "$BIN_DIR"
        mkdir -p "$BIN_DIR"
    fi
    {
        echo '#!/bin/sh'
        echo 'lg2 "$@"'
    } > "${BIN_DIR}/git"
    chmod +x "${BIN_DIR}/git"
    ok "git → lg2 Wrapper erstellt"
else
    warn "lg2 nicht gefunden — 'pkg install git' ausführen für git-Unterstützung"
fi

# ── agent_mini.py direkt einbetten (kein Download nötig) ─────────────────────
step "agent_mini.py erstellen (eingebettet)"

AGENT_OUT="${SKILL_DIR}/agent_mini.py"

# Python schreibt den Agent direkt — kein Netzwerk, keine URL-Probleme
"$PYTHON_CMD" - "$AGENT_OUT" << 'WRITE_AGENT'
import sys, os, textwrap

dest = sys.argv[1]
os.makedirs(os.path.dirname(dest), exist_ok=True)

code = textwrap.dedent('''
    """agent_mini.py — a-Shell Native Agent (anthropic SDK only)"""
    from __future__ import annotations
    import json, os, sqlite3, subprocess, sys
    from datetime import datetime
    from pathlib import Path

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 4096
    MAX_ROUNDS = 8

    _DOCS = Path(os.path.expanduser("~")) / "Documents"
    _DATA = _DOCS / ".langchain-assistant" / "data"
    _DATA.mkdir(parents=True, exist_ok=True)
    DB_PATH = _DATA / "memory.db"

    SYSTEM = """You are a helpful AI assistant with tool use.
    Tools: run_python, read_file, write_file, shell_safe.
    Be direct. Code-first for technical questions.""".strip()

    TOOLS = [
        {"name":"run_python","description":"Execute Python code. Returns stdout/stderr.",
         "input_schema":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}},
        {"name":"read_file","description":"Read file from ~/Documents/",
         "input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
        {"name":"write_file","description":"Write file to ~/Documents/",
         "input_schema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
        {"name":"shell_safe","description":"Run safe shell command (ls,pwd,git log,pip list)",
         "input_schema":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}},
    ]

    _BLOCKED = ["__import__","exec(","eval(","compile(","ctypes","os.system(","os.execv","socket"]
    _SAFE    = ["ls","pwd","echo","cat","head","tail","git log","git status","pip list","pip show","lg2"]

    def _run_python(code):
        if any(p in code.lower() for p in _BLOCKED):
            return "[BLOCKED] Unsafe pattern."
        try:
            r = subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=15)
            return (r.stdout+r.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired: return "[TIMEOUT]"
        except Exception as e: return f"[ERROR] {e}"

    def _read_file(path):
        p = _DOCS / path.lstrip("/")
        try:
            t = p.read_text(encoding="utf-8",errors="replace")
            return t[:8000]+(f"\\n[truncated {len(t)}]" if len(t)>8000 else "")
        except Exception as e: return f"[ERROR] {e}"

    def _write_file(path, content):
        p = _DOCS / path.lstrip("/")
        p.parent.mkdir(parents=True,exist_ok=True)
        try: p.write_text(content,encoding="utf-8"); return f"[OK] {p}"
        except Exception as e: return f"[ERROR] {e}"

    def _shell_safe(cmd):
        if not any(cmd.strip().startswith(p) for p in _SAFE):
            return f"[BLOCKED] Use: {', '.join(_SAFE)}"
        try:
            r = subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=10)
            return (r.stdout+r.stderr).strip() or "(no output)"
        except Exception as e: return f"[ERROR] {e}"

    def run_tool(name, inp):
        if name=="run_python":  return _run_python(inp.get("code",""))
        if name=="read_file":   return _read_file(inp.get("path",""))
        if name=="write_file":  return _write_file(inp.get("path",""),inp.get("content",""))
        if name=="shell_safe":  return _shell_safe(inp.get("command",""))
        return f"[ERROR] Unknown tool: {name}"

    def _db():
        c = sqlite3.connect(str(DB_PATH))
        c.execute("CREATE TABLE IF NOT EXISTS ex(id INTEGER PRIMARY KEY,tid TEXT,human TEXT,ai TEXT,ts TEXT DEFAULT(datetime(\'now\')))")
        c.execute("CREATE INDEX IF NOT EXISTS i ON ex(tid,id DESC)")
        c.commit(); return c

    def load_history(tid, n=6):
        with _db() as c:
            rows = c.execute("SELECT human,ai FROM ex WHERE tid=? ORDER BY id DESC LIMIT ?",(tid,n)).fetchall()
        msgs = []
        for h,a in reversed(rows):
            msgs += [{"role":"user","content":h},{"role":"assistant","content":a}]
        return msgs

    def save(tid, human, ai):
        with _db() as c:
            c.execute("INSERT INTO ex(tid,human,ai) VALUES(?,?,?)",(tid,human[:2000],ai[:4000]))
            c.execute("DELETE FROM ex WHERE tid=? AND id NOT IN(SELECT id FROM ex WHERE tid=? ORDER BY id DESC LIMIT 200)",(tid,tid))
            c.commit()

    def run_agent(text, thread_id="default", channel="webchat"):
        key = os.environ.get("ANTHROPIC_API_KEY","")
        if not key: return "[FEHLER] ANTHROPIC_API_KEY nicht gesetzt.\\nexport ANTHROPIC_API_KEY=sk-ant-..."
        try: from anthropic import Anthropic
        except ImportError: return "[FEHLER] pip install anthropic --prefer-binary"
        client = Anthropic(api_key=key)
        sys_p = SYSTEM
        if channel in ("siri","voice"): sys_p += "\\nShort spoken answers. No markdown."
        msgs = load_history(thread_id) + [{"role":"user","content":text}]
        for _ in range(MAX_ROUNDS):
            resp = client.messages.create(model=MODEL,max_tokens=MAX_TOKENS,system=sys_p,tools=TOOLS,messages=msgs)
            msgs.append({"role":"assistant","content":resp.content})
            if resp.stop_reason != "tool_use": break
            results = []
            for b in resp.content:
                if b.type=="tool_use":
                    results.append({"type":"tool_result","tool_use_id":b.id,"content":run_tool(b.name,b.input)})
            msgs.append({"role":"user","content":results})
        text_out = "".join(b.text for b in resp.content if hasattr(b,"text")) or "(no response)"
        save(thread_id, text, text_out)
        return text_out

    def handle_message(payload):
        return run_agent(payload.get("text",""),payload.get("thread_id","default"),payload.get("channel","webchat"))

    if __name__ == "__main__":
        tid = "cli-" + datetime.now().strftime("%Y%m%d")
        print(f"Mini Agent | {MODEL} | DB: {DB_PATH}")
        print("Ctrl+C oder exit zum Beenden\\n")
        while True:
            try: t = input("Du: ").strip()
            except (KeyboardInterrupt,EOFError): print("\\nBye."); break
            if t.lower() in ("exit","quit","bye"): print("Bye."); break
            if not t: continue
            print("Agent:", run_agent(t, thread_id=tid))
            print()
''').lstrip()

with open(dest, "w", encoding="utf-8") as f:
    f.write(code)
print(f"  OK: {dest}")
WRITE_AGENT

ok "agent_mini.py eingebettet"

# ── API Key konfigurieren ──────────────────────────────────────────────────────
step "API Key konfigurieren"

touch "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"

if grep -q "ANTHROPIC_API_KEY" "$CONFIG_FILE" 2>/dev/null; then
    ok "ANTHROPIC_API_KEY bereits konfiguriert"
else
    printf "${YELLOW}Anthropic API Key eingeben (sk-ant-...): ${RESET}"
    if [ -t 0 ]; then
        stty -echo 2>/dev/null || true
        read -r API_KEY
        stty echo 2>/dev/null || true
        echo ""
        if [ -n "$API_KEY" ]; then
            echo "export ANTHROPIC_API_KEY=\"${API_KEY}\"" >> "$CONFIG_FILE"
            ok "API Key gespeichert in $CONFIG_FILE"
        else
            warn "Kein Key eingegeben — später in $CONFIG_FILE eintragen"
        fi
    else
        warn "Nicht-interaktiv — trage Key manuell in $CONFIG_FILE ein"
    fi
fi

# ── Shell-Profil aktualisieren ─────────────────────────────────────────────────
step "Shell-Profil aktualisieren"

# a-Shell verwendet ~/.profile
PROFILE="${HOME}/.profile"

add_to_profile() {
    LINE="$1"
    if ! grep -qF "$LINE" "$PROFILE" 2>/dev/null; then
        echo "$LINE" >> "$PROFILE"
        ok "  Hinzugefügt: $LINE"
    fi
}

add_to_profile "export PATH=\"\$HOME/Documents/bin:\$PATH\""
add_to_profile ". \"${CONFIG_FILE}\""
add_to_profile "alias lc='openclaw message send'"
add_to_profile "alias agent='python3 ${SKILL_DIR}/agent_mini.py'"

# Sofort laden
export PATH="${BIN_DIR}:${PATH}"
. "$CONFIG_FILE" 2>/dev/null || true

# ── Start-Skript ───────────────────────────────────────────────────────────────
START_SCRIPT="${INSTALL_DIR}/start.sh"
cat > "$START_SCRIPT" << START
#!/bin/sh
. "${CONFIG_FILE}"
export PATH="\${HOME}/Documents/bin:\${PATH}"

echo "LangChain Agent starten..."
echo "Zwei Optionen:"
echo ""
echo "1) OpenClaw + WebChat:"
echo "   openclaw gateway &"
echo "   openclaw agent --skill ${SKILL_DIR}"
echo ""
echo "2) Direkt in Terminal (a-Shell):"
echo "   python3 ${SKILL_DIR}/agent_mini.py"
echo ""
python3 "${SKILL_DIR}/agent_mini.py"
START
chmod +x "$START_SCRIPT"

# ── Test ──────────────────────────────────────────────────────────────────────
step "System testen"

"$PYTHON_CMD" - << 'PYTEST'
import sys, os

errors = []

try:
    from anthropic import Anthropic
except ImportError as e:
    errors.append(f'anthropic: {e}')

try:
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE t (x TEXT)')
    conn.close()
except Exception as e:
    errors.append(f'sqlite3: {e}')

if errors:
    print('FEHLER:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
else:
    print('  anthropic SDK: OK')
    print('  sqlite3:       OK')
    print('  Bereit.')
PYTEST

# ── Zusammenfassung ────────────────────────────────────────────────────────────
printf "\n${BOLD}${GREEN}╔══════════════════════════════════════╗"
printf "\n║  ✓ a-Shell Setup abgeschlossen       ║"
printf "\n╚══════════════════════════════════════╝${RESET}\n\n"

printf "${BOLD}Agent starten:${RESET}\n"
printf "  ${CYAN}python3 ${SKILL_DIR}/agent_mini.py${RESET}\n"
printf "  oder: ${CYAN}sh ${START_SCRIPT}${RESET}\n\n"

printf "${BOLD}Shell neu laden:${RESET}\n"
printf "  ${CYAN}source ${PROFILE}${RESET}  (in a-Shell: . ${PROFILE})\n\n"

printf "${BOLD}API Key prüfen:${RESET}\n"
printf "  ${CYAN}echo \$ANTHROPIC_API_KEY${RESET}\n\n"

exit 0
