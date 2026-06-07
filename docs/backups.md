# Database Backups & Restore

## Where backups come from

Production Postgres is managed by Render. Render automatically takes **daily
snapshots** of the database with a default **7-day retention** window. No application
code is involved — snapshots are taken at the storage layer.

Reference: <https://render.com/docs/postgresql-backups>

## RPO / RTO

| Metric | Target  | Notes                                                   |
|--------|---------|---------------------------------------------------------|
| RPO    | 24 hours | We can lose at most one day of writes (daily snapshot). |
| RTO    | ~1 hour  | Manual restore via the Render dashboard.                |

If we need a tighter RPO than 24h, we must upgrade to a Render plan that supports
point-in-time recovery (PITR). See "Disaster scenarios" below.

## Restore drill (recommended quarterly)

Spin up a copy of production to validate that the snapshot is usable.

1. In the Render dashboard, navigate to the production Postgres instance.
2. Open the **Backups** tab and pick the most recent snapshot.
3. Click **Restore** and choose **Restore to a new database** — never overwrite the
   live production DB during a drill.
4. Wait for the new instance to come up (a few minutes).
5. Connect via `psql` using the new connection string and run smoke queries:
   - `SELECT count(*) FROM users;`
   - `SELECT count(*) FROM organizations;`
   - `SELECT max(created_at) FROM audit_log;` — confirms recency.
6. Optionally point a staging deployment at the restored DB and exercise a few
   read-only flows.
7. Delete the restored instance when finished.

Record the drill date, snapshot used, and outcome in the team ops log.

## Disaster scenarios

### Full region outage

Render's snapshots are stored in the same region as the database by default. If the
region is down:

1. Provision a new Postgres instance in a healthy region from the dashboard.
2. Use Render's cross-region restore (if available on the current plan) or import
   the most recent dump manually.
3. Update `DATABASE_URL` on the web service and redeploy.

### Accidental table truncation or bad migration

The daily-snapshot tier **does not support point-in-time recovery**. The best
available recovery is the most recent nightly snapshot, which can mean losing up to
24 hours of writes.

**Upgrade path:** Render's higher-tier Postgres plans include PITR with WAL
streaming, reducing RPO to minutes. Recommended once business impact of a 24-hour
data loss exceeds the plan upgrade cost.

### Application-level data corruption (e.g. buggy bulk update)

1. Restore the latest snapshot to a new instance (see "Restore drill").
2. Export the affected rows from the restored copy.
3. Reconcile against production manually — do not swap the whole DB unless the
   corruption is catastrophic.
