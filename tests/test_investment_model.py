from copy import deepcopy

import pytest

from app.services.investment_model import rank_metros


def snapshot():
    return {"year": 2025, "metros": [{
        "cbsa": f"{10000+i}", "name": f"Synthetic metro {i}",
        "hpi": {2023: 100, 2025: 110+i},
        "units": {2022: 100, 2023: 100, 2024: 100, 2025: 100+i},
        "population_2024": 1000, "population_2025": 1050, "net_migration_2025": 20,
    } for i in range(20)]}


def test_exact_weights_and_nonpermit_demand_indicators():
    rows = rank_metros(snapshot())
    assert rows[0]["cbsa"] == "10019" and rows[0]["score"] == 1
    assert rows[-1]["score"] == 0
    assert rows[0]["population_growth_1yr"] == pytest.approx(.05)
    assert rows[0]["net_migration_per_1000"] == pytest.approx(20/1050*1000)
    assert rows[0]["score"] == pytest.approx(.7*rows[0]["momentum_percentile"] + .3*rows[0]["supply_percentile"])


def test_ties_and_source_order_do_not_change_ranking():
    data = snapshot()
    for row in data["metros"]:
        row["hpi"][2025] = 110
        row["units"][2025] = 100
    first = rank_metros(data)
    data["metros"].reverse()
    assert rank_metros(data) == first
    assert all(row["score"] == .5 for row in first)


def test_future_outcomes_and_local_filing_counts_cannot_change_scores():
    data = snapshot()
    original = rank_metros(data)
    for row in data["metros"]:
        row["hpi"][2026] = 999999
        row["units"][2026] = 999999
        row["municipal_permit_count"] = 999999
    assert rank_metros(data) == original


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, 0, True, None])
def test_missing_or_invalid_inputs_do_not_become_zero_scores(invalid):
    data = snapshot()
    data["metros"][0]["hpi"][2023] = invalid
    with pytest.raises(ValueError, match="cohort"):
        rank_metros(data)


def test_duplicate_cbsa_is_rejected_and_input_not_mutated():
    data = snapshot()
    original = deepcopy(data)
    rank_metros(data)
    assert data == original
    data["metros"].append(data["metros"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        rank_metros(data)
