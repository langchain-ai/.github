# iOS Autonomous Pipeline

## Full Chain

```
Chat Input (you type here)
    ↓
Claude writes code → apps/<name>/
    ↓
git commit + push → GitHub branch
    ↓
GitHub Actions (macos-latest) — Theos compile → .deb
    ↓        OR
Local Linux container — Theos cross-compile → .deb
    ↓
SSH push → dpkg -i on jailbroken device
    ↓
ldrestart / killall SpringBoard
    ↓
Running on iOS kernel
    ↓
Result reported back in chat
```

## CLI Commands (run on local container)

```sh
# First time setup
claude-ios setup <DEVICE_IP> [PORT] [USER] [PASS]

# Full pipeline for an app
claude-ios pipeline <app-name>

# Execute anything on device as root
claude-ios exec "ls /var/jb/usr/lib/"
claude-ios exec "cat /etc/fstab"
claude-ios exec "killall SpringBoard"

# File operations
claude-ios edit /etc/hosts
claude-ios write /etc/hosts /tmp/my_hosts

# System info
claude-ios sysinfo
claude-ios status
```

## Adding a New App (from chat)

Just tell Claude what you want. Claude will:
1. Create `apps/<name>/Makefile` + source files
2. Create `apps/<name>/control` (package metadata)
3. Push to GitHub
4. Compile + package as `.deb`
5. SSH deploy to your device
6. Report result

## Local Toolchain

| Tool | Path | Purpose |
|---|---|---|
| `claude-ios` | `/home/user/workspace/bin/claude-ios` | Master pipeline runner |
| `ios-bridge` | `/home/user/workspace/bin/ios-bridge` | SSH/SCP bridge to device |
| `ios-compile.sh` | `/home/user/workspace/deploy/ios-compile.sh` | Theos compiler wrapper |
| `deploy.sh` | `/home/user/workspace/deploy/deploy.sh` | GitHub pull + local sync |
| `Theos` | `/opt/theos` | Build system |
| iOS SDKs | `/opt/theos/sdks/` | iPhoneOS 9.3 — 16.5 |
| `ldid` | `/usr/local/bin/ldid` | iOS binary fake-signing |
| `sshpass` | `/bin/sshpass` | Non-interactive SSH auth |

## Device Config

Stored at: `/home/user/workspace/deploy/device.conf`

```sh
DEVICE_IP=192.168.x.x
DEVICE_PORT=22
DEVICE_USER=root
DEVICE_PASS=alpine
IOS_VERSION=16.x
ARCH=arm64
```
