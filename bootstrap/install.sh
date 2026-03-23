#!/usr/bin/env sh
# =============================================================================
# LangChain AI Assistant — One-Click Bootstrapper
# Powered by: OpenClaw + LangGraph + Claude API
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/langchain-ai/.github/main/bootstrap/install.sh | sh
#
# Or clone first (recommended for air-gapped / offline):
#   git clone https://github.com/langchain-ai/.github && cd .github && sh bootstrap/install.sh
#
# Supported environments:
#   - macOS (Intel + Apple Silicon)
#   - Linux (x86_64, arm64)
#   - a-Shell on iOS/iPadOS  ← primary mobile target
#   - Termux on Android
#
# This script is IDEMPOTENT — safe to run multiple times.
# =============================================================================

set -e

# ── Color output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { printf "${BLUE}[langchain]${RESET} %s\n" "$*"; }
ok()   { printf "${GREEN}[✓]${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}[!]${RESET} %s\n" "$*"; }
err()  { printf "${RED}[✗]${RESET} %s\n" "$*" >&2; exit 1; }
step() { printf "\n${BOLD}${CYAN}━━━ %s ━━━${RESET}\n" "$*"; }

# ── Banner ────────────────────────────────────────────────────────────────────
printf "\n${BOLD}${CYAN}"
printf "  ██╗      █████╗ ███╗   ██╗ ██████╗  ██████╗██╗  ██╗ █████╗ ██╗███╗   ██╗\n"
printf "  ██║     ██╔══██╗████╗  ██║██╔════╝ ██╔════╝██║  ██║██╔══██╗██║████╗  ██║\n"
printf "  ██║     ███████║██╔██╗ ██║██║  ███╗██║     ███████║███████║██║██╔██╗ ██║\n"
printf "  ██║     ██╔══██║██║╚██╗██║██║   ██║██║     ██╔══██║██╔══██║██║██║╚██╗██║\n"
printf "  ███████╗██║  ██║██║ ╚████║╚██████╔╝╚██████╗██║  ██║██║  ██║██║██║ ╚████║\n"
printf "  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝\n"
printf "${RESET}"
printf "  ${BOLD}AI System Assistant${RESET} — OpenClaw + LangGraph + Claude\n"
printf "  One-Click Bootstrap for macOS / Linux / a-Shell (iOS)\n\n"

# ── Detect environment ────────────────────────────────────────────────────────
step "Detecting environment"

OS="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
ASHELL=false
TERMUX=false

if [ -n "$A_SHELL_SESSION" ] || [ -d "/private/var/mobile" ]; then
    ASHELL=true
    log "Detected: a-Shell (iOS/iPadOS)"
elif [ -d "/data/data/com.termux" ]; then
    TERMUX=true
    log "Detected: Termux (Android)"
elif [ "$OS" = "Darwin" ]; then
    log "Detected: macOS ($ARCH)"
elif [ "$OS" = "Linux" ]; then
    log "Detected: Linux ($ARCH)"
else
    warn "Unknown environment — attempting generic install"
fi

INSTALL_DIR="${HOME}/.langchain-assistant"
SKILL_DIR="${INSTALL_DIR}/skills/langchain-dev"
CONFIG_FILE="${INSTALL_DIR}/config.env"

mkdir -p "$INSTALL_DIR" "$SKILL_DIR"
ok "Install directory: $INSTALL_DIR"

