"""The appreciation layer is a backtest GATE, not a forecast. These tests pin
that it withholds any projection until the signal shows out-of-sample skill, and
that the packaged single-vintage reference can never clear that gate."""
from app.services import appreciation as appr
from app.services import investment_areas as areas


def test_rank_correlation_is_monotonic_and_none_without_variation():
    rising = [(i, i * 2.0) for i in range(10)]
    falling = [(i, -i * 2.0) for i in range(10)]
    assert round(appr.rank_correlation(rising), 6) == 1.0
    assert round(appr.rank_correlation(falling), 6) == -1.0
    assert appr.rank_correlation([(1, 5), (2, 5), (3, 5)]) is None   # no y variation
    assert appr.rank_correlation([(1, 2)]) is None                   # too few points


def test_backtest_insufficient_with_too_few_observations():
    obs = [{"signal": i / 10, "realized_return": i / 100, "horizon_years": 2}
           for i in range(10)]            # below MIN_OBSERVATIONS_PER_HORIZON
    report = appr.backtest(obs)
    assert report["status"] == "insufficient_history"
    assert report["observation_count"] == 10
    assert report["horizons"][0]["calibrated"] is False


def test_backtest_calibrated_only_with_skillful_out_of_sample_signal():
    # 40 metros where realized forward return tracks the as-of signal.
    skillful = [{"signal": i / 40, "realized_return": i / 40 * 0.1 + (i % 3) * 0.001,
                 "horizon_years": 2} for i in range(40)]
    report = appr.backtest(skillful)
    assert report["status"] == "calibrated"
    horizon = report["horizons"][0]
    assert horizon["observations"] == 40
    assert horizon["rank_correlation"] >= appr.MIN_RANK_CORRELATION
    assert horizon["tercile_lift"] > 0

    # Same count, but the signal is pure noise versus realized return.
    noise = [{"signal": (i * 7) % 40, "realized_return": (i * 13) % 40 * -0.01,
              "horizon_years": 2} for i in range(40)]
    assert appr.backtest(noise)["status"] == "insufficient_history"


def test_observations_need_three_vintages_for_disjoint_windows():
    # Two HPI vintages (the momentum pair) yield no out-of-sample observation.
    single_pair = {"metros": [{"hpi": {2023: 100.0, 2025: 110.0}}]}
    assert appr.observations_from_snapshot(single_pair) == []

    # Three vintages yield one disjoint (signal, realized) observation per metro.
    three = {"metros": [{"hpi": {2021: 100.0, 2023: 110.0, 2025: 121.0}}]}
    obs = appr.observations_from_snapshot(three)
    assert len(obs) == 1
    assert round(obs[0]["signal"], 4) == 0.1 and round(obs[0]["realized_return"], 4) == 0.1
    assert obs[0]["horizon_years"] == 2


def test_appreciation_outlook_reports_insufficient_history_on_single_vintage():
    snapshot = {"metros": [{"hpi": {2023: 100.0, 2025: 110.0 + i}} for i in range(40)]}
    out = appr.appreciation_outlook(snapshot, "36100")
    assert out["status"] == "insufficient_history"
    assert out["calibration"]["observation_count"] == 0
    assert "multi-vintage HPI history is required" in out["required"]


def test_appreciation_service_disabled_by_default_keeps_preview(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "APPRECIATION_OUTLOOK_ENABLED", False)
    out = areas.appreciation(None, "36100", snapshot={"metros": []})
    assert out["status"] == "disabled"
    assert out["projection"]["status"] == "research_preview"


def test_appreciation_service_enabled_withholds_projection_without_backtest(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "APPRECIATION_OUTLOOK_ENABLED", True)
    snapshot = {"metros": [{"hpi": {2023: 100.0, 2025: 112.0}}]}
    out = areas.appreciation(None, "36100", snapshot=snapshot)
    assert out["status"] == "insufficient_history"
    assert out["calibration"]["status"] == "insufficient_history"
    assert out["projection"]["status"] == "research_preview"   # still no forecast
