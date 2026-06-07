# Operations

## Environment Variables

### Error Tracking (Sentry)

The backend integrates with [Sentry](https://sentry.io) for error tracking, but only
activates when `SENTRY_DSN` is set in the environment. Without it, the SDK is never
imported and there is zero overhead — useful for local development and tests.

| Variable      | Required | Default       | Description                                   |
|---------------|----------|---------------|-----------------------------------------------|
| `SENTRY_DSN`  | No       | (unset)       | Project DSN from Sentry. When unset, Sentry is disabled entirely. |
| `ENVIRONMENT` | No       | `development` | Tag attached to Sentry events (e.g. `production`, `staging`). |

`send_default_pii=False` is enforced so emails, IPs, and other personally-identifiable
request data are never sent to Sentry. Trace sampling is set to 10%.

To enable in production, set `SENTRY_DSN` in the Render service environment.

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every pull request. It:

1. Installs Python dependencies.
2. Runs `alembic upgrade head` against a throwaway SQLite database.
3. Runs an Alembic drift check — fails the build if a SQLAlchemy model change
   has no matching migration.
4. Runs the full `pytest` suite.

See `docs/backups.md` for backup and restore procedures.
