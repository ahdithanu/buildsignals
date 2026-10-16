from datetime import datetime, timedelta, timezone

import pytest

from app.services.demo_seed import validate_snapshot_scope

SITE = "columbus_oh_site_engineering_applications"


def scope(start_days=15, end_days=0):
    today = datetime.now(timezone.utc).date()
    return {"start_inclusive": (today - timedelta(days=start_days)).isoformat(),
            "end_exclusive": (today - timedelta(days=end_days)).isoformat()}


def test_recent_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="Q1 2024"):
        validate_snapshot_scope(SITE, scope())
    validate_snapshot_scope(SITE, scope(), recent=True)


@pytest.mark.parametrize("start,end", [(0, 0), (32, 0), (15, -1), (61, 40), (1, 2)])
def test_recent_rejects_unbounded_future_and_stale_scopes(start, end):
    with pytest.raises(ValueError):
        validate_snapshot_scope(SITE, scope(start, end), recent=True)


def test_recent_rejects_other_sources():
    with pytest.raises(ValueError, match="site applications only"):
        validate_snapshot_scope("columbus_oh_commercial_building_permits", scope(), recent=True)


def test_historical_guard_remains_unchanged():
    validate_snapshot_scope(SITE, {"start_inclusive": "2024-01-01", "end_exclusive": "2024-04-01"})
