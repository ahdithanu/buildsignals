# Security Policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in DealSignal, report it
privately — **do not open a public GitHub issue**.

- Email **security@dealsignal.com** *(set this to a monitored inbox before
  publishing the repo — a distribution list, not a personal address).*
- Include: what you found, steps to reproduce, affected endpoint/version, and
  the impact you believe it has.
- If you have a proof-of-concept, include it. If exploiting it would expose
  real user data, describe the exploit instead of running it against
  production.

We aim to acknowledge a report within **2 business days** and to share a
remediation timeline within **5 business days**. Please give us a reasonable
window to fix an issue before any public disclosure.

## Scope

In scope:

- The DealSignal API (`app/`) and web frontend (`src/`).
- Authentication, authorization, multi-tenant isolation, and data exposure.

Out of scope:

- Findings that require a compromised developer machine or leaked credentials
  we already treat as compromised (see `docs/secrets.md`).
- Denial of service from raw request volume — the app has per-IP rate limits,
  but capacity limits aren't treated as vulnerabilities.
- Reports against a self-hosted fork rather than our production deployment.

## What we already do

These are the guarantees a report should account for — if you can defeat one,
that's a finding:

- **Auth** — JWT access tokens (15-min TTL) + rotating refresh tokens in
  httpOnly, Secure cookies. TOTP 2FA available. Passwords hashed with bcrypt.
- **Tenant isolation** — Postgres row-level security plus application-layer
  org scoping on every query. A token for org A cannot read org B's data.
- **Transport & headers** — HSTS, CSP, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, and Permissions-Policy on every response.
- **Config safety** — production refuses to boot with a dev signing key, a
  non-Postgres database, wildcard CORS, or anonymous access enabled.
- **Dependencies** — `pip-audit` gates CI; Dependabot tracks updates. We carry
  no known-CVE dependencies at time of writing.
- **Secrets** — never in version control; rotation procedures in
  `docs/secrets.md`.

## Supported versions

DealSignal is a continuously deployed SaaS — only the current production
release (the tip of `main`) is supported. There are no backported security
fixes to older revisions.
