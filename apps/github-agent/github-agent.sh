#!/bin/bash
# github-agent.sh — Fully autonomous device agent
# Polls GitHub for commands, executes as root, writes results back
# No SSH inbound, no Tailscale, no port forwarding — works on any network

mkdir -p /var/mobile/github-agent
echo $$ > /var/run/github-agent.pid

CONF="/var/mobile/github-agent/agent.conf"
LOG="/var/mobile/github-agent/agent.log"
LAST_SHA_FILE="/var/mobile/github-agent/last_sha"

source "$CONF" 2>/dev/null
REPO="${REPO:-Benjaminh94-wq/.github}"
BRANCH="${BRANCH:-claude/create-claude-md-jdEx9}"
INTERVAL="${POLL_INTERVAL:-10}"
API="https://api.github.com/repos/$REPO/contents"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

api_get() {
  curl -s -H "Authorization: token $GITHUB_TOKEN" \
       -H "Accept: application/vnd.github.v3+json" \
       "$API/$1?ref=$BRANCH"
}

api_put() {
  curl -s -X PUT \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    -H "Content-Type: application/json" \
    "$API/$2" \
    -d "{\"message\":\"$3\",\"content\":\"$1\",\"sha\":\"$4\",\"branch\":\"$BRANCH\"}"
}

decode_content() {
  echo "$1" | python3 -c "
import sys,json,base64
d=json.load(sys.stdin)
c=d.get('content','').replace('\\n','')
try: print(base64.b64decode(c).decode('utf-8'))
except: pass
" 2>/dev/null
}

get_sha() {
  echo "$1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null
}

LAST_SHA=$(cat "$LAST_SHA_FILE" 2>/dev/null || echo "")
log "=== github-agent started ==="
log "repo=$REPO branch=$BRANCH poll=${INTERVAL}s"

while true; do
  RESPONSE=$(api_get "cmd/pending")
  SHA=$(get_sha "$RESPONSE")

  if [ -n "$SHA" ] && [ "$SHA" != "$LAST_SHA" ]; then
    CMD=$(decode_content "$RESPONSE")
    CMD_CLEAN=$(echo "$CMD" | grep -v '^# empty' | grep -v '^[[:space:]]*$')

    if [ -n "$CMD_CLEAN" ]; then
      log "EXEC: $CMD_CLEAN"
      RESULT=$(eval "$CMD_CLEAN" 2>&1)
      EXIT=$?
      log "EXIT=$EXIT RESULT=$RESULT"

      BODY="$(date '+%Y-%m-%d %H:%M:%S') exit=$EXIT\n$RESULT"
      B64=$(printf '%s' "$BODY" | base64 | tr -d '\n')
      RESULT_RESPONSE=$(api_get "cmd/result")
      RESULT_SHA=$(get_sha "$RESULT_RESPONSE")
      api_put "$B64" "cmd/result" "agent: result exit=$EXIT" "$RESULT_SHA" > /dev/null
      log "Result written to GitHub"
    fi

    echo "$SHA" > "$LAST_SHA_FILE"
    LAST_SHA="$SHA"
  fi

  sleep "$INTERVAL"
done
