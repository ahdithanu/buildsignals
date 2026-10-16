# Recurring Columbus Ingestion

Two independent AWS EventBridge Scheduler jobs run daily in `us-east-1`, in
schedule group `buildsignals-ingestion`:

- `columbus-production-daily`: explicitly pinned customer organization.
- `columbus-demo-daily`: reserved read-only demo organization, fetching public
  source data independently. Never copies customer tables or rows.

Both use `scripts/recurring_columbus.py`, the reviewed Columbus Site Engineering
application catalog entry, existing normalization, provenance and graph pipeline.
Each fetches applications filed in the current UTC day plus the previous 30 days.
This is overlapping-window collection, not a provider change-data-capture feed:
changes to older filings outside that window require separate reconciliation.
Records aging out are retained, not inferred deleted. Site applications are not
commercial permit issuances, confirmed brand expansions or for-sale parcels.

## Bounds and Isolation

Four pages of at most 250 records; 30-second HTTP timeout, one retry per request;
provider counts before/after must match the fetched count. Overflow/incomplete
runs fail instead of silently claiming complete coverage. Upserts use stable
source record identity. Existing recent-snapshot source IDs are adopted rather
than duplicating their records. PostgreSQL advisory locks prevent overlapping
same-mode workers; the service also claims runs. Demo and production jobs have
different source keys and tenant contexts, with existing PostgreSQL RLS.

Only `maps2.columbus.gov` is allowed outbound. Personal contacts, attachments and
raw geometry remain excluded by the reviewed catalog. Demo sources are returned
to inactive even on failure and are manual for the general catalog dispatcher.
Public demo HTTP sessions remain read-only independently of worker configuration.

## Deployment

Use authorized AWS credentials and the repo virtualenv from the repo root:

```sh
PYTHONPATH=. python scripts/configure_recurring_columbus.py \
  --organization-id YOUR_CONFIRMED_WORKSPACE_ID \
  --image YOUR_EXISTING_API_ECR_IMAGE_AT_SHA256_DIGEST \
  --confirm-production
```

The provisioning script registers separate versioned Fargate task definitions.
They embed the reviewed worker script in their command and pin the existing API
image by digest; no API deployment or production schema change is needed.
Database credentials use the existing managed secret references, not plaintext
environment variables. The Scheduler IAM role may run only those two task
revisions on the existing cluster and pass only the existing execution role to
ECS. Trust is restricted to this account and schedule group.

Provisioning schedules the first invocations shortly afterward, then daily.
Reprovisioning deliberately registers new task revisions and resets that start
time; review before running it against an existing schedule. IAM creation may
need propagation time before Scheduler accepts a newly created execution role.
AWS compute/logging charges apply; no OpenRouter calls or model credits are used.

## Verification and Recovery

Check Scheduler configuration, actual ECS task invocation and container exit,
CloudWatch logs `/ecs/buildsignals-ingestion` (30-day retention), and persisted
`ingestion_runs` and source-specific record counts. A configured schedule or a
successful RunTask delivery alone is not a successful data refresh. Logs report
seen/inserted/updated/failed counts and reconciliation. Scheduler retries launch
delivery twice within 15 minutes; those retries do not detect application exits.
Runtime failures are logged and retained in ingestion-run receipts when the run
has started. Automatic paging/notification for runtime failure is not configured.

Disable either schedule without changing data:

1. Get its full configuration with `aws scheduler get-schedule`.
2. Update the same schedule with `State=DISABLED`, preserving its target/expression.
3. Check for already-running ECS tasks; disabling future runs does not stop them.

Do not delete records or alter other tenants to recover a failed refresh. Review
the specific source run, request budget and official source availability first.
