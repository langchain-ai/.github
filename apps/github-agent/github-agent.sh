#!/bin/bash
# github-agent.sh — Autonomous iOS device agent v2
# - Polls cmd/pending for shell commands (every POLL_INTERVAL seconds)
# - Polls packages/ for new .deb files (every 60s) and auto-installs
# - Pure outbound GitHub API polling — no inbound SSH, Tailscale, or ports

mkdir -p /var/mobile/github-agent
printf '%d\n' $$ > /var/run/github-agent.pid

CONF="/var/mobile/github-agent/agent.conf"
LOG="/var/mobile/github-agent/agent.log"
CMD_SHA_FILE="/var/mobile/github-agent/last_cmd_sha"
PKG_SUM_FILE="/var/mobile/github-agent/last_pkg_sum"

[ -f "$CONF" ] && . "$CONF"
REPO="${REPO:-Benjaminh94-wq/.github}"
BRANCH="${BRANCH:-claude/create-claude-md-jdEx9}"
INTERVAL="${POLL_INTERVAL:-10}"
API="https://api.github.com/repos/$REPO/contents"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }

# Fetch raw file content
api_raw() {
  curl -sfL \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3.raw" \
    "$API/$1?ref=$BRANCH" 2>/dev/null
}

# Get file SHA (JSON endpoint, extract sha field)
api_sha() {
  curl -sf \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "$API/$1?ref=$BRANCH" 2>/dev/null \
    | grep -o '"sha":"[^"]*"' | head -1 | sed 's/"sha":"//;s/"//'
}

# Download binary file to path
api_dl() {
  curl -sfL \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3.raw" \
    "$API/$1?ref=$BRANCH" \
    -o "$2" 2>/dev/null
}

# Write result back to GitHub
api_put() {
  local path="$1" content="$2" sha="$3" msg="$4"
  local b64
  b64=$(printf '%s' "$content" | base64 | tr -d '\n')
  curl -sf -X PUT \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Content-Type: application/json" \
    "$API/$path" \
    -d "{\"message\":\"$msg\",\"content\":\"$b64\",\"sha\":\"$sha\",\"branch\":\"$BRANCH\"}" \
    >/dev/null 2>&1
}

# Get directory listing JSON
api_list() {
  curl -sf \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "$API/$1?ref=$BRANCH" 2>/dev/null
}

# ── Init ─────────────────────────────────────────────────────────────────────

LAST_CMD_SHA=$(cat "$CMD_SHA_FILE" 2>/dev/null || echo "")
LAST_PKG_CHECK=0

log "=== github-agent v2 started ==="
log "repo=$REPO  branch=$BRANCH  interval=${INTERVAL}s"

# ── Main loop ────────────────────────────────────────────────────────────────

while true; do
  NOW=$(date +%s)

  # ── COMMAND CHANNEL ──────────────────────────────────────────────────────
  CUR_SHA=$(api_sha "cmd/pending")

  if [ -n "$CUR_SHA" ] && [ "$CUR_SHA" != "$LAST_CMD_SHA" ]; then
    CMD=$(api_raw "cmd/pending" | sed '/^[[:space:]]*$/d;/^#/d')

    if [ -n "$CMD" ]; then
      log "EXEC ▶ $CMD"
      RESULT=$(eval "$CMD" 2>&1)
      EXIT=$?
      log "EXIT=$EXIT"

      RES_SHA=$(api_sha "cmd/result")
      BODY="$(date '+%Y-%m-%d %H:%M:%S') exit=$EXIT\n--- OUTPUT ---\n$RESULT"
      api_put "cmd/result" "$BODY" "$RES_SHA" "agent: result exit=$EXIT" \
        && log "Result written" \
        || log "WARN: failed to write result"
    fi

    printf '%s' "$CUR_SHA" > "$CMD_SHA_FILE"
    LAST_CMD_SHA="$CUR_SHA"
  fi

  # ── PACKAGE AUTO-INSTALL (every 60s) ─────────────────────────────────────
  if [ $((NOW - LAST_PKG_CHECK)) -ge 60 ]; then
    LAST_PKG_CHECK=$NOW

    PKG_JSON=$(api_list "packages")
    if [ -n "$PKG_JSON" ]; then
      # Fingerprint = cksum of all .deb SHA values combined
      NEW_SUM=$(printf '%s' "$PKG_JSON" | grep -o '"sha":"[^"]*"' | cksum | cut -d' ' -f1)
      OLD_SUM=$(cat "$PKG_SUM_FILE" 2>/dev/null || echo "")

      if [ "$NEW_SUM" != "$OLD_SUM" ]; then
        log "New packages detected — installing..."
        DID_INSTALL=0

        printf '%s' "$PKG_JSON" \
          | grep -o '"path":"[^"]*\.deb"' \
          | sed 's/"path":"//;s/"//' \
          | while IFS= read -r PKG_PATH; do
              PKG_NAME=$(basename "$PKG_PATH")
              TMP="/tmp/agent_$PKG_NAME"
              log "Downloading: $PKG_NAME"
              api_dl "$PKG_PATH" "$TMP"
              if [ -f "$TMP" ] && [ -s "$TMP" ]; then
                log "Installing: $PKG_NAME"
                dpkg -i "$TMP" 2>&1 | tee -a "$LOG"
                rm -f "$TMP"
              else
                log "WARN: download failed for $PKG_NAME"
              fi
            done

        printf '%s' "$NEW_SUM" > "$PKG_SUM_FILE"
        log "Scheduling SpringBoard restart in 5s..."
        nohup sh -c 'sleep 5; ldrestart 2>/dev/null || killall SpringBoard 2>/dev/null || true' \
          >/dev/null 2>&1 &
      fi
    fi
  fi

  sleep "$INTERVAL"
done
