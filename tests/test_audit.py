"""Tests for audit logging."""
from __future__ import annotations

from app.models.audit_log import AuditLog
from tests.conftest import SAMPLE_DEAL


class TestAuditLogging:
    def test_deal_create_logged(self, client, db):
        client.post("/deals", json=SAMPLE_DEAL)
        logs = db.query(AuditLog).filter(AuditLog.action == "create").all()
        assert len(logs) >= 1
        assert logs[0].entity_type == "deal"

    def test_deal_update_logged(self, client, db):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.patch(f"/deals/{deal_id}", json={"name": "Renamed"})
        logs = db.query(AuditLog).filter(
            AuditLog.entity_type == "deal",
            AuditLog.action == "update"
        ).all()
        assert len(logs) >= 1

    def test_stage_change_logged(self, client, db):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.post(f"/deals/{deal_id}/move-stage", json={"stage": "qualified"})
        logs = db.query(AuditLog).filter(AuditLog.action == "stage_change").all()
        assert len(logs) >= 1

    def test_soft_delete_logged(self, client, db):
        deal_id = client.post("/deals", json=SAMPLE_DEAL).json()["id"]
        client.delete(f"/deals/{deal_id}")
        logs = db.query(AuditLog).filter(AuditLog.action == "soft_delete").all()
        assert len(logs) >= 1
