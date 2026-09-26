# Ops log

Chronological record of operational drills, incidents, and infra changes.
Append new entries at the top.

---

## YYYY-MM-DD — [Title]

**Type:** restore drill / incident / deploy / config change
**Owner:**
**Outcome:** pass / fail / partial

### What we did

-

### Results

-

### Follow-ups

- [ ]

---

## Example — 2026-Q3 restore drill

**Type:** restore drill
**Owner:** @backend-oncall
**Outcome:** pass

### What we did

1. Restored latest Render Postgres snapshot to `dealsignal-db-drill-2026q3`.
2. Ran `SELECT count(*) FROM users, organizations, audit_log`.
3. Pointed staging API at restored DB; logged in and loaded `/deals`.

### Results

- Snapshot age: 4 hours
- Row counts matched production order-of-magnitude (staging seed differs)
- Smoke test green in 3 minutes

### Follow-ups

- [ ] Schedule Q4 drill before 2026-12-01
