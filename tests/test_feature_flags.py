"""Feature flag helper."""
from __future__ import annotations

import pytest

from app.utils.feature_flags import is_enabled


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " true "])
def test_truthy_values_enable_flag(monkeypatch, value):
    monkeypatch.setenv("FEATURE_MY_THING", value)
    assert is_enabled("my_thing") is True
    # Case-insensitive name match too.
    assert is_enabled("MY_THING") is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
def test_falsy_values_disable_flag(monkeypatch, value):
    monkeypatch.setenv("FEATURE_MY_THING", value)
    assert is_enabled("my_thing") is False


def test_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("FEATURE_MY_THING", raising=False)
    assert is_enabled("my_thing") is False


def test_reads_env_every_call(monkeypatch):
    """No caching — flags respond to env changes without a restart."""
    monkeypatch.delenv("FEATURE_TOGGLED", raising=False)
    assert is_enabled("toggled") is False
    monkeypatch.setenv("FEATURE_TOGGLED", "true")
    assert is_enabled("toggled") is True
