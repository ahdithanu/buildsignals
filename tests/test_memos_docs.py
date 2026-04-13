"""Tests for memos and documents."""
from __future__ import annotations

from tests.conftest import SAMPLE_DEAL, SAMPLE_ASSUMPTIONS


class TestDocuments:
    def test_create_document(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.post(f"/deals/{deal_id}/documents", json={
            "filename": "rent_roll.xlsx",
            "file_type": "xlsx",
            "file_size": 2048,
        })
        assert r.status_code == 201
        assert r.json()["filename"] == "rent_roll.xlsx"

    def test_list_documents(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/documents", json={
            "filename": "test.pdf", "file_type": "pdf", "file_size": 1024
        })
        r = client.get(f"/deals/{deal_id}/documents")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_soft_delete_document(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        doc_id = client.post(f"/deals/{deal_id}/documents", json={
            "filename": "del.pdf", "file_type": "pdf", "file_size": 512
        }).json()["id"]
        r = client.delete(f"/documents/{doc_id}")
        assert r.status_code == 204


class TestMemos:
    def test_generate_memo(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.put(f"/deals/{deal_id}/assumptions", json=SAMPLE_ASSUMPTIONS)
        client.post(f"/deals/{deal_id}/recalculate")
        r = client.post(f"/deals/{deal_id}/generate-memo")
        assert r.status_code == 201
        data = r.json()
        assert "content" in data
        assert len(data["content"]) > 0

    def test_get_memo(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/generate-memo")
        r = client.get(f"/deals/{deal_id}/memo")
        assert r.status_code == 200

    def test_update_memo(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/generate-memo")
        r = client.put(f"/deals/{deal_id}/memo", json={
            "title": "Custom Title",
            "content": "# Custom memo"
        })
        assert r.status_code == 200
        assert r.json()["title"] == "Custom Title"

    def test_get_memo_404_when_none(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        r = client.get(f"/deals/{deal_id}/memo")
        assert r.status_code == 404

    def test_soft_delete_memo(self, client):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/generate-memo")
        r = client.delete(f"/deals/{deal_id}/memo")
        assert r.status_code == 204
        r = client.get(f"/deals/{deal_id}/memo")
        assert r.status_code == 404
