# Browser session protocol and cookie-race regression gate

The original five HttpOnly cookie/identity reproductions are now **positive
assertions**, extended to twelve cases. Every mode exits nonzero on a failed
assertion. This is local regression evidence, not production certification.

## Run

```sh
node e2e/auth-cookie-races/reproduce.mjs --require-safe
BROWSER=webkit node e2e/auth-cookie-races/reproduce.mjs --require-safe
```

Chromium is the default; only `chromium` and `webkit` are allowed. Playwright
engines and project dependencies must already be installed. `PYTHON` may name the
Python executable. `PLAYWRIGHT_BROWSERS_PATH` may locate an isolated engine cache.
The script accepts no server or database target. All servers use ephemeral
loopback ports, so it does not use the regular browser workflow's ports.

The fixture overrides inherited database, JWT, and cookie settings before app
imports, uses a fresh temporary SQLite database and synthetic `example.com`
accounts, blocks external browser requests, and never prints credentials. It
loads neither Vite environment files nor full-app schedulers. It uses
`create_all`; migration tests are a separate gate. Servers, browser contexts,
and temporary data are removed at completion.

A native HTTP proxy holds response bytes before the browser can apply
`Set-Cookie`. The actual auth/switch-org routes, client, AuthProvider, cookies,
and Web Locks run together. Expired-access probes return controlled 401s without
replacing the original signed identity. Queue assertions observe a pending Web
Lock, then release the held response. A watchdog failure is a test failure, never
proof of serialization.

## Wire contract

Cooperating clients serialize auth transitions with an exclusive Web Lock scoped
to the frontend origin/storage bucket and API origin. They persist only
`{id: UUID, epoch: nonnegative safe integer}` under
`buildsignals.browser-session.v1:<API origin>`. No tokens, user IDs, or workspace
IDs are stored there. The metadata is not secret and never authorizes a request.

Login, registration, refresh, logout, logout-all, account deletion, and workspace
switch requests send:

```text
X-Browser-Protocol: 1
X-Browser-Id: <UUID>
X-Browser-Epoch: <integer>
```

The server's CORS allowlist includes these headers. Login, registration, and
switch-org issue the existing TokenResponse fields; there are no new top-level
JSON fields. Their signed access and refresh JWTs contain:

| Claim | Meaning |
| --- | --- |
| `sid` | Persisted browser-family row ID |
| `sg` | Server generation, rotated at an identity transition |
| `bid` | Non-secret browser ID binding |
| `be` | Non-secret client epoch binding |

JWT `sub`, `org_id`, `tv`, expiry, and signature remain required. Business
authorization checks the current active user, active organization, membership,
token version, and family. Knowing `bid` or editing storage never supplies a
credential. Switching an existing browser family to another account requires
fresh password/MFA authentication and possession of its signed family cookie.
Same-account password/MFA login can recover after cookie loss.

## Persistence and response ordering

`browser_sessions` has a unique browser ID, nullable user/organization FKs,
generation, client epoch, revocation flag, absolute expiry, and timestamps.
Identity issuance/revocation locks that row (`FOR UPDATE` in PostgreSQL; a
no-op UPDATE acquires the SQLite write lock). Tokens from earlier generations
fail closed even if a late response replaces the browser's cookie slot.
Timezone-aware database expiries are converted to UTC, not relabeled as UTC.

Only successful login, registration, and switch-org send `Set-Cookie`. Refresh,
auth failures, ordinary logout, logout-all, and account deletion **never expire
or overwrite a cookie**. Refresh mints access only; family expiry is absolute,
not sliding (the configured refresh lifetime, currently 14 days). All auth
responses are non-cacheable. Ordinary logout revokes just its browser family;
logout-all explicitly increments the user's token version across all devices.
Deleted/inactive users cannot authenticate even if old cookies remain in a jar.

Logout also presents the captured signed access identity and must match the
persisted family's user, workspace, generation, and epoch. A present valid cookie
must agree; a missing cookie does not prevent revoking the captured family, since
an old response could still deliver it later. An old queued logout cannot
consume a newer login cookie. Expired access is accepted only as this signed
logout possession proof, never for business authorization. Epoch and captured
identity checks happen inside the Web Lock **before storage changes or dispatch**.
AuthContext retires its state before deliberate login/register/switch/logout;
storage events retire other tabs rather than adopting their credentials.

