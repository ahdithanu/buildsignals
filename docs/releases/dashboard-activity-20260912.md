# Dashboard activity release

## Scope

Show read-only imported planning records and national-brand permit matches on
the dashboard and empty saved-deal inbox. Keep saved deals separate from detected
activity. Preserve manual deal creation and existing populated workspaces.

The feed uses the existing production endpoints for planning events, permit brand
matches, and measured ingestion coverage. A compatible audit-service fix ensures
deal writes inherit the authenticated organization instead of a hardcoded tenant.
No authentication protocol, database migration, or tenant-permission changes are
included. The audit fix needs the API deployment in addition to the Vercel UI.

## Evidence and empty states

- Keep source links and original record descriptions accessible.
- Distinguish company-name match confidence from evidence of a new opening.
- Distinguish loading, request failures, filtered results, and missing inventory.
- Do not manufacture deals, confirm identities, or import records on page load.
- Keep nearby candidates distinct from verified listings.

## Release verification

- Frontend unit tests, type checking, lint, and production build.
- Browser workflows use a disposable migrated database, never an inherited target.
- Verify the production alias points to the released commit and the API is healthy.
- Authenticate as the intended customer organization to verify real inventory.

Deploying this UI does not populate production data. Prior local imports are not
evidence of production coverage. The broader authentication and infrastructure
changes in PR #115 remain a separate coordinated release.
