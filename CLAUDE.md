# CLAUDE.md — AI Assistant Instructions for benjaminh94-wq/.github

> This file is the authoritative, hardcoded guide for Claude Code (and any AI assistant)
> operating inside this repository. Read it in full before making any changes.

---

## Repository Identity

| Field | Value |
|---|---|
| Owner | `benjaminh94-wq` |
| Repo | `.github` |
| Purpose | GitHub **community health files** — default templates and policies that apply across all repos owned by this account/org |
| Primary tech | Markdown only — no build system, no package manager, no compiled code |
| Maintainer style | LangChain-aligned OSS governance (see CONTRIBUTING.md, SECURITY.md) |

---

## What Lives Here (Hardcoded File Map)

```
/
├── .gitignore            # Minimal — repo has no build artifacts
├── CODE_OF_CONDUCT.md    # Contributor Covenant-based code of conduct
├── CONTRIBUTING.md       # LangChain OSS contribution policy + PR requirements
├── SECURITY.md           # Vulnerability disclosure policy + bug bounty tiers
├── profile/
│   └── README.md         # GitHub organisation/user profile page (rendered on github.com)
└── CLAUDE.md             # THIS FILE — AI assistant instructions
```

Every file above is a **GitHub special file**. GitHub renders them automatically.
Do NOT rename, move, or delete them without an explicit user instruction.

---

## Absolute Rules (Never Break These)

1. **Markdown only.** Never add source code, binaries, lock files, or build configs.
2. **No new top-level files** unless GitHub documents them as a community health file
   (e.g. `SUPPORT.md`, `FUNDING.yml`, `CODEOWNERS`).
3. **Preserve all existing headings and section structure** unless the user explicitly
   asks for a structural change. Downstream tooling and humans rely on stable anchors.
4. **Never weaken security or conduct policies.** You may tighten scope, add clarity,
   or fix grammar — never remove disclosure requirements, safe-harbor clauses, or
   reporting channels.
5. **Branch discipline:** All changes go to the designated feature branch.
   Never push directly to `main` without explicit user approval.
6. **Commit messages** must follow conventional commits:
   `<type>(<scope>): <short description>`
   Valid types: `feat`, `fix`, `docs`, `chore`, `refactor`.
   Scope examples: `security`, `contributing`, `conduct`, `profile`.

---

## File-by-File Guidance

### CONTRIBUTING.md
- Governs **all** LangChain repos: `langchain`, `langgraph`, `deepagents`.
- Key policy: every PR **must** link to a maintainer-approved issue/discussion.
- Do NOT remove the anti-spam clause ("denial-of-service on human effort").
- Link to canonical docs: `https://docs.langchain.com/oss/python/contributing`.

### SECURITY.md
- Scope is explicitly LangChain-owned assets (LangSmith, high-usage repos, branded sites).
- Bug bounty tiers are **hardcoded dollar amounts** — do not modify without user instruction:
  - LangSmith: Low $200 / Moderate $500 / High $1 000+ / Critical $5 000–$10 000+
  - Open Source: High $500–$2 000 / Critical $2 000–$4 000
  - Branded Websites: High $150–$300 / Critical up to $300
- Contact address is `security@langchain.dev` — never change this.
- Payment methods: Wire transfer and Goody (`https://www.ongoody.com/plus`).

### CODE_OF_CONDUCT.md
- Based on Contributor Covenant. Keep version tag intact.
- Enforcement contact must remain valid and reachable.

### profile/README.md
- Rendered publicly on the GitHub profile page.
- Keep it concise, professional, and consistent with LangChain branding.
- No marketing fluff; no placeholder text.

---

## Branch Strategy

| Branch pattern | Purpose |
|---|---|
| `main` | Production — protected, requires PR |
| `claude/*` | AI-driven changes (this session: `claude/create-claude-md-jdEx9`) |
| `<author>/<slug>` | Human contributor branches (e.g. `mdrxy/contributing`) |
| `revert-*` | Auto-generated revert branches — investigate before deleting |

Active feature branches observed in this repo:
- `claude/add-claude-documentation-3TvEs` — previous Claude docs attempt (reverted)
- `mdrxy/llm-guidelines` — LLM-specific contribution guidelines (pending)
- `erick/dark-mode` — profile dark mode update
- `eugene/security_md` — security policy revision
- `jk/05feb/bb-policy` — bug bounty policy update

Coordinate with these branches if your changes overlap.

---

## Workflow Checklist

Before committing any change:

- [ ] Read the target file in full (not just the section you are editing)
- [ ] Confirm the change is within the file's stated scope
- [ ] Verify no bounty amounts, contact emails, or external URLs are altered unintentionally
- [ ] Run a Markdown lint pass mentally — check heading hierarchy, table alignment, link syntax
- [ ] Write a conventional commit message
- [ ] Push to the correct feature branch
- [ ] Open a PR against `main` and summarise the change in the PR body

---

## What Claude Must NOT Do

- Generate, guess, or alter any URLs (bounty links, doc links, contact links) unless
  the user provides the exact replacement URL.
- Add emojis, decorative elements, or filler text to policy documents.
- Introduce opinions about LangChain products, competitors, or security severity
  beyond what is already stated.
- Create `README.md` files in subdirectories unless explicitly requested.
- Run any shell commands — this is a pure-Markdown repo; no execution needed.
- Merge or close pull requests without explicit user confirmation.

---

## Quick Reference — GitHub Community Health Files

GitHub will surface these files automatically for any repo under this account
that lacks its own copy:

| File | Purpose |
|---|---|
| `CODE_OF_CONDUCT.md` | Contributor behaviour standards |
| `CONTRIBUTING.md` | How to contribute |
| `SECURITY.md` | Vulnerability reporting policy |
| `SUPPORT.md` | Where to get help (not yet present — can be added) |
| `FUNDING.yml` | Sponsorship buttons |
| `CODEOWNERS` | Auto-assign reviewers |
| `.github/ISSUE_TEMPLATE/` | Default issue templates |
| `.github/PULL_REQUEST_TEMPLATE.md` | Default PR template |

---

*This CLAUDE.md was generated on 2026-03-25 based on full codebase analysis.
Update it whenever the repository structure, policies, or maintainer contacts change.*