Automatic retries compare the original signed-token identity with the refreshed
identity, including user, workspace, family, generation, and epoch. Business
requests with no parseable original identity never refresh or retry. Only
`GET /auth/me` can bootstrap anonymously. No mutation is replayed into another
workspace. The current deletion API remains `POST /auth/delete-account`.

## Positive cases

1. Old refresh versus newer login: reload retains the newer identity.
2. Old logout versus newer login: reload retains the newer identity.
3. Old refresh versus logout: reload stays signed out.
4. Old failed refresh versus password recovery: newer session survives.
5. Cross-tab login: the old tab retires its identity.
6. Workspace switch: old-context mutation is not replayed; reload restores only
   the deliberately selected workspace.
7. Queued cross-tab switch: rejected before dispatch or epoch update.
8. Queued cross-tab logout: cannot revoke or invalidate the newer login.
9. In-flight old-identity mutation: only its original dispatch occurs.
10. Opaque/no-token mutations: neither refresh nor replay occurs.
11. Independent device: ordinary logout leaves its family authenticated.
12. Different frontend origins: cookie/browser-ID mismatch requires relogin;
    an old request cannot migrate to the other origin's identity.

Unit/route tests additionally cover malformed headers, missing locks/storage,
bounded lock acquisition and timer cleanup, forged browser IDs, spliced signed
claims, timezone normalization, logout-all/deletion without cookie clearing,
stale access revocation, workspace membership checks, and CORS preflight.

## Compatibility, rollout, and limits

- Apply additive migration `20260910_0001` before serving this backend. Its
  standalone parent is `20260908_0001`; the release integrator will retarget this
  unreleased migration to the MFA migration head after merging that branch.
  Do not deploy two heads. No existing data is rewritten. Downgrade refuses to
  discard populated browser-family revocation state; empty-schema reversibility
  is tested separately.
- Deploy backend/frontend as one protocol release. Old auth clients receive 426
  and must reload/sign in. Legacy refresh tokens cannot mint new access. Already
  signed legacy access tokens are accepted only for their remaining bounded
  lifetime (at most 15 minutes); global active-user/org/token-version checks
  still apply. All public token issuers now create bound tokens. Browser-family
  revocation only applies to bound tokens during that short compatibility window.
- Web Locks, secure-context UUID generation, and usable site storage are required.
  Missing support or storage denial fails closed with an actionable error.
  Lock acquisition and auth fetch/body processing have 30-second deadlines and
  clear their timers. Aborted/unloaded documents cannot guarantee cookie delivery;
  persisted generations ensure stale delivered cookies cannot restore identity.
  Navigation/abort scheduling is not a dedicated browser case in this gate.
- Two frontend origins do not share Web Locks/storage. If they share one API
  cookie, they can force each other to reauthenticate on `bid` mismatch. Use one
  canonical frontend origin or isolate cookie scopes; do not promise seamless
  cross-origin sessions. Independent browser/device profiles have separate rows.
- An in-flight authorized business operation may already have committed before
  revocation; discarding its response is not cancellation. Failed-network logout
  clears local state but cannot prove server revocation. A copied valid cookie
  retains authority until its family/token version expires or is revoked.
- The family table is an authentication table, not tenant business data. Public
  APIs must never expose it by browser ID. One row per browser family avoids
  per-refresh row growth. Retention/cleanup must preserve revocation guarantees;
  there is no automatic history purge in this release.
- SQLite and Chromium results are not PostgreSQL or cross-engine certification.
  The integration owner must run PostgreSQL concurrency/migration checks, the
  second-engine gate, combined MFA regressions, and production restore/config
  evidence before release. No production deployment is performed by this work.

## Account deletion invariant

Deletion counts only other **active** administrators and locks membership parent
organizations in sorted order before locking the user, matching member-mutation
locking. It rechecks credentials, membership sets, and roles, then commits the
audit record and deletion atomically. Memberships acquired during lock acquisition
produce a retryable 409 rather than an out-of-order lock. Independent-connection
SQLite deletion/demotion tests cover the invariant; PostgreSQL evidence remains
a separate integration gate. Out-of-band membership writes must honor the same
locking invariant.