# ── a-Shell: git wrapper (lg2 alias) ──────────────────────────────────────────
if $ASHELL; then
    step "Setting up git wrapper for a-Shell (lg2)"
    BIN_DIR="${HOME}/Documents/bin"

    # Remove if exists as file (not directory)
    if [ -e "$BIN_DIR" ] && [ ! -d "$BIN_DIR" ]; then
        rm -f "$BIN_DIR"
        ok "Removed stale $BIN_DIR file"
    fi

    mkdir -p "$BIN_DIR"

    if command -v lg2 >/dev/null 2>&1; then
        {
            echo '#!/bin/sh'
            echo 'lg2 "$@"'
        } > "${BIN_DIR}/git"
        chmod +x "${BIN_DIR}/git"
        ok "git → lg2 wrapper created at ${BIN_DIR}/git"

        # PATH sofort aktiv
        case ":${PATH}:" in
            *":${BIN_DIR}:"*) ;;
            *) export PATH="${BIN_DIR}:${PATH}" ;;
        esac

        # Dauerhaft in .profile eintragen
        PROFILE="${HOME}/.profile"
        PATH_LINE="export PATH=\"\$HOME/Documents/bin:\$PATH\""
        if ! grep -qF 'Documents/bin' "$PROFILE" 2>/dev/null; then
            echo "$PATH_LINE" >> "$PROFILE"
            ok "PATH updated in $PROFILE"
        fi
    else
        warn "lg2 not found — run 'pkg install git' in a-Shell to get lg2"
    fi
fi

# ── Check/install Node.js ─────────────────────────────────────────────────────
step "Checking Node.js (required for OpenClaw)"

check_node_version() {
    if command -v node >/dev/null 2>&1; then
        NODE_VER="$(node -e 'process.stdout.write(process.versions.node)')"
        MAJOR="$(echo "$NODE_VER" | cut -d. -f1)"
        if [ "$MAJOR" -ge 22 ]; then
            ok "Node.js $NODE_VER ✓"
            return 0
        else
            warn "Node.js $NODE_VER found but need 22+ (OpenClaw requirement)"
            return 1
        fi
    fi
    return 1
}

