# Production Acceptance

These checks distinguish implemented software from verified live operation.
They do not activate sources, deploy code, configure delivery or migrate schemas.

## Ingestion Collection

Use an existing, appropriately scoped customer-workspace credential. Provision
`INGESTION_VERIFY_TOKEN` through the operator's environment/secret manager; never
put it in a shell argument, committed file, report or chat. Do not use demo login
to certify customer ingestion.

```sh
.venv/bin/python scripts/verify_ingestion_runs.py \
  --api-base https://www.buildsignals.ai \
  --organization-id CONFIRMED_WORKSPACE_ID \
  --record-type permit --source-key EXPECTED_REVIEWED_SOURCE \
  --freshness-hours 36 --live-acceptance
```

Repeat `--source-key` for every expected source in this record-type scope, at most
50. Run separately for `planning`. An empty or duplicate expected scope is refused.
No live request occurs without explicit live mode and an environment credential.
The HTTPS origin cannot contain credentials, a path or query. Requests are GET
only, redirects are not followed, each response is bounded to two MB, and coverage
pagination is limited to ten pages of 100 sources. Expected sources absent from
the response fail; truncated, stale or duplicate coverage evidence fails closed.

The gate checks `/v1/auth/me` against the exact expected workspace, excludes demo
sessions, retrieves measured inventory, then requests the latest run per source.
Each selected source must be active and have nonempty stored inventory plus a
recent scheduled, completed run with zero record failures and coherent timestamps.
A zero-row refresh can pass when existing inventory is nonempty: quiet feeds are
not inherently unhealthy. A completed keyset cursor is not itself a failure.

JSON output includes source keys, counts, run IDs and stable reason codes, not
tokens, raw records, error text, people or actor details. Exit 0 means this
explicit collection scope passed; all other dispositions exit nonzero. A pass
does not prove independent provider totals, unique projects, new filing dates,
complete geographic coverage, parcel matches or for-sale availability.

## Isolated PostgreSQL Restore

`scripts/verify_postgres_recovery.py` must run only against an independently
identified isolated restored copy using the restricted application role. Set
`RESTORE_DATABASE_URL` securely; keep the actual source `DATABASE_URL` available
for identity comparison. Never print either value.

```sh
.venv/bin/python scripts/verify_postgres_recovery.py --isolated-restored-copy
```

The guard requires an explicit PostgreSQL host/database, rejects source-target
identity equivalence despite credential, driver, default-port or host-case
differences, and refuses libpq routing overrides. It cannot detect DNS aliases,
tunnels or infrastructure mistakes. Explicit operator verification is mandatory.

The existing probe uses rollback-only transactions to check restricted-role,
forced-RLS metadata and selected deal-table cross-tenant/default-deny behavior.
Only literal `passed: true` yields success. This does not measure snapshot
provenance, application recovery, all tables' behavioral isolation or RPO/RTO.
Record those separately during a separately authorized real restore drill.

## Remaining Operational Gates

- Owned alert destination, delivery configuration and demonstrated failure/recovery.
- Actual fresh ingestion acceptance receipt against the customer workspace.
- Isolated PostgreSQL recovery receipt, application checks and measured RPO/RTO.
- Authenticated customer acquisition workflow and MFA acceptance.

Do not mark these complete based on offline fixtures or this runbook.
