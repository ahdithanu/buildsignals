# Postmortem — [INCIDENT TITLE]

**Date:** YYYY-MM-DD
**Severity:** Sev-1 / Sev-2 / Sev-3
**Authors:**
**Status:** Draft / Final

---

## Summary

One paragraph: what broke, who was affected, how long, how it was fixed.

---

## Impact

| Metric | Value |
|--------|-------|
| Duration | HH:MM UTC → HH:MM UTC (X min) |
| Users affected | all / subset / none (internal) |
| Data loss | yes/no — details |
| SLO budget consumed | ~X% of monthly error budget |

---

## Timeline (UTC)

| Time | Event |
|------|-------|
| HH:MM | Alert fired / user report |
| HH:MM | On-call acknowledged |
| HH:MM | Root cause identified |
| HH:MM | Mitigation deployed |
| HH:MM | Resolved — smoke test green |
| HH:MM | Status page updated "resolved" |

---

## Root cause

Technical explanation. Include the specific change, config, or dependency that failed.

---

## Detection

- How was it detected? (Sentry, uptime probe, user report)
- Time to detect: X minutes
- What would detect it faster next time?

---

## Resolution

Steps taken to restore service. Include rollback commit/ deploy ID if applicable.

---

## What went well

-

---

## What went poorly

-

---

## Action items

| Action | Owner | Due | Ticket |
|--------|-------|-----|--------|
| | | | |

Every Sev-1/Sev-2 postmortem must have at least one action item with an owner and ticket.

---

## Lessons learned

-
