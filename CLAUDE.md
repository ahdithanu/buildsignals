# BuildSignals / Claude Code

@AGENTS.md

Read `docs/agent-handoff.md` before taking the next task. Use
`docs/agent-onboarding.md` for setup. Update the shared handoff when stopping;
keep durable project instructions in AGENTS.md rather than duplicating them here.

Current state (2026-10-19): PRs #251–#254 are MERGED and `main` is deployed to
the API (see `docs/releases/2026-10-19-api-rollout.md`). The ERCOT
(`ercot_mis_xlsx`), Census BPS and Loudoun LOLA connectors are committed as
`technical_hold` candidates with canaries/ingestion DISABLED and NOT activated;
Development Velocity v0 + the cutoff-safe replay harness are merged (score
UNVALIDATED). Keep every source gate: a merged or deployed PR and offline fixture
checks are not live qualification, commercial-reuse clearance, or source-activation
authorization. The #249 worker reliability fixes still need a gated regional
re-provision to reach the live schedules. Read the handoff and
`docs/source-qualification/` before continuing.
