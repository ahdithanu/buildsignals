# BuildSignals / Claude Code

@AGENTS.md

Read `docs/agent-handoff.md` before taking the next task. Use
`docs/agent-onboarding.md` for setup. Update the shared handoff when stopping;
keep durable project instructions in AGENTS.md rather than duplicating them here.

Current context (2026-10-22): PRs #251–#254 are MERGED and `main` was deployed to
the API (see `docs/releases/2026-10-19-api-rollout.md`). The ERCOT
(`ercot_mis_xlsx`), Census BPS and Loudoun LOLA connectors are committed as
`technical_hold` candidates with canaries/ingestion DISABLED and NOT activated;
Development Velocity v0 + the cutoff-safe replay harness are merged (score
UNVALIDATED). Keep every source gate: a merged or deployed PR and offline fixture
checks are not live qualification, commercial-reuse clearance, or source-activation
authorization. The #249 worker reliability fixes reached 13/14 regional workers
on October 19; Texas still needs its in-budget canary/re-provision. The Columbus
2023–2025 local archive is retrospective, not known-then validation. Preserve
partial DBs and receipt timestamps. Read the latest October 22 corpus/production
audit and shared handoff for completed capture, verification and remaining gates.
Read the handoff and
`docs/source-qualification/` before continuing.
