"""In-process per-account lockout for failed logins.

The IP-based rate limiter (see `rate_limiter.py`) caps how fast any one
IP can grind on a single email+IP bucket, but a determined attacker can
spread a password-spray across many IPs and still hammer one victim's
account. This module adds a second, complementary defense: regardless of
the source IP, after `MAX_ATTEMPTS` consecutive failed logins for an
email, the account is frozen for `LOCK_WINDOW` seconds. A successful
login clears the counter.

Scope & trade-offs
------------------
- Process-local. Like the rate limiter, a multi-worker deploy gives each
  worker its own counters, so the effective threshold is N × MAX_ATTEMPTS.
  Acceptable for the pilot; revisit with Redis when we scale out.
- Not durable across restarts — a deploy resets the counter. Short
  lockout window makes this an acceptable trade.
- Keyed by lower-cased email so `Alice@x` and `alice@x` share state.

This is deliberately a separate module from `rate_limiter` because the
semantics are different (account-state vs. request-rate) and we want the
two checks to be auditable independently.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict

# Tunables — conservative on purpose. 10 attempts covers fat-finger,
# password manager re-fills, and the user trying a few old passwords.
# Anything beyond that looks like an attack.
MAX_ATTEMPTS = 10
LOCK_WINDOW = 30 * 60  # 30 minutes


@dataclass
class _Entry:
    failures: int
    locked_until: float  # monotonic epoch; 0 when not locked


class AccountLockout:
    """Counts consecutive failures per email and freezes after the cap."""

    def __init__(self) -> None:
        self._entries: Dict[str, _Entry] = {}
        self._lock = threading.Lock()

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
            if not entry or entry.locked_until <= now:
                # Lock expired — clear failures so the user starts fresh.
                if entry and entry.locked_until and entry.locked_until <= now:
                    self._entries.pop(key, None)
                return False, 0
            retry = max(1, int(entry.locked_until - now))
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
            if entry is None or (entry.locked_until and entry.locked_until <= now):
                # Fresh start, either first failure or after an expired lock.
                entry = _Entry(failures=0, locked_until=0.0)
            entry.failures += 1
            if entry.failures >= MAX_ATTEMPTS:
                entry.locked_until = now + LOCK_WINDOW
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


# Shared, process-wide instance. Import this from routes.
lockout = AccountLockout()
