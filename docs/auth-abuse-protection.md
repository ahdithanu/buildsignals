# Authentication abuse protection

Implemented locally; production rollout is gated on shared Redis and verified
proxy trust. This is not a penetration-test or availability attestation.

## Decisions and scope

- Registration, login, refresh, password recovery, and MFA verification/disable
  require a successful protection decision. An unavailable store, invalid
  nonpositive policy, or missing production Redis returns HTTP 503 with
  `Retry-After: 30` and `Cache-Control: no-store`. No new session or recovery
  message is issued on this path.
- Ordinary global traffic and AI budgets retain their existing fail-open outage
  policy. Revoking a session does not require a working rate-limit store.
- Setting `REDIS_URL` selects shared counters and account locks. Initialization
  failure never silently selects per-process counters. Without Redis,
  development uses bounded local counters; `ENVIRONMENT=production` refuses
  sensitive auth operations. Staging must also be configured with Redis to
  exercise production behavior.
- Counter updates and expiry run in single-key Redis scripts. The fixed-window
  rate counter saturates after the limit and does not slide forward on rejected
  requests. Missing expiry is repaired. Redis failures are not retried as new
  authentication attempts; an ambiguous write may consume budget, never grant
  extra budget.
- Account failure counters are shared across workers. Ten failed password/MFA
  attempts in a 30-minute observation window trigger a 30-minute lock. Requests
  blocked by an existing lock do not prolong it. Successful authentication or
  password recovery clears failure state.
- Login also has non-resettable admission budgets: 100 attempts per resolved IP
  and 30 per normalized email, each per 15 minutes by default. These complement
  the existing 10-attempt email/IP bucket and bound already-running requests
  before expensive password checks. A concurrent success can clear failure
  state but cannot clear these aggregate budgets. Lockout is not a promise that
  precisely ten parallel requests can ever enter password verification.
- MFA verification and disable share ten attempts per user per 15 minutes,
  independent of organization, session and source address. Successful operations
  do not reset this budget.
- Redis key names use a versioned namespace and SHA-256 digests rather than raw
  emails/IPs/user IDs. Digests are not anonymization. The Redis dataset remains
  sensitive operational data. Passwords, TOTP codes and tokens are never keys.
- Shared `clear()` is disabled. No `FLUSHDB`, wildcard delete, or production
  cleanup operation is exposed by these services. Local development state is
  capped at 100,000 entries per store and fails closed for sensitive requests
  at capacity rather than evicting active counters.

## Proxy boundary

Application code uses `request.client.host`, canonicalizing IP notation. It
does not reinterpret raw `X-Forwarded-For` or `Forwarded` headers. Uvicorn must
resolve client identity from explicitly trusted upstream peers, and the edge
must sanitize forwarded headers and prevent direct untrusted access through a
trusted peer. Do not set `forwarded-allow-ips=*` on an unrestricted listener.
An unconfigured proxy may group legitimate users into one IP budget; verify
the real hosting path before release, including serverless ASGI adapters.

Render, Docker and Procfile now use `python -m app.server`. In production that launcher
requires `FORWARDED_ALLOW_IPS` with reviewed IPs/CIDRs, or explicit `none` for a
direct listener; missing configuration, wildcard or collective /0 trust is rejected before
serving. Render prompts for this value rather than inventing provider CIDRs.
Other entrypoints/adapters must enforce the same reviewed boundary.

See [Uvicorn settings](https://www.uvicorn.org/settings/) and
[Redis EVAL](https://redis.io/docs/latest/commands/eval/) for the underlying
server trust and scripting interfaces.

## Release gates

1. Provision an access-controlled shared Redis for this environment; use TLS
   where traffic crosses an untrusted network. Choose `noeviction`, persistence,
   backup/HA and capacity alerts deliberately. Eviction, data loss or failover
   losing acknowledged writes can reset budgets; the application cannot infer
   those events from an empty key.
2. Allow the required Redis script/key operations for both `rate` and `lockout`
   namespaces. Keep administrative commands unavailable to the application.
3. Verify `/health/auth-protection` reports `shared`, including under the real
   application role. This probe exercises fixed synthetic rate and account-lock
   writes, reads and deletes, not real customer counters. `local` is development-only
   evidence. An outage reports 503 without backend URLs or exception details.
4. Monitor that dependency probe separately from `/health`. Do not turn a cache
   outage into an automatic application restart loop. Existing signed sessions
   may use business routes while valid, but cannot refresh during an outage.
5. Exercise login, recovery and MFA across at least two deployed workers, and
   validate proxy source addresses using controlled clients. Test outage and
   recovery without disabling enforcement. New v1 counter keys start with new
   budgets; old pre-release counters are not migrated.

## Limits

Fixed windows permit a boundary burst. Shared office IPs can consume aggregate
budgets; policy changes need measured traffic. An attacker can deliberately
consume a victim's account budget, so recovery must remain available through
its separately limited channel. These controls are not a replacement for edge
DDoS protection, bot defenses, breached-password checks or incident response.
Redis and database mutations are not a distributed transaction: a failed
database operation can consume budget or clear a failure counter after proof
of credentials. Non-resettable admission budgets remain in force.

`tests/test_auth_abuse_protection.py` covers outage responses, no-session/no-mail
side effects, forged headers, configuration failures, local concurrency and
bounded state. Real Redis verification is optional and isolated; see
`tests/test_redis_abuse_integration.py`. No production Redis or customer data is
used by those tests. CI installs a Redis binary and enables this suite; hosted
execution still needs to pass after the draft branch is pushed.
