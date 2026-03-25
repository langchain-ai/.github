# Autonomous Workflow Specification

## Session Contract

| Role | Responsibility |
|---|---|
| **You (User)** | Give input in chat |
| **Claude** | Build, commit, push, deploy, run, report |
| **GitHub** | Source of truth, version history, CI validation |
| **Local container** | Runtime environment (`/home/user/workspace/`) |

## Deployment Pipeline (Step by Step)

1. **User input** → Claude receives task in chat
2. **Code generation** → Claude writes files locally to `/home/user/.github/` or creates new app in `apps/`
3. **GitHub push** → Claude commits + pushes to branch `claude/create-claude-md-jdEx9`
4. **CI validation** → GitHub Actions runs `.github/workflows/ci.yml`
5. **Local deploy** → Claude runs `deploy.sh` — pulls from GitHub, copies to `apps/`, installs deps
6. **Run & verify** → Claude executes the app or service and reports output
7. **Report** → Claude summarises result in chat

## Hardcoded Environment Variables

| Variable | Value |
|---|---|
| `WORKSPACE` | `/home/user/workspace` |
| `REPO_DIR` | `/home/user/.github` |
| `DEPLOY_BRANCH` | `claude/create-claude-md-jdEx9` |
| `GIT_REMOTE` | `http://local_proxy@127.0.0.1:42557/git/Benjaminh94-wq/.github` |
| `PLATFORM` | `linux / Alpine ash` |
| `JAVA_HOME` | `/usr/lib/jvm/java-21-openjdk-amd64` |

## What Claude Can Deploy Here

- Shell scripts (`.sh`)
- Node.js applications (requires `package.json`)
- Python scripts (requires `requirements.txt` or standalone `.py`)
- Static files / configs
- Any tool installable via `apk add` or `pip install`

## Security Boundaries

- No Anthropic infra tokens are used or exposed
- No external ports are opened
- Deployment is contained to `/home/user/workspace/`
- GitHub auth goes through the existing local proxy (`127.0.0.1:42557`)
