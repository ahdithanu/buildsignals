"""Tests for audit logging."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.models.audit_log import AuditLog
from app.services.audit_service import log_change
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.conftest import SAMPLE_DEAL


class TestAuditLogging:
    def test_omitted_scope_follows_each_request(self):
        db = Mock()
        for org in ("organization-a", "organization-b"):
            token = set_current_context(RequestContext(org_id=org, user_id="actor"))
            try:
                entry = log_change(db, "deal", "deal-id", "create")
                assert entry.organization_id == org
                db.add.assert_called_with(entry)
            finally:
                reset_current_context(token)

    def test_explicit_background_scope_is_preserved(self):
        entry = log_change(Mock(), "deal", "deal-id", "create", organization_id="worker-org")
        assert entry.organization_id == "worker-org"

    @pytest.mark.parametrize("organization_id", ["", "   "])
    def test_blank_scope_is_rejected_before_writing(self, organization_id):
        db = Mock()
        with pytest.raises(ValueError, match="organization_id must not be empty"):
            log_change(db, "deal", "deal-id", "create", organization_id=organization_id)
        db.add.assert_not_called()

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
