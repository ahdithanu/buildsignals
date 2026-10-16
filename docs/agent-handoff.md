# Agent Handoff

This file is the durable handoff contract between humans and coding agents. It
is intentionally short and operational. Update it before switching agents,
ending a session, or opening a handoff PR.

## How To Resume

From the repository root:

```bash
python scripts/agent_context.py
git status --short --branch
```

Read `AGENTS.md`, then read the current sections below. Confirm the branch and
working tree before trusting any recorded status. If the recorded branch or
commit no longer exists, treat the record as historical and inspect `main`.

## Current Handoff

- Status: `ready`
- Objective: maintain a portable, evidence-backed Build Signals product.
- Branch: update this field at each handoff.
- Commit: update this field at each handoff.
- Last verified: update this field with an ISO-8601 timestamp.
- Owner/agent: update this field before handoff.

### Completed In The Current Slice

- Keep this list limited to work that is committed and verified.

### Next Action

- Start with the first unfinished item in the active task or PR.
- If no task is recorded, inspect `docs/enterprise_readiness.md` and the latest
  merged commits, then choose the smallest high-value slice.

### Files Changed

- List paths changed by the active task, or write `none` when the tree is clean.
- Separate intentional changes from unrelated pre-existing files.

### Verification

- Record the exact commands run and whether they passed.
- Include focused tests, lint/type checks, build checks, and CI/PR status when known.

### Open Risks And Decisions

- Record blockers, unresolved tradeoffs, required approvals, and known gaps.
- Never hide a skipped test, missing environment, or unverified deployment.

## Handoff Rules

- The working tree and git history outrank this document if they disagree.
- Do not put secrets, access tokens, customer records, or raw deployment logs here.
- Use commit SHAs and file paths, not conversational descriptions alone.
- If work is interrupted, record the last completed verification and the exact
  next command so another agent can resume without reconstructing the session.

