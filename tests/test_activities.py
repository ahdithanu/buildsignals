"""Tests for outreach activities and follow-ups."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


SAMPLE_CONTACT = {"name": "Test Contact", "role": "Owner", "email": "t@t.com"}


class TestActivities:
    def test_create_activity(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        r = client.post(f"/deals/{deal_id}/activities", json={
            "contact_id": cid,
            "activity_type": "email",
            "subject": "Intro",
            "notes": "Sent intro email",
        })
        assert r.status_code == 201
        assert r.json()["activity_type"] == "email"

    def test_list_activities(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        client.post(f"/deals/{deal_id}/activities", json={
            "contact_id": cid, "activity_type": "call", "subject": "Follow up"
        })
        r = client.get(f"/deals/{deal_id}/activities")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_follow_ups(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        client.post(f"/deals/{deal_id}/activities", json={
            "contact_id": cid,
            "activity_type": "email",
            "subject": "Follow up",
            "follow_up_date": "2030-01-01T00:00:00Z",
        })
        r = client.get("/outreach/follow-ups")
        assert r.status_code == 200