if ! check_node_version; then
    if $ASHELL; then
        log "Installing Node.js via a-Shell pkg..."
        pkg install node || err "Failed: run 'pkg install node' manually in a-Shell"
        check_node_version || err "Node installation failed"
    elif $TERMUX; then
        log "Installing Node.js via Termux pkg..."
        pkg install nodejs || err "Failed to install Node.js"
        check_node_version || err "Node installation failed"
    elif [ "$OS" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            log "Installing Node.js via Homebrew..."
            brew install node@22
        else
            err "Node.js 22+ required. Install via: https://nodejs.org or Homebrew"
        fi
    else
        err "Node.js 22+ required. Install via your package manager or https://nodejs.org"
    fi
fi

# ── Check/install Python ──────────────────────────────────────────────────────
step "Checking Python 3.11+"

check_python() {
    for py in python3 python3.12 python3.11; do
        if command -v "$py" >/dev/null 2>&1; then
            VER="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
            MAJOR="$(echo "$VER" | cut -d. -f1)"
            MINOR="$(echo "$VER" | cut -d. -f2)"
            if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
                PYTHON_CMD="$py"
                ok "Python $VER ($py) ✓"
                return 0
            fi
        fi
    done
    return 1
}

if ! check_python; then
    if $ASHELL; then
        log "Installing Python via a-Shell pkg..."
        pkg install python || err "Run 'pkg install python' manually"
        check_python || err "Python installation failed"
    elif $TERMUX; then
        pkg install python
        check_python || err "Python installation failed"
    else
        err "Python 3.11+ required. Install from https://python.org"
    fi
fi

# ── Install OpenClaw ──────────────────────────────────────────────────────────
step "Installing OpenClaw"

if command -v openclaw >/dev/null 2>&1; then
    CLAW_VER="$(openclaw --version 2>/dev/null || echo 'installed')"
    ok "OpenClaw $CLAW_VER already installed"
    log "Updating to latest stable..."
    openclaw update --channel stable 2>/dev/null || warn "Auto-update failed — continuing with installed version"
else
    log "Installing OpenClaw via npm..."
    npm install -g openclaw@latest || err "OpenClaw install failed. Check npm permissions."
    ok "OpenClaw installed"
fi

# ── Install Python dependencies ───────────────────────────────────────────────
step "Installing Python AI stack"

# Core: LangChain + LangGraph + Anthropic
log "Installing: anthropic, langgraph, langchain..."
"$PYTHON_CMD" -m pip install --quiet --upgrade \
    "anthropic>=0.40.0" \
    "langgraph>=0.2.0" \
    "langchain-anthropic>=0.3.0" \
    "langchain-community>=0.3.0" \
    "langchain-core>=0.3.0" \
    "sqlalchemy>=2.0.0" \
    "aiosqlite>=0.20.0" \
    "httpx>=0.27.0" \
    || err "pip install failed — check network and try again"
ok "Python AI stack installed"

# coding/ skill extra: hypothesis for fuzzing-based refactor verification
log "Installing coding skill extras: hypothesis..."
"$PYTHON_CMD" -m pip install --quiet --upgrade "hypothesis>=6.100.0" \
    && ok "hypothesis installed" \
    || warn "hypothesis install failed — refactor_verifier will run in basic mode"

# memory-mesh optional: semantic embeddings (heavy, skip on low-memory devices)
if [ "$ASHELL" = "false" ] && [ "$TERMUX" = "false" ]; then
    log "Installing memory-mesh optional: sentence-transformers (may take a while)..."
    "$PYTHON_CMD" -m pip install --quiet "sentence-transformers>=3.0.0" "numpy>=1.26.0" \
        && ok "sentence-transformers installed — ACMM semantic search active" \
        || warn "sentence-transformers skipped — ACMM will use keyword fallback"
else
    log "Skipping sentence-transformers on mobile (too large) — ACMM uses keyword mode"
fi

# ── Deploy All Skills ─────────────────────────────────────────────────────────
step "Deploying OpenClaw skills"

# Detect if running from cloned repo or piped via curl
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
REPO_SKILLS_DIR="${SCRIPT_DIR}/skills"
BASE_URL="https://raw.githubusercontent.com/langchain-ai/.github/main/bootstrap/skills"

# Skills to deploy: name → install dir
SKILLS="langchain-dev ashell coding memory-mesh"

for skill in $SKILLS; do
    TARGET_DIR="${INSTALL_DIR}/skills/${skill}"
    mkdir -p "$TARGET_DIR"

    if [ -d "${REPO_SKILLS_DIR}/${skill}" ]; then
        # Running from repo clone — copy directly (excludes __pycache__)
        rsync -a --exclude='__pycache__' --exclude='*.pyc' \
            "${REPO_SKILLS_DIR}/${skill}/" "$TARGET_DIR/" 2>/dev/null \
        || cp -r "${REPO_SKILLS_DIR}/${skill}/." "$TARGET_DIR/"
        ok "Skill '${skill}' deployed from local repo"
    else
        # Piped install — download SKILL.md to check what files exist
        log "Downloading skill '${skill}'..."
        # Download known files per skill
        case "$skill" in
            langchain-dev)
                files="SKILL.md agent.py memory.py requirements.txt"
                ;;
            coding)
                files="SKILL.md causal_diff.py invariant_miner.py revert_advisor.py smell_memory.py refactor_verifier.py chat_modes.py requirements.txt"
                ;;
            ashell)
                files="SKILL.md tts.py url_orchestrator.py icloud_handoff.py clipboard_daemon.py sensor_briefing.py"
                ;;
            memory-mesh)
                files="SKILL.md embedder.py compressor.py scheduler.py requirements.txt"
                ;;
        esac
        skill_ok=true
        for file in $files; do
            curl -fsSL "${BASE_URL}/${skill}/${file}" -o "${TARGET_DIR}/${file}" 2>/dev/null \
                && ok "  ${skill}/${file}" \
                || { warn "  Could not download ${skill}/${file}"; skill_ok=false; }
        done
        $skill_ok && ok "Skill '${skill}' downloaded" || warn "Skill '${skill}' partially downloaded"
    fi
done

# Backwards-compat symlink: SKILL_DIR still points to langchain-dev
SKILL_DIR="${INSTALL_DIR}/skills/langchain-dev"

# ── Configure secrets ─────────────────────────────────────────────────────────
step "Configuring API keys"

