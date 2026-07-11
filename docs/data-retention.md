# Data retention & deletion

What DealSignal stores, how long it's kept, and how it's deleted. Written to
answer the two questions every enterprise data-processing agreement asks:
*"how long do you hold our data?"* and *"can you delete it on request?"*

## What we hold

| Data | Contains PII? | Where |
|---|---|---|
| Organizations, memberships | Names | Postgres |
| Users | Email, name, password hash (bcrypt), TOTP secret | Postgres |
| Deals, assumptions, outputs, contacts, signals, documents, memos, distributions, pipeline events, buy boxes | Contact names/emails; deal financials | Postgres |
| Audit logs | Actor id + change diffs | Postgres |
| Password-reset tokens | Hashed token + user id | Postgres |
| Error events (Sentry) | No PII — `send_default_pii=False` enforced | Sentry |
| Application logs | Request id, method, path, status — no request bodies | Log storage |
| Metrics (Prometheus) | Route templates + counts — no user data | Metrics store |

## Retention

DealSignal is an operational system of record, not an archive. While an
organization is active, its data is retained for as long as the account
exists — that's the point of a deal pipeline.

| Data | Retention |
|---|---|
| Active org's business data | Life of the account |
| Password-reset tokens | Single-use; expire per `REFRESH`/reset TTL, then dead |
| Database backups | Render daily snapshots, **7-day** window (see [backups.md](backups.md)) |
| Error events (Sentry) | Per Sentry project retention (default 90 days) |
| Application logs / metrics | Per the platform's retention — set a cap on the log store |

**Backups are the long pole for deletion.** After an erasure (below), a
copy of the deleted data persists in snapshots until they roll off the 7-day
window. A data-processing agreement should state this explicitly: erasure is
immediate in the live database and completes fully within the backup window.

## Deletion (right to erasure)

`POST /v1/organizations/{org_id}/delete` permanently erases an organization
and all its data. It is **irreversible in the live database**.

Guard rails:

- **Admin only**, and the `{org_id}` must equal the caller's active org — an
  admin cannot delete an org they aren't currently acting in.
- The request body must echo the org's **exact name** (a type-to-confirm
  step) — an irreversible bulk delete can't be triggered by accident.
- The **default/demo org cannot be deleted**.

What it removes:

- Every tenant-scoped table (deals, contacts, memos, documents, signals,
  audit logs, …), in FK-safe order.
- All memberships for the org.
- Users whose **only** membership was this org. A user who also belongs to
  another org keeps their account; only their membership here is removed.

Because the org's own `audit_logs` are erased too, the deletion is recorded
as a **PII-free receipt** (org id, timestamp, actor id, per-table row counts)
to the application log — which lives in separate storage — rather than to
`audit_logs`. The API response returns that same receipt.

### Deleting a single user

`POST /v1/auth/delete-account` lets a user erase their own account (GDPR
right to erasure). It requires re-entering the current password and is
irreversible.

- The user row (email, name, password hash, TOTP secret) is deleted — that's
  the personal data, so deleting it is the erasure.
- FKs handle the rest: memberships and password-reset tokens cascade away;
  authored records (deals, audit rows, buy boxes) have their
  `created_by`/`actor_id` set NULL. The org keeps its data; the personal
  link is severed.
- Guard: a user who is the **sole admin** of any org can't self-delete (it
  would orphan the org). They must promote another admin or delete the org
  first — a 409 explains which org(s).

An admin can also remove another user: drop their membership
(`DELETE /v1/organizations/{org_id}/members/{user_id}`), then delete the
orphaned user row via the backoffice CLI (`scripts/admin.py`) if it was
their last membership.

## Gaps / future work

- **No automated retention enforcement.** Nothing prunes data on a schedule;
  retention is "life of the account." If a contractual retention *cap* is
  ever required (e.g. delete inactive-org data after N months), it needs a
  scheduled job.
- **No per-user self-service erasure** (see above).
- **Backup deletion is time-bound, not immediate** — inherent to snapshot
  backups; document it in the DPA rather than trying to engineer around it.
