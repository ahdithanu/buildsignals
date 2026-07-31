# Changelog

All notable changes to DealSignal are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Daily permit ingestion cron (`scripts/daily-ingestion.sh`, Render cron, GitHub Actions)
- Staging Render blueprint (`render-staging.yaml`)
- Uptime probe script and scheduled GitHub workflow (`scripts/uptime-check.sh`)
- Pre-commit CI workflow
- Postmortem template and ops log
- Example Prometheus alert rules

## [1.1.0] — 2026-07-29
- Post-deploy smoke test script (`scripts/smoke-test.sh`)
- Frontend CI workflow (lint, typecheck, vitest, build)
- Playwright E2E CI workflow (auth + deal flows)
- Monitoring, staging, and dependabot triage guides

### Fixed
- Refresh cookie path (`/v1/auth`) — auth persists across full-page navigation
- Frontend type errors, test fixtures, and ESLint configuration
- E2E networking via Vite dev proxy for same-origin API calls

### Changed
- `render.yaml`: starter plans, `npm ci` build, CSP enabled
- `package-lock.json` regenerated for Node 20

### Security
- Content-Security-Policy on static frontend
- Export policy gating for parcel boundary geometry (PR #23)

## [1.0.0] — pilot baseline

Initial pilot release: multi-tenant deal platform with auth, RLS, ingestion,
parcel discovery, and underwriting workflows.

[Unreleased]: https://github.com/ahdithanu/cre-deal-intelligence/compare/main...cursor/enterprise-readiness-9bac
[1.0.0]: https://github.com/ahdithanu/cre-deal-intelligence/releases/tag/v1.0.0
