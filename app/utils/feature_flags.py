"""Env-driven feature flags.

Small on purpose. When you need to gate a code path without a redeploy,
add its name to `_KNOWN_FLAGS` and check `is_enabled("flag_name")` at
the call site.

Naming convention
-----------------
`FEATURE_<UPPER_SNAKE>` — env var read at import time. To flip a flag,
set it on Render and restart (env var changes need a service restart,
not just a config reload).

Truthy values: "1", "true", "yes", "on" (case-insensitive).
Anything else — including unset — is off. Defaulting to off means new
features are dark-shipped and the on-switch is deliberate.

Frontend mirror lives in src/lib/featureFlags.ts using VITE_FEATURE_*
env vars. Keep flag names in sync across the two — a flag toggled on
the backend but off in the UI is the recipe for a confused user.
"""
from __future__ import annotations

import os

# Registry of known flags. Not enforced (is_enabled will still return
# based on the env var if you check an unregistered name) but the source
# of truth for docs / dashboards / grep. Add a one-line comment on what
# the flag guards.
_KNOWN_FLAGS: dict[str, str] = {
    # example: "new_deal_scoring": "route inference through the v2 scoring model",
}


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_enabled(name: str) -> bool:
    """Check whether `FEATURE_<NAME>` is truthy in the environment."""
    return os.environ.get(f"FEATURE_{name.upper()}", "").strip().lower() in _TRUTHY


def all_flags() -> dict[str, bool]:
    """Snapshot of every known flag's current state. For /admin dashboards
    and structured-log context. Reads env every call — no caching, so a
    restart-free hot-reload during dev works."""
    return {name: is_enabled(name) for name in _KNOWN_FLAGS}
