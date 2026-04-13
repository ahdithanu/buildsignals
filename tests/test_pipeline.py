"""Tests for pipeline stage movement and validation."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


class TestPipeline:
    def test_move_stage_forward(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/move-stage", json={"stage": "qualified"})
        assert r.status_code == 200
        assert client.get(f"/deals/{deal_id}").json()["status"] == "qualified"

    def test_move_stage_sequential(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        stages = ["qualified", "underwriting", "ic_review", "loi_sent", "closed"]
        for stage in stages:
            r = client.post(f"/deals/{deal_id}/move-stage", json={"stage": stage})
            assert r.status_code == 200
        assert client.get(f"/deals/{deal_id}").json()["status"] == "closed"

    def test_cannot_move_backward(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/move-stage", json={"stage": "underwriting"})
        r = client.post(f"/deals/{deal_id}/move-stage", json={"stage": "new"})
        assert r.status_code == 400

    def test_can_move_to_dead_from_any(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/move-stage", json={"stage": "dead"})
        assert r.status_code == 200
        assert client.get(f"/deals/{deal_id}").json()["status"] == "dead"

    def test_invalid_stage_422(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/move-stage", json={"stage": "bogus"})
        assert r.status_code == 422
