# Schema reconciliation release

Revision `20260923_0001` reconciles legacy migrations with current SQLAlchemy
metadata. It changes nullability, index names, and equivalent uniqueness
enforcement. It does not backfill, delete, or fabricate customer records.

## Release gates

- CI runs `python -m alembic check` directly on SQLite and PostgreSQL. Its exit
  status must fail the job. Do not pipe through `tee` without `pipefail`, suppress
  errors, or replace a failed check with generated migration output.
- Frontend CI audits the complete lockfile, including development dependencies,
  at moderate severity or higher. Render uses `npm ci` to build that same tree.
- Run the data-preservation migration tests, backend/frontend suites, and real
  browser evaluation flow before promoting a release. See [E2E](../../e2e/README.md).
- A green build, a frontend preview, and `/health` do not prove the migration was
  exercised against an isolated deployed API. Verify the actual staging API URL
  and its database are separate from production.

## Before migrating

1. Take a recoverable database backup and confirm the restore procedure with the
   operator. Rehearse on an access-controlled database copy; never place customer
   data in shared staging. Public staging uses synthetic data only.
2. Inspect the current Alembic revision. This revision follows `20260920_0001`.
3. Schedule a maintenance window and pause writes/background workers. PostgreSQL
   takes `ACCESS EXCLUSIVE` locks while checking and changing affected tables.
   Long transactions can delay lock acquisition; use an operator-approved lock
   timeout and retry later rather than leaving a release waiting indefinitely.
4. Run migrations using the PostgreSQL table-owner maintenance role, not the
   application's restricted runtime role. During the transaction, this revision
   temporarily relaxes `FORCE ROW LEVEL SECURITY` on affected tables so preflight
   includes every tenant. It restores the original flags before commit. Any
   failure rolls the changes back. It does not remove tenant policies.

```bash
# DATABASE_URL must refer to the intended environment; never print its value.
python -m alembic current
python -m alembic upgrade head
python -m alembic check
```

The online preflight stops if historical required columns contain NULLs or if
unique fields have duplicate groups. The error reports column names and counts,
not customer values. Repair only from authoritative records with explicit
operator approval, then retry. Do not fill missing dates with today's date,
guess ownership, or delete rows just to make deployment pass.

Offline `--sql` generation is deliberately rejected because it cannot validate
the existing records. SQLite runs a transactional batch rebuild on a dedicated
connection with foreign keys disabled before the transaction, preserves
triggers, and checks foreign-key integrity before and after. It refuses unsafe
foreign-key settings instead of toggling them mid-transaction.

## Verify and recover

After upgrade, confirm `alembic current`, a zero-drift `alembic check`, and
`/health/ready`. Exercise login, tenant isolation, opportunities, and an admin
evaluation run against the isolated deployment. Record commit, migration head,
test results, and operator approval before promoting that commit.

If preflight or DDL fails, keep the previous application running and investigate
the reported inconsistency; this revision is transactional. If application
rollback is needed after a successful migration, prefer the previous compatible
application version with the reconciled schema. A schema downgrade is a separate
maintenance operation: it restores prior nullable columns/index conventions,
not a backup or lost business data. Test downgrade/re-upgrade on an isolated
copy before considering it in production.

## Tradeoffs and scaling

The one-time locked migration favors correctness across legacy schemas over an
online, zero-downtime rollout. At millions of opportunities, schedule based on
measured table sizes and rehearsal duration. If the lock window is unacceptable,
split a future rollout into concurrent index creation, staged constraint
validation, and short metadata changes. Do not silently drop validation to speed
up deployment. Normal application traffic continues to use tenant-scoped
services and policies after migration.
