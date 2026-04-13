"""Tests for contacts and the auto-advance business rule."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL


SAMPLE_CONTACT = {
    "name": "Jane Broker",
    "role": "Broker",
    "email": "jane@example.com",
    "phone": "555-1234",
    "company": "Brokerage Inc",
}


class TestContacts:
    def test_create_contact(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT)
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Jane Broker"
        assert data["status"] == "new"

    def test_list_contacts(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT)
        r = client.get(f"/deals/{deal_id}/contacts")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_update_contact_status(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        r = client.patch(f"/contacts/{cid}", json={"status": "contacted"})
        assert r.status_code == 200
        assert r.json()["status"] == "contacted"

    def test_soft_delete_contact(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        r = client.delete(f"/contacts/{cid}")
        assert r.status_code == 204
        # Should not appear in list
        contacts = client.get(f"/deals/{deal_id}/contacts").json()
        assert not any(c["id"] == cid for c in contacts)


class TestBusinessRuleAutoAdvance:
    """Business rule: when a contact is qualified, deal auto-advances from 'new' to 'qualified'."""

    def test_contact_qualified_advances_deal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        # Verify deal starts as "new"
        assert client.get(f"/deals/{deal_id}").json()["status"] == "new"

        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        client.patch(f"/contacts/{cid}", json={"status": "qualified"})

        # Deal should now be "qualified"
        assert client.get(f"/deals/{deal_id}").json()["status"] == "qualified"

    def test_qualified_does_not_regress_advanced_deal(self, client):
        """If deal is already past 'new', qualifying a contact shouldn't change it."""
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        # Move deal forward
        client.post(f"/deals/{deal_id}/move-stage", json={"stage": "qualified"})
        client.post(f"/deals/{deal_id}/move-stage", json={"stage": "underwriting"})

        cid = client.post(f"/deals/{deal_id}/contacts", json=SAMPLE_CONTACT).json()["id"]
        client.patch(f"/contacts/{cid}", json={"status": "qualified"})

        # Deal should still be "underwriting", not regressed
        assert client.get(f"/deals/{deal_id}").json()["status"] == "underwriting"
