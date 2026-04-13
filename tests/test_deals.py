"""Tests for deal CRUD and core workflows."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL, SAMPLE_ASSUMPTIONS


class TestDealCRUD:
    def test_create_deal(self, client):
        r = client.post("/deals", json=SAMPLE_DEAL)
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Test Deal"
        assert data["property_type"] == "Office"  # normalized
        assert data["status"] == "new"
        assert "id" in data

    def test_list_deals(self, client):
        client.post("/deals", json=SAMPLE_DEAL)
        r = client.get("/deals")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_deal_detail(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.get(f"/deals/{deal_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == deal_id
        assert "assumptions" in data
        assert "outputs" in data
        assert "contacts_count" in data

    def test_update_deal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.patch(f"/deals/{deal_id}", json={"name": "Updated Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_get_nonexistent_deal_404(self, client):
        r = client.get("/deals/nonexistent-id")
        assert r.status_code == 404

    def test_filter_by_status(self, client):
        client.post("/deals", json=SAMPLE_DEAL)
        r = client.get("/deals?status=new")
        assert r.status_code == 200
        for deal in r.json():
            assert deal["status"] == "new"

    def test_soft_delete_deal(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.delete(f"/deals/{deal_id}")
        assert r.status_code == 204
        # Should be 404 after soft delete
        r = client.get(f"/deals/{deal_id}")
        assert r.status_code == 404

    def test_bulk_import(self, client):
        deals = [
            {**SAMPLE_DEAL, "name": "Import 1"},
            {**SAMPLE_DEAL, "name": "Import 2"},
        ]
        r = client.post("/deals/import", json=deals)
        assert r.status_code == 201
        assert len(r.json()) == 2


class TestNormalization:
    def test_property_type_normalized_on_create(self, client):
        deal = {**SAMPLE_DEAL, "property_type": "multi-family"}
        r = client.post("/deals", json=deal)
        assert r.json()["property_type"] == "Multifamily"

    def test_property_type_normalized_on_update(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.patch(f"/deals/{deal_id}", json={"property_type": "warehouse"})
        assert r.json()["property_type"] == "Industrial"

    def test_unknown_property_type_preserved(self, client):
        deal = {**SAMPLE_DEAL, "property_type": "Self Storage"}
        r = client.post("/deals", json=deal)
        assert r.json()["property_type"] == "Self Storage"