if [ -f "$CONFIG_FILE" ]; then
    ok "Config file already exists at $CONFIG_FILE"
    # shellcheck source=/dev/null
    . "$CONFIG_FILE"
fi

configure_key() {
    VAR_NAME="$1"
    PROMPT_MSG="$2"
    CURRENT_VAL="$(eval echo "\$$VAR_NAME")"

    if [ -n "$CURRENT_VAL" ]; then
        ok "$VAR_NAME already set"
        return 0
    fi

    printf "${YELLOW}%s: ${RESET}" "$PROMPT_MSG"
    # Read without echo for secrets
    if [ -t 0 ]; then
        stty -echo 2>/dev/null
        read -r INPUT
        stty echo 2>/dev/null
        echo ""
    else
        warn "Non-interactive mode — set $VAR_NAME in $CONFIG_FILE manually"
        return 0
    fi

    if [ -n "$INPUT" ]; then
        echo "export ${VAR_NAME}=\"${INPUT}\"" >> "$CONFIG_FILE"
        eval "export ${VAR_NAME}=\"${INPUT}\""
        ok "$VAR_NAME saved"
    else
        warn "$VAR_NAME skipped — set it in $CONFIG_FILE before starting"
    fi
}

touch "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"  # Secrets: owner-read-only

configure_key "ANTHROPIC_API_KEY" "Anthropic API Key (sk-ant-...)"
configure_key "LANGSMITH_API_KEY" "LangSmith API Key (optional, press Enter to skip)"

# ── Shell profile integration ─────────────────────────────────────────────────
step "Configuring shell environment"

SHELL_PROFILE=""
if [ -f "${HOME}/.zshrc" ]; then
    SHELL_PROFILE="${HOME}/.zshrc"
elif [ -f "${HOME}/.bashrc" ]; then
    SHELL_PROFILE="${HOME}/.bashrc"
elif [ -f "${HOME}/.profile" ]; then
    SHELL_PROFILE="${HOME}/.profile"
fi

SOURCE_LINE=". \"${CONFIG_FILE}\""
ALIAS_LINE="alias lc='openclaw message send'"

if [ -n "$SHELL_PROFILE" ]; then
    if ! grep -qF "$CONFIG_FILE" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# LangChain AI Assistant" >> "$SHELL_PROFILE"
        echo "$SOURCE_LINE" >> "$SHELL_PROFILE"
        echo "$ALIAS_LINE" >> "$SHELL_PROFILE"
        ok "Added to $SHELL_PROFILE"
    else
        ok "Shell profile already configured"
    fi
fi

# ── iOS Shortcuts integration (a-Shell specific) ──────────────────────────────
if $ASHELL; then
    step "Setting up iOS Shortcuts integration"

    SHORTCUT_SCRIPT="${INSTALL_DIR}/siri-trigger.sh"
    cat > "$SHORTCUT_SCRIPT" << SHORTCUT
#!/bin/sh
# iOS Shortcut / Siri trigger for LangChain AI Assistant
# Add to iOS Shortcuts as "Run Script over SSH" or "a-Shell" action
. "${CONFIG_FILE}"
openclaw message send "\$1"
SHORTCUT
    chmod +x "$SHORTCUT_SCRIPT"

    ok "Shortcut script: $SHORTCUT_SCRIPT"
    log ""
    log "To add Siri integration:"
    log "  1. Open iOS Shortcuts app"
    log "  2. New Shortcut → Add Action → 'a-Shell'"
    log "  3. Command: sh ${SHORTCUT_SCRIPT} \"[Shortcut Input]\""
    log "  4. Add to Siri with phrase: 'Ask LangChain'"
fi

# ── OpenClaw onboard ──────────────────────────────────────────────────────────
step "Running OpenClaw first-time setup"

if [ -f "${HOME}/.openclaw/config.json" ]; then
    ok "OpenClaw already configured"
