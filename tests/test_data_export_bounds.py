"""Bounded whole-organization exports against isolated synthetic databases."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, insert
from sqlalchemy.orm import Query, Session

from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes import data_portability as routes
from app.services.security import create_access_token


def _identity(db, name, *, role=MemberRole.admin):
    org = Organization(id=str(uuid4()), name=name, slug=str(uuid4()))
    user = User(id=str(uuid4()), email=f"{name}@example.com", full_name=name,
                password_hash="synthetic-password-hash", totp_secret="SYNTHETIC-MFA-SECRET",
                totp_enabled=True, token_version=7, is_active=True, is_superuser=False)
    db.add_all([org, user])
    db.flush()
    membership = OrganizationMembership(organization_id=org.id, user_id=user.id, role=role)
    db.add(membership)
    db.commit()
    token = create_access_token(user_id=user.id, org_id=org.id, token_version=user.token_version)
    return org, user, {"Authorization": f"Bearer {token}"}


def _deal(db, org, name="Synthetic deal", *, deleted=False):
    deal = Deal(id=str(uuid4()), organization_id=org.id, name=name)
    if deleted:
        deal.deleted_at = datetime.now(timezone.utc)
    db.add(deal)
    db.commit()
    return deal


def _export(client, org, headers, **kwargs):
    return client.get(f"/v1/organizations/{org.id}/export", headers=headers, **kwargs)


def _assert_no_download(response, status):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    assert "content-disposition" not in response.headers
    assert set(response.json()) == {"detail"}


def test_empty_organization_export_has_all_sections_and_profile_allowlist(client, db):
    org, user, headers = _identity(db, "empty")
    response = _export(client, org, headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.json"')
    body = response.json()
    assert body["organization_id"] == org.id
    assert body["organization"]["id"] == org.id
    assert len(body["members"]) == 1
    assert set(body["members"][0]["user"]) == routes._USER_EXPORT_FIELDS
    assert body["members"][0]["user"]["id"] == user.id
    for entry in routes.EXPORT_TABLES:
        assert body[entry.name] == []
        assert body["manifest"]["tables"][entry.name]["row_count"] == 0
    for secret in ("synthetic-password-hash", "SYNTHETIC-MFA-SECRET", "password_hash",
                   "totp_secret", "token_version", "is_superuser"):
        assert secret not in response.text
    receipt = db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").one()
    metadata = json.loads(receipt.new_values)
    assert metadata["row_count"] == 3  # organization + membership + user
    assert metadata["byte_count"] == len(response.content)


def test_exact_total_row_cap_succeeds_and_counts_soft_deleted_rows(client, db, monkeypatch):
    org, _, headers = _identity(db, "exact")
    _deal(db, org)
    tombstone = _deal(db, org, "Deleted deal", deleted=True)
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 5)
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["deals"]) == 2
    assert next(item for item in response.json()["deals"] if item["id"] == tombstone.id)["deleted_at"]
    receipt = db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").one()
    assert json.loads(receipt.new_values)["row_count"] == 5


def test_total_budget_is_shared_across_tables_not_reset_per_table(client, db, monkeypatch):
    org, _, headers = _identity(db, "aggregate")
    deal = _deal(db, org, "Must never appear in error")
    db.add(Contact(organization_id=org.id, deal_id=deal.id, name="Private contact"))
    db.add(AuditLog(organization_id=org.id, entity_type="deal", entity_id=deal.id,
                    action="create", new_values='{"confidential":"late table"}'))
    db.commit()
    # Three base rows, one deal and one contact fit; the final audit table overflows.
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 5)
    response = _export(client, org, headers)
    _assert_no_download(response, 413)
    assert "5-row" in response.json()["detail"]
    assert "Private contact" not in response.text
    assert "Must never appear" not in response.text
    assert "late table" not in response.text
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0


def test_membership_and_profile_rows_both_consume_budget(client, db, monkeypatch):
    org, _, headers = _identity(db, "members")
    _, second, _ = _identity(db, "second-user")
    db.add(OrganizationMembership(organization_id=org.id, user_id=second.id, role=MemberRole.viewer))
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 4)  # Needs five rows, not three.
    response = _export(client, org, headers)
    _assert_no_download(response, 413)
    assert second.email not in response.text


@pytest.mark.parametrize("cap", [30, None])
def test_large_actual_dataset_fails_without_loading_or_serializing_every_row(client, db, monkeypatch, cap):
    org, _, headers = _identity(db, "large")
    db.execute(insert(Deal), [{"id": str(uuid4()), "organization_id": org.id,
                               "name": "Large synthetic record"} for _ in range(20_000)])
    db.commit()
    if cap is not None:
        monkeypatch.setattr(routes, "EXPORT_ROW_CAP", cap)
    effective_cap = routes.EXPORT_ROW_CAP
    loaded = []
    selects = []

    def record_load(session, obj):
        if isinstance(obj, Deal):
            loaded.append(obj.id)

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM deals" in statement:
            selects.append(statement)

    event.listen(Session, "loaded_as_persistent", record_load)
    event.listen(db.get_bind(), "before_cursor_execute", record_select)
    try:
        response = _export(client, org, headers)
    finally:
        event.remove(Session, "loaded_as_persistent", record_load)
        event.remove(db.get_bind(), "before_cursor_execute", record_select)
    _assert_no_download(response, 413)
    assert len(loaded) <= effective_cap - 2  # Minus org/member/user, plus sentinel.
    assert selects and all("LIMIT" in statement for statement in selects)
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0


def test_foreign_large_tenant_does_not_consume_budget_or_leak_data(client, db, monkeypatch):
    org, _, headers = _identity(db, "small-tenant")
    foreign, foreign_user, _ = _identity(db, "foreign-tenant")
    _deal(db, org, "Own record")
    db.execute(insert(Deal), [{"id": str(uuid4()), "organization_id": foreign.id,
                               "name": "Foreign private data"} for _ in range(1_000)])
    db.add(AuditLog(organization_id=foreign.id, entity_type="deal", entity_id=str(uuid4()),
                    action="create", new_values='{"secret":"foreign audit"}'))
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 4)
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["deals"]] == ["Own record"]
    assert foreign.id not in response.text
    assert foreign_user.email not in response.text
    assert "Foreign private data" not in response.text
    assert "foreign audit" not in response.text


@pytest.mark.parametrize("role", [MemberRole.viewer, MemberRole.editor])
def test_non_admin_export_is_denied_without_data(client, db, role):
    org, _, headers = _identity(db, "non-admin", role=role)
    _assert_no_download(_export(client, org, headers), 403)


def test_cross_org_export_is_denied_even_for_dual_admin(client, db):
    org, user, headers = _identity(db, "active")
    foreign, _, _ = _identity(db, "other")
    db.add(OrganizationMembership(organization_id=foreign.id, user_id=user.id, role=MemberRole.admin))
    db.commit()
    _assert_no_download(_export(client, foreign, headers), 403)


def test_missing_bearer_export_requires_authentication(client, db):
    org, _, _ = _identity(db, "anonymous")
    _assert_no_download(_export(client, org, {}), 401)


def test_query_limit_cannot_turn_whole_export_into_a_silent_partial_download(client, db, monkeypatch):
    org, _, headers = _identity(db, "no-pagination")
    _deal(db, org)
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 3)
    _assert_no_download(_export(client, org, headers, params={"limit": 1, "offset": 100}), 413)


def test_large_text_fails_byte_budget_without_partial_download(client, db, monkeypatch):
    org, _, headers = _identity(db, "large-text")
    deal = _deal(db, org)
    deal.notes = "Sensitive text " * 10_000
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_BYTE_CAP", 2_000)
    response = _export(client, org, headers)
    _assert_no_download(response, 413)
    assert "Sensitive text" not in response.text
    assert "2,000-byte" in response.json()["detail"]
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0


def test_json_envelope_also_counts_toward_byte_cap(client, db, monkeypatch):
    org, _, headers = _identity(db, "envelope")
    # The entity JSON fits, but arrays, names, and exported_at exceed this budget.
    items_size = 0
    original_add = routes._ExportBudget.add

    def tracked_add(self, item, **kwargs):
        nonlocal items_size
        result = original_add(self, item, **kwargs)
        items_size = self.encoded_bytes
        return result

    monkeypatch.setattr(routes._ExportBudget, "add", tracked_add)
    first = _export(client, org, headers)
    assert first.status_code == 200
    # Remove only this synthetic export receipt, keeping the next snapshot identical.
    db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").delete()
    db.commit()
    assert items_size < len(first.content)
    monkeypatch.setattr(routes, "EXPORT_BYTE_CAP", items_size)
    _assert_no_download(_export(client, org, headers), 413)


@pytest.mark.parametrize("failure", ["serialization", "query", "audit", "commit"])
def test_internal_errors_never_return_partial_data_credentials_or_success_receipt(client, db, monkeypatch, failure):
    org, _, headers = _identity(db, "errors")
    _deal(db, org, "Confidential deal")

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic-password-hash SYNTHETIC-MFA-SECRET database-internal-error")

    if failure == "serialization":
        original = routes._serialize

        def serialize(obj, **kwargs):
            if isinstance(obj, Deal):
                return broken()
            return original(obj, **kwargs)

        monkeypatch.setattr(routes, "_serialize", serialize)
    elif failure == "query":
        monkeypatch.setattr(Query, "yield_per", broken)
    elif failure == "audit":
        monkeypatch.setattr(routes, "log_change", broken)
    else:
        monkeypatch.setattr(Session, "commit", broken)
    response = _export(client, org, headers)
    _assert_no_download(response, 500)
    assert response.json()["detail"] == "Organization export failed. No data was returned."
    for value in ("Confidential deal", "synthetic-password-hash", "SYNTHETIC-MFA-SECRET", "database-internal-error"):
        assert value not in response.text
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0


def test_orphan_membership_is_not_silently_omitted_from_export(client, db):
    org, _, headers = _identity(db, "orphan")
    # The shared SQLite fixture permits constructing corruption; production FKs
    # normally prevent it. An imported/legacy orphan must fail closed anyway.
    db.add(OrganizationMembership(organization_id=org.id, user_id=str(uuid4()), role=MemberRole.viewer))
    db.commit()
    _assert_no_download(_export(client, org, headers), 500)
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0
