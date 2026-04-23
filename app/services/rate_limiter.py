"""In-process sliding-window rate limiter.

Used to slow down credential-stuffing and registration-abuse on the
public /auth/* endpoints. This is deliberately simple — one bucket per
(key, scope) tuple, held in a module-level dict, evicted lazily.

Scope & trade-offs
------------------
- Process-local. A multi-worker deploy (e.g. gunicorn -w 4) will give
  each worker its own buckets, so the effective limit is N × configured.
  Acceptable for the pilot; revisit with Redis once we scale horizontally.
- Not durable across restarts. Attackers can reset their budget by
  waiting for a deploy, but the window is already short (minutes).
- Keyed by the caller's choice — typically `ip:path` for public endpoints
  or `email:path` for credential-stuffing-specific guards.

The limiter exposes `check()` which returns a decision dataclass so the
route can surface a 429 with Retry-After instead of raising deep in
middleware where the response headers are harder to shape.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int  # seconds until the next allowed call; 0 when allowed


class RateLimiter:
    """Fixed-window counter. Cheap, predictable, good enough for auth."""

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


# Shared, process-wide instance. Import this from routes.
limiter = RateLimiter()


# ── Policies ──────────────────────────────────────────────────────────────
#
# One place to tune the knobs. Numbers are conservative on purpose — a real
# user typically types their password 1–2 times, not 10, and registration
# is even rarer. If we start blocking legitimate users we loosen these,
# not drop the guard entirely.

LOGIN_LIMIT = 10          # attempts per email+IP combo
LOGIN_WINDOW = 15 * 60    # 15 minutes

REGISTER_LIMIT = 5        # attempts per IP
REGISTER_WINDOW = 60 * 60 # 1 hour

REFRESH_LIMIT = 60        # attempts per IP — real clients refresh rarely,
REFRESH_WINDOW = 60 * 60  # but tab storms can happen
