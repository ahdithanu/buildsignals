# Incident response runbook — DealSignal

What to do when production is broken. Optimized for the 2am case: skim the
severity table, find your symptom, act. Depth is in the linked runbooks.

> **Before first production incident:** replace the `[CONFIGURE]` placeholders
> in §On-call with your org's rotation, paging tool, and status page. Until
> then, treat `#dealsignal-incidents` as the paging channel.

---

## 1. Declare severity

Pick the highest row that matches. When in doubt, round up — it's cheaper to
stand down a Sev-1 than to under-respond.

| Sev | Definition | Examples | Response |
|-----|-----------|----------|----------|
| **Sev-1** | Broad outage or data exposure | API down, auth broken for all users, cross-tenant data leak, DB unreachable | Page on-call immediately. All-hands. Status page updated. |
| **Sev-2** | Major degradation, workaround exists | One core flow broken (e.g. deal creation), elevated 5xx, slow but up | Page on-call. Fix within hours. |
| **Sev-3** | Minor / cosmetic | Single non-critical endpoint, UI glitch, one tenant affected | Ticket. Next business day. |

**Security incidents** (suspected breach, leaked secret, active exploitation)
are **Sev-1 regardless of user impact** — see §5.

---

## 2. First 5 minutes

1. **Acknowledge** the page so it stops escalating and the team knows it's owned.
2. **Post in `#dealsignal-incidents`** *(Slack)*: what you see, severity, "investigating."
3. **Check the obvious signals** before theorizing:
   - Sentry — new error spike? What's the exception + release tag?
   - `GET /health/deep` — is the DB reachable? (`/health` alone only proves the process is up.)
   - Render dashboard — did a deploy just land? Is the service crash-looping?
   - Render Postgres — CPU / disk / connection alarms?
4. **Decide: roll back or fix forward.** Use the matrix in
   [deploy.md](deploy.md#rollback). Default to rollback for a bad deploy; **do
   NOT roll back the app after a bad migration** — the schema won't roll back
   with it. Page whoever owns the migration.

---

## 3. Triage by symptom

| Symptom | Most likely | First check |
|---|---|---|
| Every request 5xx right after a deploy | Missing env var → boot crash | Render build log for `KeyError` / config guard error |
| Every request 5xx, no deploy | DB unreachable | `/health/deep`, Postgres alarms |
| Auth broken for everyone | Signing-key rotation, `token_version` bug, or bad auth deploy | Did `SECRET_KEY` change? Recent auth PR? — treat as Sev-1 |
| Elevated but not total 5xx | One endpoint / slow query | Sentry grouping, slow-query spans |
| Frontend white screen | Static build or bad `VITE_*` env | Render static-site build log; frontend Sentry |
| 429s spiking | Rate limit too tight or an attack | `GLOBAL_RATE_LIMIT`; is it one IP or many? |
| Deploy stuck / never cuts over | `preDeployCommand` (migration) failed | Render pre-deploy logs |

---

## 4. Communication

- **Internal:** `#dealsignal-incidents`. Post on declare, on status change, and
  on resolve. Timestamp updates so the postmortem timeline writes itself.
- **External (Sev-1/2):** update the status page at **[CONFIGURE: status page URL]**
  (e.g. `https://status.dealsignal.com` via Instatus, Statuspage, or Better Uptime).
  Say what's affected and that you're on it; don't speculate on cause or ETA.
- **Cadence:** Sev-1 → update at least every 30 min even if it's "still
  investigating." Silence reads as "nobody's handling it."

---

## 5. Security incidents

Suspected breach, a secret leaked in a commit/screenshot/log, or active
exploitation:

1. **Rotate first, investigate second.** Follow the leaked-secret playbook in
   [secrets.md](../secrets.md#leaked-secret-playbook) — don't wait to confirm
   the leak was seen.
2. **Preserve evidence** — capture logs and Sentry events before they age out
   of retention.
3. **Assess blast radius** — what could the exposed credential reach? Check
   `pg_stat_activity` for unexpected clients; review recent `audit_log` rows.
4. **File an incident note even if blast radius is empty.** The paper trail is
   the point, and it matters for any future compliance conversation.

---

## 6. Resolve & postmortem

**Resolve:** confirm the fix with the smoke test in
[deploy.md](deploy.md#smoke-test), post "resolved" internally and on the status
page, stand down the page.

**Postmortem** (required for every Sev-1 and Sev-2, within 3 business days):

- **Blameless.** The target is the system that let a human mistake reach prod,
  not the human.
- Cover: timeline (from the Slack timestamps), user impact, root cause,
  what detected it (and how fast), and concrete action items with owners.
- Every action item becomes a tracked ticket. A postmortem with no follow-up
  is theater.

---

## On-call

Replace `[CONFIGURE]` fields before relying on this in production.

- **Rotation:** [CONFIGURE: e.g. PagerDuty schedule "DealSignal Primary"] — link:
  `[CONFIGURE: schedule URL]`
- **Primary on-call (today):** [CONFIGURE: name + phone/Slack]
- **Secondary / backup:** [CONFIGURE: name + phone/Slack]
- **Paging:** [CONFIGURE: PagerDuty / Opsgenie service name]. Ack window: **5 min**.
- **Escalation:** If primary doesn't ack in 5 min → page secondary. If neither
  acks in 10 min → page [CONFIGURE: engineering lead / CTO].
- **Status page admin:** [CONFIGURE: who can post external updates]

**Setup checklist (one-time):**

1. Create PagerDuty/Opsgenie service with Slack + SMS/phone routes.
2. Import on-call calendar (weekly rotation recommended for pilot).
3. Connect Sentry + Render deploy-failure webhooks to the paging service.
4. Create public status page; store URL above and in `docs/operations.md`.

| What broke | Who |
|---|---|
| API 5xx, Sentry errors | Backend on-call |
| Frontend white screen / build fail | Frontend on-call |
| Postgres CPU / disk / connections | Backend on-call → DBA / migration author |
| Auth broken for everyone | Backend on-call — **Sev-1** |
| Migration failed mid-deploy | Migration author first, then backend on-call |
| Suspected security incident | Backend on-call + whoever owns security — **Sev-1** |
