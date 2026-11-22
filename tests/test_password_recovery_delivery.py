"""Recovery delivery and tenant-audit regressions; no external email calls."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event, text

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.password_reset_token import PasswordResetToken
from app.routes import password_reset
from app.services import email_service
from app.services.rate_limiter import limiter
from tests.test_password_reset import NEW_PW, REGISTER, _extract_token, _register


@pytest.fixture(autouse=True)
def clean_limiter():
    limiter.clear()
    yield
    limiter.clear()


def test_recovery_audits_account_membership_without_default_org(client, db, monkeypatch):
    db.execute(text("PRAGMA foreign_keys=ON"))
    _register(client)
    account_org = db.query(Organization).one().id
    assert db.get(Organization, "default-org") is None
    send = MagicMock()
    monkeypatch.setattr(email_service.email_service, "send", send)
    client.cookies.clear()
    response = client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    assert response.status_code == 204
    token = _extract_token(send.call_args)
    response = client.post("/auth/password/reset", json={"token": token, "new_password": NEW_PW})
    assert response.status_code == 204
    audits = db.query(AuditLog).filter(AuditLog.action.in_([
        "password_reset_requested", "password_reset_completed",
    ])).all()
    assert len(audits) == 2
    assert {row.organization_id for row in audits} == {account_org}


@pytest.mark.parametrize("address", [REGISTER["email"], "unknown@example.com"])
def test_unavailable_transport_is_global_503_without_tokens(client, db, monkeypatch, address):
    _register(client)
    monkeypatch.setattr(email_service.email_service, "available", False)
    send = MagicMock()
    monkeypatch.setattr(email_service.email_service, "send", send)
    user_reads = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "FROM users" in statement:
            user_reads.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", observe)
    response = client.post("/auth/password/forgot", json={"email": address})
    event.remove(db.get_bind(), "before_cursor_execute", observe)
    assert response.status_code == 503
    assert response.json() == {"detail": "Password recovery is temporarily unavailable. Please try again later."}
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Cache-Control"] == "no-store"
    assert db.query(PasswordResetToken).count() == 0
    send.assert_not_called()
    assert user_reads == []


def test_provider_exception_is_private_and_not_account_enumeration(client, monkeypatch, caplog):
    _register(client)
    secret = "never-log-reset-token-or-provider-key"
    send = MagicMock(side_effect=RuntimeError(secret))
    monkeypatch.setattr(email_service.email_service, "send", send)
    known = client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    unknown = client.post("/auth/password/forgot", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content == b""
    assert "password_reset_delivery_failed" in caplog.text
    assert secret not in caplog.text
    assert REGISTER["email"] not in caplog.text


def test_no_membership_does_not_issue_unaudited_reset(client, db, monkeypatch):
    _register(client)
    db.query(OrganizationMembership).delete()
    db.commit()
    send = MagicMock()
    monkeypatch.setattr(email_service.email_service, "send", send)
    response = client.post("/auth/password/forgot", json={"email": REGISTER["email"]})
    assert response.status_code == 204
    assert db.query(PasswordResetToken).count() == 0
    send.assert_not_called()


def test_console_sender_never_logs_email_or_body(caplog):
    with caplog.at_level("INFO"):
        email_service.ConsoleEmailService().send(
            to="private@example.com", subject="Recovery", html="private-token", text="private-token",
        )
    assert "private-token" not in caplog.text
    assert "private@example.com" not in caplog.text


@pytest.mark.parametrize("key,sender", [(None, None), ("test-key", None), (None, "BuildSignals <noreply@example.com>")])
def test_deployed_transport_requires_key_and_explicit_sender(monkeypatch, key, sender):
    monkeypatch.setattr(email_service, "IS_DEPLOYED", True)
    for name, value in [("RESEND_API_KEY", key), ("RESEND_FROM_ADDRESS", sender)]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    service = email_service._build_service()
    assert service.available is False
    with pytest.raises(email_service.EmailDeliveryUnavailable):
        service.send(to="private@example.com", subject="Recovery", html="token", text="token")


def test_sender_selection_never_imports_provider_when_unconfigured(monkeypatch):
    monkeypatch.setattr(email_service, "IS_DEPLOYED", False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert isinstance(email_service._build_service(), email_service.ConsoleEmailService)


def test_active_membership_selection_does_not_use_inactive_org(client, db):
    _register(client)
    organization = db.query(Organization).one()
    organization.is_active = False
    db.commit()
    membership = db.query(OrganizationMembership).one()
    assert password_reset._recovery_organization_id(db, membership.user_id) is None


def test_configured_transport_forwards_only_to_fake_provider(monkeypatch):
    send = MagicMock()
    requests_client = MagicMock()
    fake = SimpleNamespace(Emails=SimpleNamespace(send=send), api_key=None, RequestsClient=requests_client)
    monkeypatch.setitem(sys.modules, "resend", fake)
    monkeypatch.setattr(email_service, "IS_DEPLOYED", True)
    monkeypatch.setenv("RESEND_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "BuildSignals <noreply@example.com>")
    service = email_service._build_service()
    assert service.available is True
    requests_client.assert_called_once_with(timeout=5)
    assert fake.default_http_client is requests_client.return_value
    service.send(to="test@example.com", subject="Recovery", html="html", text="text")
    send.assert_called_once_with({
        "from": "BuildSignals <noreply@example.com>", "to": ["test@example.com"],
        "subject": "Recovery", "html": "html", "text": "text",
    })


def test_real_sdk_uses_short_explicit_io_timeout_without_network(monkeypatch):
    import requests
    import resend

    monkeypatch.setattr(resend, "api_key", resend.api_key)
    monkeypatch.setattr(resend, "default_http_client", resend.default_http_client)
    monkeypatch.setenv("RESEND_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "BuildSignals <noreply@example.com>")
    transport = MagicMock(return_value=SimpleNamespace(
        content=b'{"id":"synthetic-email-id"}', status_code=200,
        headers={"content-type": "application/json"},
    ))
    monkeypatch.setattr(requests, "request", transport)
    email_service.ResendEmailService().send(
        to="test@example.com", subject="Recovery", html="html", text="text",
    )
    transport.assert_called_once()
    assert transport.call_args.kwargs["timeout"] == 5


def test_reset_without_active_membership_does_not_consume_token(client, db, monkeypatch):
    _register(client)
    send = MagicMock()
    monkeypatch.setattr(email_service.email_service, "send", send)
    assert client.post("/auth/password/forgot", json={"email": REGISTER["email"]}).status_code == 204
    token = _extract_token(send.call_args)
    db.query(OrganizationMembership).delete()
    db.commit()
    response = client.post("/auth/password/reset", json={"token": token, "new_password": NEW_PW})
    assert response.status_code == 400
    db.expire_all()
    assert db.query(PasswordResetToken).one().used_at is None
