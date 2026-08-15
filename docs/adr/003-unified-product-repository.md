# ADR 003: Unified Build Signals product repository

## Status

Accepted on August 15, 2026.

## Context

Build Signals product work had become split between two repositories:

- `ahdithanu/cre-deal-intelligence`, containing the FastAPI API, ingestion
  workers, knowledge graph, React/Vite application, tests, and infrastructure;
- `ahdithanu/deal-signal-terminal`, containing a separate Next.js presentation
  application deployed to Vercel.

Maintaining two user-facing applications duplicates authentication, opportunity
projection, graph presentation, deployment configuration, and design work. It
also makes it possible for a backend capability to ship without appearing in
the production interface.

## Decision

`ahdithanu/cre-deal-intelligence` is the canonical repository for all Build
Signals product development.

- The existing React/Vite application in `src/` is the customer-facing UX.
- Vercel builds the frontend from the repository root and publishes `dist/`.
- FastAPI remains the source of truth for authentication, permits,
  opportunities, graph data, evidence, and workflows.
- API and ingestion services may remain on Render during the initial frontend
  cutover. Hosting location does not change repository ownership.
- New UX concepts from the separate terminal are ported onto existing API
  contracts; its independent storage and business logic are not copied.
- No new product work is added to `deal-signal-terminal`. It can be archived
  after the unified Vercel deployment passes production smoke tests.

## Vercel contract

The Vercel project must use this repository and its root directory. Required
build configuration is checked in as `vercel.json`.

The production project must define:

- `VITE_API_BASE_URL`: HTTPS origin of the production FastAPI service;
- `VITE_SENTRY_DSN`: optional frontend Sentry project;
- `VITE_SENTRY_ENVIRONMENT=production`.

The API must allow the final Build Signals Vercel origin in
`CORS_ALLOWED_ORIGINS`, and `APP_BASE_URL` must use that same public origin so
password-reset links remain valid. Authentication cookie behavior must be
verified on a Vercel preview before domain cutover.

## Cutover sequence

1. Port and verify the redesigned signals feed and opportunity detail UX.
2. Create a Vercel preview from this repository.
3. Configure the production API URL and optional Sentry environment values.
4. Add the preview and production origins to API CORS configuration.
5. Run frontend tests, production build, browser smoke tests, auth checks, and
   `npm audit --omit=dev`; resolve high-severity production advisories before
   promoting the deployment.
6. Move `buildsignals.ai` only after explicit production approval.
7. Keep the previous deployment available for rollback through the validation
   window, then archive the superseded repository.

## Consequences

One pull request can now evolve ingestion, graph contracts, and the UI that
consumes them. Vercel previews exercise the same frontend that is tested beside
the backend. The tradeoff is that frontend and backend CI run from a larger
repository, which is already supported by the repository's path-scoped
workflows.
