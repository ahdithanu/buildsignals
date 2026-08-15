# Build Signals Vercel export

The nationwide ingestion service is the source-normalization producer. The Vercel application is
the user-facing opportunity and knowledge-graph consumer. They exchange provider-neutral contract
version `1.0` over an authenticated HTTPS endpoint.

## Dry run

```bash
python -m app.services.ingestion.cli publish-build-signals \
  --organization <organization-id-or-slug> \
  --stage pre_approval_and_approved \
  --source-key mesa_az_commercial_permit_submittals \
  --dry-run \
  --output /tmp/build-signals-import.json
```

Dry run does not call Vercel. Review the generated JSON before enabling a source scope.

## Publish

Set these values in the runtime that executes nationwide ingestion:

- `BUILD_SIGNALS_INGESTION_URL=https://www.buildsignals.ai/api/internal/ingestion/import`
- `BUILD_SIGNALS_INGESTION_SECRET=<same value as Vercel INGESTION_BRIDGE_SECRET>`

Then publish a reviewed scope:

```bash
python -m app.services.ingestion.cli publish-build-signals \
  --organization <organization-id-or-slug> \
  --stage pre_approval_and_approved \
  --source-key mesa_az_commercial_permit_submittals
```

The command exports only active canonical records in `pre_approval` or `approved` stages by
default. Records are grouped by source and market and sent in bounded 500-record batches. The Vercel receiver
uses source key plus external record ID for idempotency, so retries update records rather than
duplicating them.

Start with one reviewed source, compare producer counts to the Vercel data-health page, and then
expand through the existing rollout waves. Do not publish candidate or legal-hold sources.
