from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


_DATE_PLACEHOLDER = re.compile(r"\{utc_today(?:(?P<direction>_plus_|_minus_)(?P<days>\d+))?\}")


def resolve_connector_config_dates(
    value: Any,
    *,
    now: datetime | None = None,
) -> Any:
    """Resolve rolling UTC date placeholders in connector configuration values."""
    now = _as_utc(now or datetime.now(timezone.utc))
    if isinstance(value, dict):
        return {
            key: resolve_connector_config_dates(item, now=now)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_connector_config_dates(item, now=now) for item in value]
    if isinstance(value, str):
        return _DATE_PLACEHOLDER.sub(lambda match: _format_placeholder(match, now), value)
    return value


def _format_placeholder(match: re.Match[str], now: datetime) -> str:
    days = int(match.group("days") or 0)
    direction = match.group("direction")
    if direction == "_minus_":
        target = now - timedelta(days=days)
    else:
        target = now + timedelta(days=days)
    return target.strftime("%Y-%m-%dT00:00:00")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
