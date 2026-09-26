# Customer Ingestion Dispatcher

The customer ingestion dispatcher converts an active onboarding enrollment into
bounded source runs. It is a control-plane worker, not a connector: source
fetching, normalization, reconciliation, graph projection, and evidence
handling remain in the existing ingestion service.

## Safety Boundary

- Only source keys present in the checked production catalog can run.
- Each enrollment's stored catalog-manifest digest must match the worker's
  checked manifest before any source is claimed.
- Production execution requires one reviewed rollout wave.
- The existing rollout-manifest and outbound-host attestations run before any
  network request.
- Each organization receives a fresh `RequestContext` and database session.
  PostgreSQL transaction-local RLS therefore cannot leak one customer's data
  into another customer's run.
- An expiring enrollment-source lease is committed before the network call.
  Completion is fenced by the same lease token, so a stale worker cannot
  overwrite a replacement worker.
- Paused, manual, removed, future-due, unreviewed, and currently leased sources
  are skipped.

## Bounds and Retries

The dispatcher limits organizations, total sources, sources per organization,
pages per source, and total worker wall-clock time. It does not start another
source after the wall-clock deadline. Individual connector requests retain the
connector layer's timeout and retry bounds, while enrollment
`max_pages_per_run` controls the number of pages processed.

Successful `completed` and `partial` runs return to their configured cadence.
Failed and `partial_with_errors` runs use exponential retry backoff starting at
15 minutes, capped by the source cadence and 24 hours. One source or customer
failure does not stop later customers.

## Worker Command

Run a no-write production parity check for Wave 1:

```bash
ENVIRONMENT=production \
INGESTION_ROLLOUT_WAVE=1 \
INGESTION_PLAN_ONLY=true \
./scripts/customer-ingestion-dispatcher.sh
```

After rollout and host-policy attestations match the worker scope, enable
writes with `INGESTION_PLAN_ONLY=false`.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `INGESTION_ROLLOUT_WAVE` | none | Reviewed wave; required for production writes |
| `INGESTION_SHARD_COUNT` | `1` | Deterministic source shard count |
| `INGESTION_SHARD_INDEX` | `0` | Source shard handled by this worker |
| `INGESTION_ORGANIZATIONS` | all | Optional comma-separated org IDs or slugs |
| `INGESTION_MAX_ORGANIZATIONS` | `100` | Organization cap per invocation |
| `INGESTION_MAX_SOURCES` | `100` | Global source cap per invocation |
| `INGESTION_MAX_SOURCES_PER_ORGANIZATION` | `25` | Per-customer fairness cap |
| `INGESTION_WALL_CLOCK_SECONDS` | `3000` | Stop starting work after this duration |
| `INGESTION_ENROLLMENT_LEASE_SECONDS` | `3600` | Claim lease duration; must cover the worker wall-clock bound |
| `INGESTION_PLAN_ONLY` | `false` | Report due work without claims or network calls |

The command emits one JSON summary suitable for logs and alerting. A nonzero
exit means at least one source failed or the worker reached its deadline.

## Rollout

1. Deploy the migration and API containing customer onboarding.
2. Activate a test organization with a selected-state, Wave 1 scope.
3. Run all Wave 1 shards in plan-only mode and compare source counts.
4. Run one organization and one shard with writes enabled.
5. Verify run records, enrollment timestamps, graph evidence, and tenant
   isolation.
6. Expand organization and source caps gradually.
7. Add Waves 2 through 4 as separate worker scopes with their own exact host
   policy digests.

Do not combine all waves into one production worker until its outbound host
allowlist, runtime budget, and capacity have been reviewed as one scope.
