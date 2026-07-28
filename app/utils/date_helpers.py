"""Date / time utility functions."""

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    """Return a timezone-aware UTC datetime n days in the past."""
    return utcnow() - timedelta(days=n)


def format_iso(dt: datetime) -> str:
    """Return ISO-8601 string with Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
