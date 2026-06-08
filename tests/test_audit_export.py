"""End-to-end tests for GET /audit/export.

Covers the security contract (admin-only, org-scoped), both output
formats, filtering, and the row-cap safety valve.
"""
from __future__ import annotations

import csv
import io
import json
from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes import audit as audit_routes
from app.services.rate_limiter import limiter
from app.services.security import create_access_token, hash_password

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, email="alice@example.com", org_name="Acme"):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_log(db, *, org_id, entity_type="deal", action="create",
              actor_id=None, entity_id=None, request_id=None,
              new_values=None, old_values=None):
    entry = AuditLog(
        id=str(uuid4()),
        organization_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id or str(uuid4()),
        action=action,
        actor_id=actor_id,
        new_values=json.dumps(new_values) if new_values else None,
        old_values=json.dumps(old_values) if old_values else None,
        request_id=request_id,
    )
    db.add(entry)
    db.commit()
    return entry


class TestAuditExport:
    def test_csv_export_returns_header_and_rows(self, client, db):
        reg = _register(client)
        org_id = reg["organization_id"]
        for i in range(5):
            _seed_log(db, org_id=org_id, entity_type="deal", action="create",
                      new_values={"i": i})

        r = client.get(
            "/audit/export?entity_type=deal",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        assert ".csv" in r.headers["content-disposition"]

        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        # 1 header + 5 data rows
        assert len(rows) == 6
        assert rows[0] == [
            "created_at", "request_id", "actor_email", "actor_name",
            "entity_type", "entity_id", "action",
            "old_values", "new_values",
        ]
        # new_values column is the raw JSON-encoded string
        body_rows = rows[1:]
        for row in body_rows:
            assert row[4] == "deal"
            assert row[6] == "create"
            assert json.loads(row[8])  # parses as JSON

    def test_json_export_decodes_values(self, client, db):
        reg = _register(client)
        org_id = reg["organization_id"]
        for i in range(5):
            _seed_log(db, org_id=org_id, entity_type="deal", action="create",
                      new_values={"i": i})

        r = client.get(
            "/audit/export?format=json&entity_type=deal",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 5
        for item in body:
            assert item["entity_type"] == "deal"
            assert isinstance(item["new_values"], dict)
            assert "i" in item["new_values"]

    def test_non_admin_is_denied(self, client, db):
        admin = _register(client, email="admin@acme.com", org_name="Acme")
        org_id = admin["organization_id"]

        viewer = User(
            id=str(uuid4()),
            email="view@acme.com",
            full_name="Viewer",
            password_hash=hash_password(STRONG_PW),
            is_active=True,
        )
        db.add(viewer)
        db.add(OrganizationMembership(
            id=str(uuid4()),
            organization_id=org_id,
            user_id=viewer.id,
            role=MemberRole.editor,
            is_default=True,
        ))
        db.commit()

        viewer_token = create_access_token(user_id=viewer.id, org_id=org_id)
        r = client.get("/audit/export", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_cross_org_isolation(self, client, db):
        reg_a = _register(client, email="alice@acme.com", org_name="Acme")
        reg_b = _register(client, email="bob@globex.com", org_name="Globex")

        _seed_log(db, org_id=reg_a["organization_id"], entity_type="deal",
                  new_values={"secret": "acme-internal"})
        _seed_log(db, org_id=reg_b["organization_id"], entity_type="deal",
                  new_values={"secret": "globex-internal"})

        r = client.get(
            "/audit/export?format=json&entity_type=deal",
            headers=_auth(reg_b["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["new_values"]["secret"] == "globex-internal"

    def test_filter_by_entity_type(self, client, db):
        reg = _register(client)
        org_id = reg["organization_id"]
        _seed_log(db, org_id=org_id, entity_type="deal", action="create")
        _seed_log(db, org_id=org_id, entity_type="memo", action="create")
        _seed_log(db, org_id=org_id, entity_type="memo", action="update")

        r = client.get(
            "/audit/export?format=json&entity_type=deal",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["entity_type"] == "deal"

    def test_row_cap_returns_413(self, client, db, monkeypatch):
        # Patch the cap down so we can trip it without seeding 50k rows.
        monkeypatch.setattr(audit_routes, "EXPORT_ROW_CAP", 2)

        reg = _register(client)
        org_id = reg["organization_id"]
        for i in range(3):
            _seed_log(db, org_id=org_id, entity_type="deal", action="create",
                      new_values={"i": i})

        r = client.get(
            "/audit/export?entity_type=deal",
            headers=_auth(reg["access_token"]),
        )
        assert r.status_code == 413
        assert "limit" in r.json()["detail"].lower()
