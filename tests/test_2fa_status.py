"""Secret-free account MFA status remains truthful when encryption is unavailable."""
import json
import os

import pyotp
import pytest
from cryptography.fernet import Fernet

from app.models.user import User
from app.services.account_lockout import lockout
from app.services.rate_limiter import limiter


@pytest.fixture(autouse=True)
def encryption(monkeypatch):
    limiter.clear()
    lockout.clear()
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "test")
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps({"test": Fernet.generate_key().decode()}))
    yield
    limiter.clear()
    lockout.clear()


def register(client, email="status@example.com"):
    response = client.post("/auth/register", json={
        "email": email, "password": "CorrectHorseBattery42", "full_name": "Status Test",
    })
    assert response.status_code == 201
    return response.json()


def headers(account):
    return {"Authorization": f"Bearer {account['access_token']}"}


def test_status_requires_authentication(client):
    assert client.get("/auth/2fa/status").status_code == 401
    assert client.get("/v1/auth/2fa/status", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_status_tracks_enrollment_without_exposing_pending_or_active_secret(client, db):
    account = register(client)
    auth = headers(account)
    initial = client.get("/v1/auth/2fa/status", headers=auth)
    assert initial.status_code == 200
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json() == {"enabled": False, "enrollment_ready": True}

    setup = client.post("/auth/2fa/setup", headers=auth)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    pending = client.get("/auth/2fa/status", headers=auth)
    assert pending.json() == initial.json()
    user = db.get(User, account["user_id"])
    ciphertext = user.totp_secret_ciphertext
    assert ciphertext and user.totp_secret is None
    assert secret not in pending.text and ciphertext not in pending.text

    assert client.post("/auth/2fa/verify", headers=auth, json={"code": pyotp.TOTP(secret).now()}).status_code == 204
    enabled = client.get("/auth/2fa/status", headers=auth)
    assert enabled.json() == {"enabled": True, "enrollment_ready": True}
    assert enabled.headers["cache-control"] == "no-store"
    assert secret not in enabled.text and ciphertext not in enabled.text

    assert client.post("/auth/2fa/disable", headers=auth, json={
        "password": "CorrectHorseBattery42", "code": pyotp.TOTP(secret).now(),
    }).status_code == 204
    assert client.get("/auth/2fa/status", headers=auth).json() == initial.json()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("keyring", [None, "{}", "[]", "broken", '{"test":"invalid"}'])
def test_missing_or_invalid_keys_do_not_change_account_enabled_state(client, db, monkeypatch, enabled, keyring):
    account = register(client)
    user = db.get(User, account["user_id"])
    user.totp_enabled = enabled
    user.totp_secret_ciphertext = "unreadable-encrypted-value"
    db.commit()
    if keyring is None:
        monkeypatch.delenv("MFA_ENCRYPTION_KEYS")
    else:
        monkeypatch.setenv("MFA_ENCRYPTION_KEYS", keyring)
    response = client.get("/auth/2fa/status", headers=headers(account))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"enabled": enabled, "enrollment_ready": False}
    db.refresh(user)
    assert user.totp_enabled == enabled
    assert user.totp_secret_ciphertext == "unreadable-encrypted-value"


def test_status_reuses_keyring_validation_and_never_decrypts_secrets(client, db, monkeypatch):
    from app.services import mfa_secrets

    account = register(client)
    user = db.get(User, account["user_id"])
    user.totp_enabled = True
    user.totp_secret_ciphertext = "unreadable-encrypted-value"
    db.commit()

    def must_not_read(*args, **kwargs):
        raise AssertionError("Status must not read or decrypt an authenticator secret")

    monkeypatch.setattr(mfa_secrets, "read_secret", must_not_read)
    monkeypatch.setattr(mfa_secrets, "decrypt_secret", must_not_read)
    auth = headers(account)
    assert client.get("/auth/2fa/status", headers=auth).json() == {"enabled": True, "enrollment_ready": True}
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "missing")
    assert client.get("/auth/2fa/status", headers=auth).json() == {"enabled": True, "enrollment_ready": False}
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "test")
    key = json.loads(os.environ["MFA_ENCRYPTION_KEYS"])["test"]
    monkeypatch.setenv("SECRET_KEY", key)
    assert client.get("/auth/2fa/status", headers=auth).json() == {"enabled": True, "enrollment_ready": False}


def test_status_is_scoped_to_the_authenticated_user(client, db):
    first = register(client, "first-status@example.com")
    second = register(client, "second-status@example.com")
    user = db.get(User, first["user_id"])
    user.totp_enabled = True
    db.commit()
    assert client.get("/auth/2fa/status", headers=headers(first)).json()["enabled"] is True
    assert client.get("/auth/2fa/status", headers=headers(second)).json()["enabled"] is False
