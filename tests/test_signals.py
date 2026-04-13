"""Tests for signals with normalization."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


class TestSignals:
    def test_create_signal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post("/signals", json={
            "deal_id": deal_id,
            "signal_type": "price_reduction",
            "source": "CoStar",
            "description": "Price cut 5%",
            "severity": 7.0,
        })
        assert r.status_code == 201
        assert r.json()["signal_type"] == "Price Reduction"  # normalized

    def test_signal_type_normalization(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cases = {
            "tenant_risk": "Tenant Risk",
            "new_construction": "New Construction",
            "lease_expiry": "Lease Expiry",
            "permit_activity": "Permit Activity",
            "zoning_update": "Zoning Update",
        }
        for raw, expected in cases.items():
            r = client.post("/signals", json={
                "deal_id": deal_id,
                "signal_type": raw,
                "source": "Test",
                "description": "Test",
                "severity": 5.0,
            })
            assert r.json()["signal_type"] == expected, f"{raw} -> {r.json()['signal_type']}, expected {expected}"

    def test_list_signals(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post("/signals", json={
            "deal_id": deal_id, "signal_type": "market", "source": "X", "description": "Y", "severity": 3.0
        })
        r = client.get("/signals")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_deal_signals(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post("/signals", json={
            "deal_id": deal_id, "signal_type": "market", "source": "X", "description": "Y", "severity": 3.0
        })
        r = client.get(f"/deals/{deal_id}/signals")
        assert r.status_code == 200
        assert len(r.json()) >= 1
