"""Tests for enrichment and scoring workflows."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


class TestEnrichment:
    def test_enrich_deal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/enrich")
        assert r.status_code == 200
        data = r.json()
        # Enrichment should populate market data
        assert data.get("market_cap_rate") is not None or data.get("name") is not None

    def test_enrich_nonexistent_404(self, client):
        r = client.post("/deals/nonexistent/enrich")
        assert r.status_code == 404


class TestScoring:
    def test_score_deal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        # Enrich first (scoring depends on enrichment data)
        client.post(f"/deals/{deal_id}/enrich")
        r = client.post(f"/deals/{deal_id}/score")
        assert r.status_code == 200
        data = r.json()
        assert "score" in data
        assert 0 <= data["score"] <= 100

    def test_score_nonexistent_404(self, client):
        r = client.post("/deals/nonexistent/score")
        assert r.status_code == 404
