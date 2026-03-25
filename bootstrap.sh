#!/bin/bash
# bootstrap.sh — One-time GitHub Agent setup for jailbroken iOS
#
# Run on your iPhone as root:
#   bash bootstrap.sh YOUR_GITHUB_PAT
#
# Creates:
#   /usr/local/bin/github-agent.sh        (polling daemon)
#   /var/mobile/github-agent/agent.conf   (config with PAT)
#   /Library/LaunchDaemons/com.claudepipeline.githubagent.plist
#
# After bootstrap:
#   - Device polls GitHub cmd/pending every 10s, executes commands as root
#   - Device polls packages/ every 60s, auto-installs new .deb files
#   - Zero inbound connections needed

PAT="${1:-$GITHUB_PAT}"
REPO="Benjaminh94-wq/.github"
BRANCH="claude/create-claude-md-jdEx9"
API="https://api.github.com/repos/$REPO/contents"

if [ -z "$PAT" ]; then
  echo "Usage: bash bootstrap.sh YOUR_GITHUB_PAT"
  echo ""
  echo "Create a PAT at: https://github.com/settings/tokens"
  echo "Required scope: repo  (or fine-grained: Contents read+write)"
  exit 1
fi

echo "=== GitHub Agent Bootstrap ==="
echo "repo:   $REPO"
echo "branch: $BRANCH"
echo ""

mkdir -p /var/mobile/github-agent
mkdir -p /usr/local/bin

# Download agent script
echo "→ Downloading github-agent.sh..."
curl -sfL \
  -H "Authorization: token $PAT" \
  -H "Accept: application/vnd.github.v3.raw" \
  "$API/apps/github-agent/github-agent.sh?ref=$BRANCH" \
  -o /usr/local/bin/github-agent.sh

if [ ! -s /usr/local/bin/github-agent.sh ]; then
  echo "ERROR: Download failed. Check PAT and network."
  echo "Debug: curl -v -H 'Authorization: token $PAT' '$API?ref=$BRANCH'"
  exit 1
fi
chmod +x /usr/local/bin/github-agent.sh
echo "[OK] Agent script: /usr/local/bin/github-agent.sh"

# Write agent config
cat > /var/mobile/github-agent/agent.conf << CONFEOF
GITHUB_TOKEN=$PAT
REPO=$REPO
BRANCH=$BRANCH
POLL_INTERVAL=10
CONFEOF
chmod 600 /var/mobile/github-agent/agent.conf
echo "[OK] Config: /var/mobile/github-agent/agent.conf"

# Write LaunchDaemon plist
cat > /Library/LaunchDaemons/com.claudepipeline.githubagent.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claudepipeline.githubagent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/usr/local/bin/github-agent.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/mobile/github-agent/agent.log</string>
    <key>StandardErrorPath</key>
    <string>/var/mobile/github-agent/agent.log</string>
    <key>UserName</key>
    <string>root</string>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
PLISTEOF
echo "[OK] LaunchDaemon plist written"

# Kill any existing agent
launchctl unload /Library/LaunchDaemons/com.claudepipeline.githubagent.plist 2>/dev/null || true
pkill -f github-agent.sh 2>/dev/null || true
sleep 1

# Load daemon
launchctl load /Library/LaunchDaemons/com.claudepipeline.githubagent.plist
sleep 2

if launchctl list | grep -q com.claudepipeline.githubagent; then
  echo "[OK] Daemon is running"
else
  echo "[WARN] Daemon may not be running — check:"
  echo "       launchctl list | grep githubagent"
  echo "       tail -20 /var/mobile/github-agent/agent.log"
fi

echo ""
echo "=== Bootstrap complete ==="
echo "Logs:   tail -f /var/mobile/github-agent/agent.log"
echo "Status: launchctl list | grep githubagent"
echo ""
echo "Device is now polling GitHub every 10s."
echo "Push code to apps/ → it compiles → .deb auto-installs on device."
