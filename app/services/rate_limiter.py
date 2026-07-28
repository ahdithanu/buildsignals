"""Sliding-window rate limiter with pluggable backend.

Backends
--------
- `InMemoryRateLimiter` (default) — one bucket per key in a module-
  level dict. Cheap, no external deps. Correct for a single-process
  deploy; under gunicorn -w N each worker gets its own view, so the
  effective limit is N × configured. Fine for pilot / local dev.

- `RedisRateLimiter` — used automatically when `REDIS_URL` is set.
  Atomic INCR + EXPIRE for fixed-window counting; shared state across
  all workers and pods. Fails open on Redis errors (logs a warning
  and allows the request through) — rate limiting is a nicety, and
  hard-failing every request when Redis flaps is worse than briefly
  dropping the guard.

The limiter exposes `check()` which returns a decision dataclass so the
route can surface a 429 with Retry-After instead of raising deep in
middleware where the response headers are harder to shape.

Interface is shared: routes call `limiter.check(...)`, `limiter.reset(...)`,
`limiter.clear()` and don't care which backend is behind them.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int  # seconds until the next allowed call; 0 when allowed


class InMemoryRateLimiter:
    """Fixed-window counter, process-local. Default when REDIS_URL is unset."""

    def __init__(self) -> None:
        # key -> (window_start_epoch, count)
        self._buckets: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """Record a hit against `key`. Returns whether it should proceed."""
        if limit <= 0 or window_seconds <= 0:
            # Misconfiguration — fail open rather than DoS ourselves.
            return RateLimitDecision(allowed=True, remaining=limit, retry_after=0)

        now = time.monotonic()
        with self._lock:
            window_start, count = self._buckets.get(key, (now, 0))
            # Roll the window forward if we're past it.
            if now - window_start >= window_seconds:
                window_start, count = now, 0
            count += 1
            self._buckets[key] = (window_start, count)

            if count > limit:
                retry = max(1, int(window_seconds - (now - window_start)))
                return RateLimitDecision(allowed=False, remaining=0, retry_after=retry)
            return RateLimitDecision(
                allowed=True,
                remaining=max(0, limit - count),
                retry_after=0,
            )

    def reset(self, key: str) -> None:
        """Drop a bucket — used after a successful login so the user who
        fat-fingered their password twice isn't penalized."""
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        """Wipe all state. Tests only."""
        with self._lock:
            self._buckets.clear()


class RedisRateLimiter:
    """Fixed-window counter backed by Redis.

    Algorithm: INCR the key, set an EXPIRE if the key was fresh, compare
    the count to the limit. Two round-trips in a pipeline — a Lua script
    would collapse them into one, but the two-step is easier to reason
    about and the extra hop is cheap on a colocated Redis.

    Fails open on any Redis exception. This is a deliberate choice: rate
    limiting is a defensive layer, not a hard requirement for correctness.
    A Redis flap should not turn into a full-app outage.
    """

    def __init__(self, url: str) -> None:
        # Local import so the `redis` package is only required when this
        # backend is actually selected.
        import redis  # noqa: WPS433 — intentional lazy import

        # 1-second timeouts so a bad Redis doesn't stall every request.
        self._client = redis.from_url(
            url,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=False,
        )
        self._redis_err = redis.RedisError

    def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(allowed=True, remaining=limit, retry_after=0)

        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            # ttl == -1 means no TTL set (fresh key that only INCR touched);
            # ttl == -2 means key doesn't exist (shouldn't happen post-INCR).
            if ttl < 0:
                self._client.expire(key, window_seconds)
                ttl = window_seconds
        except self._redis_err as exc:
            # Fail open. Log once per class of error so a Redis outage
            # doesn't drown the app logs.
            log.warning("rate_limiter: redis error, failing open: %s", exc)
            return RateLimitDecision(allowed=True, remaining=limit, retry_after=0)

        if count > limit:
            return RateLimitDecision(
                allowed=False, remaining=0, retry_after=max(1, int(ttl))
            )
        return RateLimitDecision(
            allowed=True,
            remaining=max(0, limit - int(count)),
            retry_after=0,
        )

    def reset(self, key: str) -> None:
        try:
            self._client.delete(key)
        except self._redis_err as exc:
            log.warning("rate_limiter: redis error on reset, ignoring: %s", exc)

    def clear(self) -> None:
        """Wipe all state. Tests only — production should never call this.

        Uses FLUSHDB which will drop every key in the selected Redis DB.
        If prod and app share a Redis instance, this is destructive.
        """
        try:
            self._client.flushdb()
        except self._redis_err as exc:
            log.warning("rate_limiter: redis error on clear, ignoring: %s", exc)


def _build_limiter():
    """Pick a backend based on env. Called once at import time."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return InMemoryRateLimiter()
    try:
        return RedisRateLimiter(url)
    except ImportError:
        log.warning(
            "REDIS_URL is set but `redis` package is not installed; "
            "falling back to in-memory limiter (per-worker buckets)"
        )
        return InMemoryRateLimiter()


# Shared, process-wide instance. Import this from routes.
limiter = _build_limiter()


# ── Policies ──────────────────────────────────────────────────────────────
#
# One place to tune the knobs. Numbers are conservative on purpose — a real
# user typically types their password 1–2 times, not 10, and registration
# is even rarer. If we start blocking legitimate users we loosen these,
# not drop the guard entirely.
#
# Each limit is env-overridable so a load-test environment (many virtual
# users behind one IP) or a temporary ops adjustment can raise them without
# a redeploy. Defaults are the production-safe values. See loadtest/README.


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("rate_limiter: %s=%r is not an int, using default %d", name, raw, default)
        return default


LOGIN_LIMIT = _int_env("LOGIN_RATE_LIMIT", 10)          # attempts per email+IP combo
LOGIN_WINDOW = _int_env("LOGIN_RATE_WINDOW_SECONDS", 15 * 60)    # 15 minutes

REGISTER_LIMIT = _int_env("REGISTER_RATE_LIMIT", 5)        # attempts per IP
REGISTER_WINDOW = _int_env("REGISTER_RATE_WINDOW_SECONDS", 60 * 60)  # 1 hour

REFRESH_LIMIT = _int_env("REFRESH_RATE_LIMIT", 60)        # attempts per IP — real clients refresh rarely,
REFRESH_WINDOW = _int_env("REFRESH_RATE_WINDOW_SECONDS", 60 * 60)  # but tab storms can happen

# Per-organization rate limits on LLM-backed endpoints (generate-memo,
# enrich, score). Tuned to allow a healthy session burst without letting
# a runaway client burn the API bill.
AI_LIMIT = _int_env("AI_RATE_LIMIT", 30)
AI_WINDOW = _int_env("AI_RATE_WINDOW_SECONDS", 60)   # seconds
