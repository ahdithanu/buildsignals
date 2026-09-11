"""Fixed-window budgets. Authentication uses required=True and fails closed.

Redis counters and expiry are changed in one atomic script. Local development
can use bounded in-process counters; production never substitutes those for a
missing shared backend. Noncritical traffic limits retain fail-open behavior.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

log = logging.getLogger(__name__)


class RateLimitUnavailable(RuntimeError):
    """A required abuse-prevention decision could not be made."""


def redis_key(kind: str, key: str) -> str:
    # Do not put raw email addresses, IPs, or user IDs into Redis key names.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"buildsignals:abuse:v1:{kind}:{digest}"


def _unavailable(required: bool, limit: int) -> RateLimitDecision:
    if required:
        raise RateLimitUnavailable("Authentication protection unavailable")
    return RateLimitDecision(allowed=True, remaining=max(0, limit), retry_after=0)


def _valid_policy(limit: int, window_seconds: int) -> bool:
    return type(limit) is int and type(window_seconds) is int and limit > 0 and window_seconds > 0


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int  # seconds until the next allowed call; 0 when allowed


class InMemoryRateLimiter:
    """Fixed-window counter, process-local. Default when REDIS_URL is unset."""

    def __init__(self, *, max_buckets: int = 100_000) -> None:
        # key -> (expiry_monotonic, count)
        self._buckets: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._max_buckets = max_buckets

    def check(self, *, key: str, limit: int, window_seconds: int, required: bool = False) -> RateLimitDecision:
        """Record a hit against `key`. Returns whether it should proceed."""
        if not _valid_policy(limit, window_seconds):
            return _unavailable(required, limit)

        now = time.monotonic()
        with self._lock:
            if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                self._buckets = {k: v for k, v in self._buckets.items() if v[0] > now}
                if len(self._buckets) >= self._max_buckets:
                    return _unavailable(required, limit)
            expiry, count = self._buckets.get(key, (now + window_seconds, 0))
            if expiry <= now:
                expiry, count = now + window_seconds, 0
            count = min(count + 1, limit + 1)
            self._buckets[key] = (expiry, count)

            if count > limit:
                retry = max(1, math.ceil(expiry - now))
                return RateLimitDecision(allowed=False, remaining=0, retry_after=retry)
            return RateLimitDecision(
                allowed=True,
                remaining=max(0, limit - count),
                retry_after=0,
            )

    def reset(self, key: str, *, required: bool = False) -> None:
        """Drop a bucket — used after a successful login so the user who
        fat-fingered their password twice isn't penalized."""
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        """Wipe all state. Tests only."""
        with self._lock:
            self._buckets.clear()


class RedisRateLimiter:
    """One-key script works across independent workers without a TTL race."""

    _CHECK = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then ttl = tonumber(ARGV[2]) end
count = math.min(count + 1, tonumber(ARGV[1]) + 1)
redis.call('SET', KEYS[1], count, 'PX', math.max(1, ttl))
return {count, ttl}
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

    def check(self, *, key: str, limit: int, window_seconds: int, required: bool = False) -> RateLimitDecision:
        if not _valid_policy(limit, window_seconds):
            return _unavailable(required, limit)

        try:
            count, ttl = self._client.eval(
                self._CHECK, 1, redis_key("rate", key), limit, window_seconds * 1000,
            )
            count, ttl = int(count), int(ttl)
            if count < 1 or ttl < 0:
                raise ValueError("Invalid counter response")
        except (self._redis_err, ValueError, TypeError):
            # Do not log the exception: URLs and credentials can appear in it.
            log.warning("rate_limiter: shared backend unavailable; required=%s", required)
            return _unavailable(required, limit)

        if count > limit:
            return RateLimitDecision(
                allowed=False, remaining=0, retry_after=max(1, math.ceil(ttl / 1000))
            )
        return RateLimitDecision(
            allowed=True,
            remaining=max(0, limit - int(count)),
            retry_after=0,
        )

    def reset(self, key: str, *, required: bool = False) -> None:
        try:
            self._client.delete(redis_key("rate", key))
        except self._redis_err:
            log.warning("rate_limiter: shared reset unavailable; required=%s", required)
            _unavailable(required, 0)

    def clear(self) -> None:
        raise RuntimeError("Shared rate-limit state cannot be cleared; use an isolated test backend")


class UnavailableRateLimiter:
    """Missing production configuration must not become per-worker protection."""

    def check(self, *, key: str, limit: int, window_seconds: int, required: bool = False) -> RateLimitDecision:
        return _unavailable(required, limit)

    def reset(self, key: str, *, required: bool = False) -> None:
        _unavailable(required, 0)

    def clear(self) -> None:
        raise RuntimeError("No shared backend configured")


def _build_limiter():
    """Pick a backend based on env. Called once at import time."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
            return UnavailableRateLimiter()
        return InMemoryRateLimiter()
    try:
        return RedisRateLimiter(url)
    except (ImportError, ValueError):
        log.warning(
            "rate_limiter: configured shared backend could not be initialized"
        )
        return UnavailableRateLimiter()


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

# These admission budgets are not reset by successful logins. They also bound
# in-flight attempts that have not yet contributed to consecutive-failure locks.
LOGIN_IP_LIMIT = _int_env("LOGIN_IP_RATE_LIMIT", 100)
LOGIN_ACCOUNT_LIMIT = _int_env("LOGIN_ACCOUNT_RATE_LIMIT", 30)

REGISTER_LIMIT = _int_env("REGISTER_RATE_LIMIT", 5)        # attempts per IP
REGISTER_WINDOW = _int_env("REGISTER_RATE_WINDOW_SECONDS", 60 * 60)  # 1 hour

REFRESH_LIMIT = _int_env("REFRESH_RATE_LIMIT", 60)        # attempts per IP — real clients refresh rarely,
REFRESH_WINDOW = _int_env("REFRESH_RATE_WINDOW_SECONDS", 60 * 60)  # but tab storms can happen

# Per-organization rate limits on LLM-backed endpoints (generate-memo,
# enrich, score). Tuned to allow a healthy session burst without letting
# a runaway client burn the API bill.
AI_LIMIT = _int_env("AI_RATE_LIMIT", 30)
AI_WINDOW = _int_env("AI_RATE_WINDOW_SECONDS", 60)   # seconds
