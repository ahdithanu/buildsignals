# Database readiness guard

Adds public `GET /health/ready`: HTTP 200 with `{"status":"ready"}` only when
every mapped table/column resolves and Alembic's stored revision set exactly
matches the release's heads. All other outcomes return HTTP 503 with
`{"status":"not_ready"}`. Responses disable caching and never expose schema
names, revision IDs, connection details, SQL, or exception text.

The guard performs one zero-row SELECT per mapped table, including both planning
tables, and reads at most the expected head count plus one Alembic version rows.
It never fetches tenant/customer rows, flushes the ORM session, commits, creates
schema, or runs migrations. Script location comes from the repository's
`alembic.ini`, with relative paths anchored there rather than to the process CWD.
Release heads are cached per process; readiness results are not cached.

PostgreSQL uses a separate read-only transaction with local 1-second statement
and 250-millisecond lock timeouts. A 5-second cooperative budget stops additional
probes. Connection/pool acquisition and network failures remain subject to the
existing engine/driver timeouts; this is not a hard end-to-end deadline. SQLite
uses its existing driver timeout. Normal rollback/close releases the connection
and PostgreSQL transaction settings, including after failures.

`/health`, `/health/deep`, authentication, dependencies, and deployment settings
are unchanged. This is a schema/revision gate, not proof of correct types,
indexes, constraints, data quality, write privileges, RLS behavior, or tenant
inventory. Missing version metadata and ahead/unknown revisions fail closed.
Do not substitute readiness for the existing restart/liveness probe.

Verification uses disposable SQLite schema fixtures plus mocked PostgreSQL
transaction/timeout checks. No production database, migrations, or deployment
are involved; a live PostgreSQL readiness check remains an operational follow-up.

## Post-deployment checks

`scripts/smoke-test.sh` now requires `/health/ready` to pass. When smoke-account
credentials are supplied, it also verifies authenticated planning, retail
expansion, and permit-match list requests. Set `REQUIRE_AUTH_SMOKE=true` for
pilot verification to fail rather than silently skip authentication. Login JSON
is encoded with `jq`, so quotes and backslashes in credentials are preserved.

These checks deliberately accept empty lists: endpoint availability is distinct
from populated inventory. Before any demo-ready claim, verify the intended
organization has real imported source records and complete the evidence,
nearby-parcel, save, and export workflow in the deployed browser.
