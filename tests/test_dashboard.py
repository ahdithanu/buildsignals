"""Tests for dashboard endpoints."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


class TestDashboard:
    def _seed_deal(self, client):
        return client.post("/deals", json=SAMPLE_DEAL).json()["id"]

    def test_kpis(self, client):
        self._seed_deal(client)
        r = client.get("/dashboard/kpis")
        assert r.status_code == 200
        data = r.json()
        assert "total_deals" in data
        assert data["total_deals"] >= 1

    def test_top_opportunities(self, client):
        deal_id = self._seed_deal(client)
        # Enrich and score to make it appear in top opportunities
        client.post(f"/deals/{deal_id}/enrich")
        client.post(f"/deals/{deal_id}/score")
        r = client.get("/dashboard/top-opportunities")
        assert r.status_code == 200

    def test_pipeline_snapshot(self, client):
        self._seed_deal(client)
        r = client.get("/dashboard/pipeline-snapshot")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_recent_signals(self, client):
        deal_id = self._seed_deal(client)
        client.post("/signals", json={
            "deal_id": deal_id, "signal_type": "market", "source": "X",
            "description": "Y", "severity": 3.0
        })
        r = client.get("/dashboard/recent-signals")
        assert r.status_code == 200

    def test_ai_insights(self, client):
        self._seed_deal(client)
        r = client.get("/dashboard/ai-insights")
        assert r.status_code == 200