else
    log "Starting OpenClaw onboarding..."
    if [ -t 0 ] && [ -t 1 ]; then
        openclaw onboard || warn "Onboarding interrupted — run 'openclaw onboard' manually"
    else
        warn "Non-interactive mode — run 'openclaw onboard' manually to complete setup"
    fi
fi

# ── Launch script ─────────────────────────────────────────────────────────────
LAUNCH_SCRIPT="${INSTALL_DIR}/start.sh"
cat > "$LAUNCH_SCRIPT" << LAUNCH
#!/bin/sh
# LangChain AI Assistant — Launcher
# Run this to start the full system

set -e
. "${CONFIG_FILE}"

echo "Starting LangChain AI Assistant..."
echo "  OpenClaw Gateway: ws://127.0.0.1:18789"
echo "  WebChat UI:       http://127.0.0.1:18788"
echo ""

# Start OpenClaw gateway in background
openclaw gateway &
GATEWAY_PID=\$!

# Wait for gateway to be ready — health-check loop (max 15s)
READY=false
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if openclaw doctor --quiet 2>/dev/null; then
        READY=true
        break
    fi
    sleep 1
done
if [ "\$READY" = "false" ]; then
    echo "Warning: gateway health-check timed out — agent may start before gateway is ready"
fi

# Start agent with langchain-dev skill
openclaw agent --skill "${INSTALL_DIR}/skills/langchain-dev" &
AGENT_PID=\$!

echo "System running. PIDs: gateway=\$GATEWAY_PID agent=\$AGENT_PID"
echo "Open http://127.0.0.1:18788 in your browser for WebChat UI"
echo ""
echo "Press Ctrl+C to stop"

# Trap for clean shutdown
trap 'kill \$GATEWAY_PID \$AGENT_PID 2>/dev/null; echo "Stopped."; exit 0' INT TERM

wait
LAUNCH
chmod +x "$LAUNCH_SCRIPT"

# ── Summary ───────────────────────────────────────────────────────────────────
printf "\n${BOLD}${GREEN}"
printf "╔══════════════════════════════════════════════════════════════╗\n"
printf "║           ✓ INSTALLATION COMPLETE                           ║\n"
printf "╚══════════════════════════════════════════════════════════════╝\n"
printf "${RESET}\n"

log "Install directory:  ${INSTALL_DIR}"
log "Skill directory:    ${SKILL_DIR}"
log "Config file:        ${CONFIG_FILE}"
log "Launch script:      ${LAUNCH_SCRIPT}"
printf "\n"
printf "${BOLD}Quick Start:${RESET}\n"
printf "  ${CYAN}sh ${LAUNCH_SCRIPT}${RESET}        # Start full system\n"
printf "  ${CYAN}openclaw gateway${RESET}            # Gateway only\n"
printf "  ${CYAN}lc \"Hello!\"${RESET}                # Send message (after shell reload)\n"
printf "\n"

if $ASHELL; then
    printf "${BOLD}iOS Siri Setup:${RESET}\n"
    printf "  Shortcuts app → New → a-Shell action\n"
    printf "  Command: sh ${SHORTCUT_SCRIPT} \"[Input]\"\n"
    printf "  Siri phrase: 'Ask LangChain'\n\n"
    printf "${BOLD}a-Shell Tipp — Re-Install ohne URL-Tipp-Problem:${RESET}\n"
    printf "  python3 -c \"import urllib.request as u; u.urlretrieve('https://' + \\\n"
    printf "    'raw.githubusercontent.com/langchain-ai/.github/main/bootstrap/install.sh',\\\n"
    printf "    'install.sh'); print('OK')\"\n"
    printf "  sh install.sh\n\n"
fi

printf "${BOLD}Next steps:${RESET}\n"
printf "  1. ${YELLOW}Reload shell:${RESET} source ${SHELL_PROFILE:-~/.profile}\n"
printf "  2. ${YELLOW}Start system:${RESET} sh ${LAUNCH_SCRIPT}\n"
printf "  3. ${YELLOW}Open WebChat:${RESET} http://127.0.0.1:18788\n\n"

exit 0
