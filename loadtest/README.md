# Load testing

A [locust](https://locust.io) harness that drives a realistic user journey
against the DealSignal API: register → login → browse deals / dashboard,
with occasional writes. Read-heavy on purpose — that's the real traffic
shape.

## Setup

```bash
pip install locust        # not a runtime dependency; install separately
```

## Running

```bash
# Boot the API against a wipeable database (NEVER production).
uvicorn app.main:app --port 8000

# Headless: 50 users, spawn 5/s, 2 minutes.
locust -f loadtest/locustfile.py --host http://localhost:8000 \
    --headless -u 50 -r 5 -t 2m

# Or the web UI at http://localhost:8089:
locust -f loadtest/locustfile.py --host http://localhost:8000
```

Point `--host` at **staging**, never production. Each virtual user registers
its own throwaway org, so a run leaves orphaned data behind — use a database
you can drop.

## Rate limits will throttle you (by design)

All virtual users share one source IP (the load generator's), and the API
rate-limits `/auth/register` per IP (default 5/hour) and `/auth/login` per
email+IP (default 10/15min). Past a handful of users you'll see a wall of
`429 Too Many Requests` on register, then cascading `401`s from users that
never got a token.

That's the anti-abuse guard working — but it makes single-IP capacity
testing useless out of the box. Raise the auth limits for the load-test
environment (every policy is env-overridable as of the rate-limiter
policy change; production keeps the safe defaults):

```bash
LOGIN_RATE_LIMIT=100000 \
REGISTER_RATE_LIMIT=100000 \
REFRESH_RATE_LIMIT=100000 \
GLOBAL_RATE_LIMIT=1000000 \
uvicorn app.main:app --port 8000
```

Do this ONLY on a throwaway load-test environment. Never raise these on
a real deployment — the limits are load-bearing security controls there.

## What to watch

- **p95 / p99 latency** per endpoint (locust reports these). Watch the
  dashboard aggregates and `POST /deals` — writes hit the DB hardest.
- **Failure rate.** Once auth limits are raised, a non-trivial failure
  rate points at a real bottleneck (connection pool exhaustion, slow
  query) rather than the rate limiter.
- **DB connections.** With the process-local rate limiter and a single
  worker, the ceiling is usually the SQLAlchemy pool or Postgres
  `max_connections`, not CPU.
