"""Nationwide ranked-cohort endpoint: surfaces the full research growth ranking
the model already computes, with a coverage flag for local evidence."""
from app.services import investment_areas as areas


def snapshot():
    # 20 eligible metros (MIN_COHORT) with varied price momentum so ranks are
    # distinct; 36100 is the one metro with a declared local evidence source.
    metros = [{"cbsa": "36100", "name": "Ocala, FL", "hpi": {2023: 100, 2025: 112},
               "units": {2022: 100, 2023: 100, 2024: 100, 2025: 110}},
              {"cbsa": "45300", "name": "Tampa, FL", "hpi": {2023: 100, 2025: 130},
               "units": {2022: 100, 2023: 100, 2024: 100, 2025: 110}}]
    for i in range(18):
        metros.append({"cbsa": f"{10000+i}", "name": f"Synthetic {10000+i}",
                       "hpi": {2023: 100, 2025: 104 + i},
                       "units": {2022: 100, 2023: 100, 2024: 100, 2025: 110}})
    return {"year": 2025, "captured_at": "2026-11-10T07:00:00+00:00", "snapshot_id": "a" * 64,
            "provenance": [{"url": "https://www.fhfa.gov/private-file.csv", "sha256": "b" * 64,
                            "period": "2025", "captured_at": "2026-11-10T07:00:00+00:00"}],
            "metros": metros}


def register(client, email):
    email = email.replace("@example.test", "@example.com")
    response = client.post("/auth/register", json={"email": email,
        "password": "CorrectHorseBattery42", "full_name": "Synthetic Reviewer",
        "organization_name": email.split("@")[0]})
    assert response.status_code == 201, response.text
    return response.json()


def test_ranked_surfaces_full_cohort_ordered_with_coverage_flag():
    out = areas.ranked_markets(snapshot=snapshot())
    assert out["cohort_size"] == 20
    assert out["status"] == "research"
    assert out["local_evidence_metros"] == 1
    ranks = [m["rank"] for m in out["markets"]]
    assert ranks == sorted(ranks) and ranks[0] == 1
    scores = [m["score"] for m in out["markets"]]
    assert scores == sorted(scores, reverse=True)      # best growth first
    assert out["markets"][0]["cbsa"] == "45300"        # strongest momentum
    ocala = next(m for m in out["markets"] if m["cbsa"] == "36100")
    assert ocala["has_local_evidence"] is True
    assert all(m["has_local_evidence"] is False for m in out["markets"] if m["cbsa"] != "36100")


def test_ranked_filters_by_name_or_cbsa_and_paginates():
    byname = areas.ranked_markets(snapshot=snapshot(), query="ocala")
    assert [m["cbsa"] for m in byname["markets"]] == ["36100"] and byname["matched"] == 1
    bycode = areas.ranked_markets(snapshot=snapshot(), query="45300")
    assert [m["cbsa"] for m in bycode["markets"]] == ["45300"]
    page = areas.ranked_markets(snapshot=snapshot(), limit=5, offset=5)
    assert len(page["markets"]) == 5 and page["markets"][0]["rank"] == 6
    assert page["limit"] == 5 and page["offset"] == 5


def test_ranked_never_leaks_internal_source_or_provenance_detail():
    import json
    body = json.dumps(areas.ranked_markets(snapshot=snapshot()))
    for internal in ("fhfa.gov", "private-file.csv", "ocala_fl_gis_new_building_projects"):
        assert internal not in body


def test_http_ranked_requires_login_and_is_not_cached(client, monkeypatch):
    monkeypatch.setattr(areas, "current_snapshot", snapshot)
    assert client.get("/v1/investment-areas/ranked").status_code == 401
    user = register(client, "ranked-a@example.test")
    response = client.get("/v1/investment-areas/ranked?limit=3",
        headers={"Authorization": f"Bearer {user['access_token']}"})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["cohort_size"] == 20 and len(body["markets"]) == 3
    assert body["markets"][0]["rank"] == 1


def test_http_ranked_input_failure_is_clean_retryable_503(client, monkeypatch):
    def fail():
        raise RuntimeError("private upstream debug detail")
    monkeypatch.setattr(areas, "current_snapshot", fail)
    user = register(client, "ranked-fail@example.test")
    response = client.get("/v1/investment-areas/ranked",
        headers={"Authorization": f"Bearer {user['access_token']}"})
    assert response.status_code == 503 and response.headers["Retry-After"] == "60"
    assert "private" not in response.text
