# Isolated Redis Auth-Abuse Verification

These optional integration tests use a real Redis server, not a fake backend.
They exercise the service classes directly, not HTTP routes or production
configuration. Existing unit and route tests remain necessary.

## Run

From `/private/tmp/buildsignals-enterprise-workflows`:

```sh
REDIS_URL='' \
REDIS_SERVER_BINARY=/absolute/path/to/redis-server \
PYTHONPATH=/private/tmp/buildsignals-security-pg.clHLMu/crypto-runtime:. \
/opt/anaconda3/bin/python scripts/verify_auth_abuse.py
```

`REDIS_SERVER_BINARY` must point to an executable Redis 7+ binary. Without that
variable, these tests skip. An invalid configured binary fails visibly. No
automatic downloads, package installs, Docker, or external services occur.
The project already includes pytest and redis-py; no dependencies are added.

The runner clears `REDIS_URL` **before pytest loads conftest or the app**. For
direct pytest invocation, explicitly set `REDIS_URL=''` as above. The fixture
rejects a nonempty value but cannot undo imports that happened in conftest.
It never derives a connection from `REDIS_URL`.

## Isolation And Cleanup

- Every test starts its own foreground subprocess on `127.0.0.1` with a random
  ephemeral port, random password, and a fresh `TemporaryDirectory`.
- No config file is loaded. RDB snapshots and AOF persistence are disabled.
- Before connecting, the fixture checks readiness in its child's log. It then
  verifies the Redis process ID, directory, loopback binding, persistence
  settings, and empty database. A port collision fails without adopting another
  server.
- Tests only create synthetic `example.test` account data. Sentinels and
  intentionally corrupted keys belong exclusively to the disposable child.
- Teardown closes connections, terminates and reaps only the owned process,
  kills that process if graceful termination times out, and removes its directory.
  It checks that no RDB or AOF files were produced. It never sends `FLUSHDB`,
  `FLUSHALL`, or a shutdown command to an external server.
- The lifecycle test explicitly verifies process exit and directory removal.
  Outage tests stop their own child before checking fail-closed behavior.

Normal assertion failures and pytest interruption run fixture cleanup. A hard
kill of the test runner or host cannot guarantee Python finalizers execute.

## Coverage

- Exactly 17 of 64 concurrent rate checks admitted across independent clients;
  correct remaining budgets, retry intervals, and a single fixed expiry.
- A real single-key `EVAL` call, checked at the client boundary and in Redis
  command statistics; namespaced SHA-256 keys without raw identity data.
- Actual rate-window expiry, no expiry extension on denied requests, and repair
  of a persisted counter that lost its TTL without restoring its budget.
- Isolated reset and disabled rate-limiter `clear()`, preserving unrelated keys.
- Redis wrong-type errors and server-stop errors: required rate checks/resets
  raise `RateLimitUnavailable`; optional rate operations retain fail-open behavior.
- Shared account failures, normalized identities, concurrent increments,
  distributed threshold enforcement, saturated counts, observation-window expiry,
  a fresh lock window at the threshold, and no lock extension on blocked hits.
- Lockout reset isolation across accounts and the rate-limiter namespace;
  disabled lockout `clear()` preserves every key.
- Missing lockout TTL repair on reads and writes, both before and after locking.
- Lockout reads/writes fail closed on wrong-type data. All lockout operations
  fail closed when the owned server is stopped.

The lockout tests temporarily use `MAX_ATTEMPTS=5` and `LOCK_WINDOW=2`, restoring
the module constants afterward. One concurrency test uses a higher threshold.
TTL assertions use Redis's absolute millisecond expiry (`PEXPIRETIME`), avoiding
timing tolerances that could hide repeated extensions.

## Local Binary Provenance

No server was found in the local dependency and application locations searched.
For this verification, Redis 7.2.16 was built only under
`/private/tmp/buildsignals-redis-source.9T93dm/redis-7.2.16` using:

```sh
make -j4 MALLOC=libc BUILD_TLS=no redis-server
```

The [official release archive](https://download.redis.io/releases/redis-7.2.16.tar.gz)
was verified against the [official Redis checksum list](https://github.com/redis/redis-hashes):

```text
960a8ec15e34ff40e57ff16837b26b33bd81f2da6d24497bb63de532a323a18e
```

The resulting binary reports Redis 7.2.16, 64-bit, `malloc=libc`. No global
installation was performed. The source/build directory is a local reusable test
dependency, not a running service or persisted Redis database.

Local binary for reruns:
`/private/tmp/buildsignals-redis-source.9T93dm/redis-7.2.16/src/redis-server`.

## Verification Results

Verified on 2026-09-11 with Python 3.13.5, pytest 8.4.0, redis-py 5.0.7,
and the above Redis 7.2.16 binary. Every invocation used `REDIS_URL=''` and
the Python executable and `PYTHONPATH` shown above.

- Standalone real Redis suite: **23 passed in 9.82 seconds**.
- Combined suite with `test_auth_abuse_protection.py`, `test_account_lockout.py`,
  `test_rate_limit_policies.py`, and `test_global_rate_limit.py`:
  **78 passed in 23.90 seconds**, including all 23 real Redis tests again.
- Unset/empty binary opt-out: **23 skipped**, exit status 0.
- Deliberately nonexistent binary: expected early failure with
  `REDIS_SERVER_BINARY must be an absolute executable file path`, exit status 1.
- Ruff lint and formatting checks passed for both new Python files.
- Each successful invocation reported one existing Starlette/httpx deprecation
  warning. No dependencies were changed to suppress it.
- Runtime-directory scan after tests found no `auth-abuse-redis-*` directories.
  Each child was terminated/reaped by fixture cleanup; no RDB/AOF was produced.

The sandbox initially blocked loopback socket creation before a server started.
Successful real Redis runs used permission to open the temporary local listener.
No existing app files were edited by this harness work, and no commit, push,
deployment, paid resource, existing Redis instance, or customer data was used.
