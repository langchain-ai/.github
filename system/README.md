# Autonomous System

This directory contains the core infrastructure for the GitHub → localhost autonomous deployment pipeline.

## How It Works

```
User chat input
    ↓
Claude writes code → pushes to GitHub branch
    ↓
GitHub Actions CI validates the code
    ↓
Claude pulls & deploys to /home/user/workspace/
    ↓
Claude runs/verifies and reports back in chat
```

## Local Paths

| Path | Purpose |
|---|---|
| `/home/user/workspace/` | Root deployment workspace |
| `/home/user/workspace/apps/` | Deployed application instances |
| `/home/user/workspace/deploy/` | Deploy scripts + state |
| `/home/user/workspace/logs/` | Deploy + runtime logs |
| `/home/user/workspace/bin/claude-run` | CLI dispatcher |
| `/home/user/.github/` | Git repo (wired to GitHub via proxy) |

## CLI Commands

```sh
claude-run deploy          # Pull from GitHub and deploy all apps
claude-run status          # Show last deploy state
claude-run logs [N]        # Show last N log lines
claude-run app <name> run  # Run a deployed app
claude-run clean           # Wipe deployed apps
```

## Adding a New App

Create a directory under `apps/<your-app-name>/` in the repo with one of:
- `package.json` → Node.js app
- `requirements.txt` → Python app
- `entrypoint.sh` → Shell app

Push to GitHub. Claude will deploy it automatically.
