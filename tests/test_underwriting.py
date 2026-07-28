"""Tests for assumptions, outputs, and recalculation."""
from __future__ import annotations

from tests.conftest import SAMPLE_ASSUMPTIONS, SAMPLE_DEAL


class TestAssumptions:
    def test_get_default_assumptions(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.get(f"/deals/{deal_id}/assumptions")
        assert r.status_code == 200
        # Default assumptions are empty/zero
        assert r.json()["deal_id"] == deal_id

    def test_put_assumptions(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.put(f"/deals/{deal_id}/assumptions", json=SAMPLE_ASSUMPTIONS)
        assert r.status_code == 200
        data = r.json()
        assert data["purchase_price"] == 9500000
        assert data["interest_rate"] == 0.06


class TestRecalculate:
    def test_recalculate_outputs(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.put(f"/deals/{deal_id}/assumptions", json=SAMPLE_ASSUMPTIONS)
        r = client.post(f"/deals/{deal_id}/recalculate")
        assert r.status_code == 200

        # Check outputs were computed
        r = client.get(f"/deals/{deal_id}/outputs")
        assert r.status_code == 200
        data = r.json()
        assert data["noi"] is not None
        assert data["noi"] > 0
        assert data["dscr"] is not None
        assert data["cap_rate"] is not None

    def test_noi_calculation(self, client):
        """NOI = gross_rental_income * (1 - vacancy) * (1 - opex)."""
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.put(f"/deals/{deal_id}/assumptions", json=SAMPLE_ASSUMPTIONS)
        client.post(f"/deals/{deal_id}/recalculate")
        data = client.get(f"/deals/{deal_id}/outputs").json()
        expected_noi = 1200000 * (1 - 0.05) * (1 - 0.35)
        assert abs(data["noi"] - expected_noi) < 1  # within $1 rounding
