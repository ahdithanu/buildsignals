"""Shared failed-login lockouts, with bounded process-local development state.

Ten failures within a 30-minute observation window lock an account for another
30 minutes. Blocked attempts never extend that lock. Login admission budgets
separately bound concurrent attempts and are never reset by successful login.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict

from app.services.rate_limiter import RateLimitUnavailable, RedisRateLimiter, redis_key

# Tunables — conservative on purpose. 10 attempts covers fat-finger,
# password manager re-fills, and the user trying a few old passwords.
# Anything beyond that looks like an attack.
MAX_ATTEMPTS = 10
LOCK_WINDOW = 30 * 60  # 30 minutes


@dataclass
class _Entry:
    failures: int
    locked_until: float  # monotonic epoch; 0 when not locked
    expires_at: float


class AccountLockout:
    """Counts consecutive failures per email and freezes after the cap."""

    def __init__(self, *, max_entries: int = 100_000) -> None:
        self._entries: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    @staticmethod
    def _key(email: str) -> str:
        return email.strip().lower()

    def is_locked(self, email: str) -> tuple[bool, int]:
        """Return (locked, retry_after_seconds).

        retry_after is 0 when not locked. Expired locks self-heal here so
        callers don't have to know the cleanup rules.
        """
        key = self._key(email)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if not entry or not entry.locked_until or entry.expires_at <= now:
                if entry and entry.expires_at <= now:
                    self._entries.pop(key, None)
                return False, 0
            retry = max(1, math.ceil(entry.locked_until - now))
            return True, retry

    def record_failure(self, email: str) -> int:
        """Increment the failure counter; lock when we hit MAX_ATTEMPTS.

        Returns the new failure count (post-increment). The route doesn't
        actually need it but it's handy for logging/tests.
        """
        key = self._key(email)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._max_entries:
                    self._entries = {k: v for k, v in self._entries.items() if v.expires_at > now}
                    if len(self._entries) >= self._max_entries:
                        raise RateLimitUnavailable("Authentication protection unavailable")
            if entry is None or entry.expires_at <= now:
                entry = _Entry(failures=0, locked_until=0.0, expires_at=now + LOCK_WINDOW)
            if entry.locked_until:
                return entry.failures
            entry.failures += 1
            if entry.failures >= MAX_ATTEMPTS:
                entry.locked_until = now + LOCK_WINDOW
                entry.expires_at = entry.locked_until
            self._entries[key] = entry
            return entry.failures

    def reset(self, email: str) -> None:
        """Clear the counter after a successful login."""
        key = self._key(email)
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Wipe all state. Tests only."""
        with self._lock:
            self._entries.clear()


class RedisAccountLockout(RedisRateLimiter):
    """Failure transitions are atomic and shared across all API workers."""

    _RECORD = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then ttl = tonumber(ARGV[2]) end
if count < tonumber(ARGV[1]) then
    count = count + 1
    if count == tonumber(ARGV[1]) then ttl = tonumber(ARGV[2]) end
end
redis.call('SET', KEYS[1], count, 'PX', math.max(1, ttl))
return count
"""
    _STATUS = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if count > 0 and ttl < 0 then
    ttl = tonumber(ARGV[1])
    redis.call('PEXPIRE', KEYS[1], ttl)
end
return {count, ttl}
"""

    @staticmethod
    def _key(email: str) -> str:
        return redis_key("lockout", AccountLockout._key(email))

    def is_locked(self, email: str) -> tuple[bool, int]:
        try:
            count, ttl = self._client.eval(self._STATUS, 1, self._key(email), LOCK_WINDOW * 1000)
            count, ttl = int(count), int(ttl)
            if count < 0 or (count and ttl < 0):
                raise ValueError("Invalid counter response")
            return (True, max(1, math.ceil(ttl / 1000))) if count >= MAX_ATTEMPTS else (False, 0)
        except (self._redis_err, ValueError, TypeError):
            raise RateLimitUnavailable("Authentication protection unavailable") from None

    def record_failure(self, email: str) -> int:
        try:
            count = int(self._client.eval(self._RECORD, 1, self._key(email), MAX_ATTEMPTS, LOCK_WINDOW * 1000))
            if count < 1:
                raise ValueError("Invalid counter response")
            return count
        except (self._redis_err, ValueError, TypeError):
            raise RateLimitUnavailable("Authentication protection unavailable") from None

    def reset(self, email: str) -> None:
        try:
            self._client.delete(self._key(email))
        except self._redis_err:
            raise RateLimitUnavailable("Authentication protection unavailable") from None


class UnavailableAccountLockout:
    def is_locked(self, email: str) -> tuple[bool, int]:
        raise RateLimitUnavailable("Authentication protection unavailable")

    def record_failure(self, email: str) -> int:
        raise RateLimitUnavailable("Authentication protection unavailable")

    def reset(self, email: str) -> None:
        raise RateLimitUnavailable("Authentication protection unavailable")

    def clear(self) -> None:
        raise RuntimeError("No shared backend configured")


def _build_lockout():
    url = os.environ.get("REDIS_URL", "").strip()
    if url:
        try:
            return RedisAccountLockout(url)
        except (ImportError, ValueError):
            return UnavailableAccountLockout()
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
        return UnavailableAccountLockout()
    return AccountLockout()


lockout = _build_lockout()
