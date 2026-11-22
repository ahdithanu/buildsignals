# Password Recovery Delivery

## Contract

`POST /auth/password/forgot` and `POST /auth/password/reset` are public,
rate-limited account recovery endpoints. Reset tokens are hashed, expire after
one hour and are single-use. A successful reset revokes existing refresh-cookie
sessions. Already-issued access JWTs remain valid until their expiry (normally
up to15minutes); immediate access-token revocation is outside this repair.
Both audit actions use the account's persisted active organization membership:
default membership first, then joining time and ID. They never use the caller's
organization or fabricate a bootstrap organization. Accounts without an active
organization cannot start or complete recovery through this path.

Accepted `/forgot` requests return 204 for known, unknown, inactive and demo
addresses. Recipient-specific provider failures also return the same 204 to
avoid account enumeration; a sanitized `password_reset_delivery_failed` warning
is emitted without exception bodies, addresses or tokens. Therefore a 204 is
request acceptance, not evidence of delivery. The UI does not promise delivery.
Identical response shapes do not eliminate the latency difference from the
existing synchronous provider call. Comprehensive timing-side-channel resistance
is not claimed; asynchronous delivery/outbox work is outside this repair.

Missing staging/production email configuration returns a uniform 503 with
`Retry-After: 60` before looking up an account. The API itself remains available.
HTTP failures and network failures show a generic retryable UI error, not a
success message. Local console transport does not send email and logs metadata
only, never message bodies or reset tokens. Demo sessions remain read-only.
The pinned Resend SDK uses an explicit five-second connect/read I/O timeout;
this is not a strict end-to-end wall-clock deadline or delivery guarantee.

## Provider Setup

1. The owner creates/signs into Resend and personally accepts any account terms.
   No paid upgrade is required by the application; do not accept one implicitly.
2. Verify a domain or subdomain you control using exactly the DNS records shown
   by Resend. DNS changes require the applicable owner approval. Do not replace
   unrelated MX, SPF or existing mail-provider records. Check the provider's
   guidance before combining records.
3. Create a dedicated **Sending access** API key restricted to that domain.
   The owner must approve credential creation. Never put the key in chat, Git,
   screenshots, frontend variables or shell history.
4. With separate production configuration/access approval, store the key in the
   existing managed-secret facility and reference it as `RESEND_API_KEY` in the
   API only. Set `RESEND_FROM_ADDRESS` to an address at the verified domain and
   `APP_BASE_URL` to the HTTPS frontend origin. Do not silently use the legacy
   default sender in a deployed environment. The application checks configuration
   presence; only provider verification can establish domain and key validity.
5. These settings are loaded at process import. Follow the separately approved
   image/configuration rollout; do not run a migration or standard deployment
   workflow under a no-migration grant. Retain a private rollback receipt and
   preserve unrelated API settings, workers, sources and schedules.

Official references, checked November 20, 2026:
- [Verified domains](https://resend.com/docs/dashboard/domains/introduction)
- [Sending-access key permissions](https://resend.com/changelog/new-api-key-permissions)
- [Email delivery dashboard](https://resend.com/docs/dashboard/emails/introduction)

## Verification

```sh
python -m pytest tests/test_password_reset.py tests/test_password_recovery_delivery.py -q
# Requires a migrated, disposable, restricted-role local PostgreSQL target.
python -m pytest tests/test_password_reset_postgres.py -q
npm test -- src/test/password-reset.test.tsx
# Disposable API + frontend; external sockets blocked, no actual email delivery.
node node_modules/@playwright/test/cli.js test -c e2e/password-recovery.playwright.config.ts
```

The PostgreSQL file accepts an explicit `TEST_POSTGRES_URL`, with a loopback
host and port and a newly provisioned `forgeos_test_<UUID-v4-hex>` database;
hosted GitHub CI uses its existing `dealsignal_test` target. Every physical
connection verifies the database/role and FORCE RLS. Independently establish
runtime ownership before provisioning; a loopback address or database name alone
is not proof of locality. Do not rename existing databases to satisfy the guard,
use a superuser/BYPASSRLS role, or fall back to production/ambient credentials.
The fixture never creates schema and only cleans its own unique synthetic rows.

After an approved rollout, make one reset request for an owner-approved account.
Verify provider acceptance and delivery in Resend; do not infer delivery from
204 or from the UI. Confirm the message reaches the recipient, not just the
provider queue. The owner opens the newest link and enters/submits a new password
personally. Verify sign-in works, old refresh cookies are rejected and the link
cannot be reused. Do not claim old access JWTs are immediately revoked. Never
retrieve a token from application/provider logs as a workaround.
Do not repeatedly resend against an unconfigured sender or bypass rate limits.

Operational identifiers, production logs and delivery receipts remain internal.
Local mocks and PostgreSQL tests are not live email-delivery acceptance.
