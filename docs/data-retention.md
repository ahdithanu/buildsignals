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

There's no per-user self-service erasure endpoint yet. To remove one user
today: an org admin removes their membership
(`DELETE /v1/organizations/{org_id}/members/{user_id}`); if that was their
last membership, delete the orphaned user row via the backoffice CLI
(`scripts/admin.py`). A dedicated per-user erasure endpoint is a reasonable
future addition if self-service GDPR requests become common.

## Gaps / future work

- **No automated retention enforcement.** Nothing prunes data on a schedule;
  retention is "life of the account." If a contractual retention *cap* is
  ever required (e.g. delete inactive-org data after N months), it needs a
  scheduled job.
- **No per-user self-service erasure** (see above).
- **Backup deletion is time-bound, not immediate** — inherent to snapshot
  backups; document it in the DPA rather than trying to engineer around it.
