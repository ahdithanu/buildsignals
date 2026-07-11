"""Verify Sentry stays a no-op when SENTRY_DSN is unset.

Importing app.main must not pull in sentry_sdk or attempt any network call.
"""
import os
import sys


def test_sentry_not_initialized_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    # Force a fresh import so the top-level SENTRY_DSN check re-runs.
    for mod in [m for m in list(sys.modules) if m == "app.main"]:
        del sys.modules[mod]

    # sentry_sdk may or may not be installed in the test env; either way, the
    # import of app.main must succeed without touching it when DSN is unset.
    sentry_before = sys.modules.get("sentry_sdk")

    import app.main  # noqa: F401

    # If sentry_sdk wasn't already imported elsewhere, app.main shouldn't have
    # imported it either.
    if sentry_before is None:
        assert "sentry_sdk" not in sys.modules, (
            "app.main imported sentry_sdk despite SENTRY_DSN being unset"
        )

    # And the env var is really unset.
    assert os.environ.get("SENTRY_DSN") is None
