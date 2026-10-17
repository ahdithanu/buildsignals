# Working With Any Coding Agent

Open the repository root, not `src/`, `app/`, or a nested worktree. Durable
context lives in Git; agent chat history and cloud logins do not transfer.

## Entry Points

| Agent | Entry |
|---|---|
| Codex and agents that support AGENTS.md | `AGENTS.md` |
| Claude Code | `CLAUDE.md` imports `AGENTS.md` |
| Google Antigravity / Gemini | Root `AGENTS.md` and `GEMINI.md` point to the shared handoff |
| GitHub Copilot | `.github/copilot-instructions.md` points to the shared instructions |
| Any other agent | Give it the resume prompt below explicitly |

Claude imports follow [Claude Code's memory documentation](https://code.claude.com/docs/en/memory).
Antigravity discovers root AGENTS.md/GEMINI.md according to its
[rules documentation](https://www.antigravity.google/docs/rules/).
Editor versions and personal settings can affect discovery; confirm the agent
has actually read the shared files. These adapters have been checked as files,
not end-to-end in every external agent application.

## Resume Prompt

```text
Read AGENTS.md and docs/agent-handoff.md. Run python3 scripts/agent_status.py.
Inspect the actual branch, dirty files and recent commits before editing.
Summarize the next task and verified blockers, then continue the next unblocked
item within my current authorization. Preserve newer product work and tenant
isolation. Do not run paid model calls, production migrations/deployments or
source activation without applicable authorization. Update the shared handoff
with exact verification and next steps when you stop.
```

Use `python3 scripts/agent_status.py --check` to validate required handoff files.
It prints Git metadata, tool availability and file presence, never secret values.
It makes no network/model requests and does not fetch or modify Git state.

## Local Setup

Follow README.md and `.env.example`. Use Python 3.11+ and a project virtualenv.
Install `requirements.txt` plus the test tools used by `.github/workflows/ci.yml`.
Use `npm ci` to install the frontend's locked dependencies. Existing `venv/`
and `.venv/` directories may contain different versions; check before reusing one.
Do not copy another agent's credentials or overwrite an existing environment file.

For local API work, verify the target database before `alembic upgrade head` or
`python seed.py`, then run `uvicorn app.main:app --reload --port 8000`.
`npm run dev` runs the frontend with the proxy in `vite.config.ts`.
Use `AGENTS.md` for test commands; use `e2e/README.md` for browser testing.
There is no need to supply an OpenRouter key for ordinary unit tests.

## Task-Specific Context

| Work | Read first |
|---|---|
| Architecture and auth | README.md, `app/main.py`, `app/middleware/auth_context.py`, `docs/rbac.md` |
| OpenRouter and evaluation | `docs/openrouter-cleanup-integration.md`, README Model routing, `eval/`, `docs/ai-evaluation-platform.md` |
| Public demo | `docs/read-only-demo.md`, `docs/demo-readiness.md` |
| Acquisition / parcel workflow | `docs/acquisition-pilot-checklist.md`, `docs/parcel-reference-resolution.md`, `docs/nearby_parcel_discovery.md` |
| Coverage / ingestion | `docs/measured-coverage.md`, `docs/nationwide_source_coverage.md`, `app/services/ingestion/` |
| Deployment | `vercel.json`, `.github/workflows/deploy-aws.yml`, `docs/runbooks/deploy-aws.md`, `docs/runbooks/deploy.md` |
| Security / recovery | SECURITY.md, `docs/security-evidence-release.md`, `docs/backups.md` |

Read only the relevant sections. Long checklist entries can describe local
implementation, not the current production service. Recheck before making claims.

## Cloud Access and Releases

Configure GitHub, AWS, Vercel or Render access in the chosen agent's own environment.
No credentials are stored in these handoff files. A missing connector is not a
reason to invent a production result; continue local work and identify the gap.

As verified on 2026-10-16, Vercel serves the frontend and proxies to AWS App Runner.
The API deployment workflow is manual and includes migrations. Render blueprints
also exist but are not proof of the active backend. See the dated handoff before
deploying anything. Successful merge/preview checks do not prove API rollout.

## Leaving a Handoff

Update `docs/agent-handoff.md` at a meaningful task boundary using the template.
Keep it short, name exact commits/PRs and commands, and distinguish pending
approval from an engineering blocker. Do not turn a dated status into a standing
authorization for another agent. Commit the handoff with the authorized work;
push/PR/merge only within the user's applicable instructions.
