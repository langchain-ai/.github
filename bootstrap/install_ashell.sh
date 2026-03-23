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

# ── Skill-Dateien downloaden oder aus Repo kopieren ───────────────────────────
step "Skill-Dateien einrichten"

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
REPO_SKILL="${SCRIPT_DIR}/skills/langchain-dev"

if [ -d "$REPO_SKILL" ]; then
    # Aus lokalem Repo kopieren
    for f in agent_mini.py memory.py SKILL.md requirements.txt; do
        [ -f "${REPO_SKILL}/${f}" ] && cp "${REPO_SKILL}/${f}" "${SKILL_DIR}/${f}" && ok "  $f"
    done
else
    # Download via Python urllib (kein curl-URL-Problem)
    "$PYTHON_CMD" - << 'PYDOWNLOAD'
import urllib.request
import os

base = 'https://raw.githubusercontent.com'
repo = '/langchain-ai/.github/main/bootstrap/skills/langchain-dev'
files = ['agent_mini.py', 'memory.py', 'SKILL.md']

skill_dir = os.path.join(
    os.path.expanduser('~'), 'Documents',
    '.langchain-assistant', 'skills', 'langchain-dev'
)

for f in files:
    url = base + repo + '/' + f
    dest = os.path.join(skill_dir, f)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f'  OK: {f}')
    except Exception as e:
        print(f'  WARN: {f} — {e}')
PYDOWNLOAD
fi

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
