import json
from types import SimpleNamespace

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.models.user import User
from app.services.mfa_secrets import decrypt_secret, encrypt_secret, read_secret, reencrypt_secrets


@pytest.fixture
def keys(monkeypatch):
    ring = {"old": Fernet.generate_key().decode(), "new": Fernet.generate_key().decode()}
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps(ring))
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "old")
    return ring


def test_ciphertext_is_randomized_bound_to_user_and_authenticated(keys):
    secret = pyotp.random_base32()
    ciphertext = encrypt_secret("alice", secret)
    assert secret not in ciphertext
    assert encrypt_secret("alice", secret) != ciphertext
    assert decrypt_secret("alice", ciphertext) == secret
    for user_id, value in (("bob", ciphertext), ("alice", ciphertext[:-4] + "AAAA")):
        with pytest.raises(HTTPException) as exc:
            decrypt_secret(user_id, value)
        assert exc.value.status_code == 503
        assert secret not in exc.value.detail


def test_unknown_keys_never_fall_back_to_plaintext(keys, monkeypatch):
    secret = pyotp.random_base32()
    cipher = encrypt_secret("alice", secret)
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "new")
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps({"new": keys["new"]}))
    with pytest.raises(HTTPException):
        read_secret(SimpleNamespace(id="alice", totp_secret=secret, totp_secret_ciphertext=cipher))


@pytest.mark.parametrize("configuration", ["{}", "[]", "broken", '{"old":"invalid"}'])
def test_bad_configuration_fails_closed(configuration, monkeypatch):
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "old")
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", configuration)
    with pytest.raises(HTTPException) as exc:
        encrypt_secret("alice", pyotp.random_base32())
    assert exc.value.status_code == 503


def test_legacy_can_be_disabled(keys, monkeypatch):
    user = SimpleNamespace(id="alice", totp_secret=pyotp.random_base32(), totp_secret_ciphertext=None)
    assert read_secret(user) == user.totp_secret
    monkeypatch.setenv("MFA_ALLOW_LEGACY_PLAINTEXT", "false")
    with pytest.raises(HTTPException):
        read_secret(user)


def test_transactional_backfill_rotation_and_idempotence(keys, monkeypatch, db):
    secret = pyotp.random_base32()
    user = User(id="legacy", email="legacy@example.test", full_name="Test", password_hash="unused",
                totp_secret=secret, totp_enabled=True)
    db.add(user)
    db.commit()
    assert reencrypt_secrets(db)["legacy"] == 1
    assert user.totp_secret == secret
    assert reencrypt_secrets(db, apply=True)["rewritten"] == 1
    db.commit()
    assert user.totp_secret is None
    assert read_secret(user) == secret
    assert reencrypt_secrets(db, apply=True)["rewritten"] == 0
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "new")
    assert reencrypt_secrets(db, apply=True)["rewritten"] == 1
    db.commit()
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps({"new": keys["new"]}))
    assert read_secret(user) == secret


def test_failed_backfill_can_roll_back_all_rows(keys, db):
    for name, secret in (("a", pyotp.random_base32()), ("z", "corrupt")):
        db.add(User(id=name, email=f"{name}@example.test", full_name=name, password_hash="unused", totp_secret=secret))
    db.commit()
    with pytest.raises(HTTPException):
        reencrypt_secrets(db, apply=True, batch_size=1)
    db.rollback()
    assert db.get(User, "a").totp_secret_ciphertext is None


def test_new_enrollment_without_keys_is_not_stored(client, db, monkeypatch):
    monkeypatch.delenv("MFA_ENCRYPTION_KEYS", raising=False)
    response = client.post("/auth/register", json={"email": "no-key@example.com", "password": "CorrectHorseBattery42", "full_name": "Test", "organization_name": "No Key Test"})
    assert response.status_code == 201, response.text
    body = response.json()
    response = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 503
    user = db.get(User, body["user_id"])
    assert user.totp_secret is None and user.totp_secret_ciphertext is None


def test_portability_never_serializes_mfa_secrets_or_security_state():
    from app.routes.data_portability import _serialize_user

    user = User(id="test", email="test@example.com", full_name="Test", password_hash="password-hash",
                totp_secret="PLAINTEXT", totp_secret_ciphertext="CIPHERTEXT", token_version=42)
    payload = _serialize_user(user)
    assert payload["email"] == "test@example.com"
    assert not {"password_hash", "totp_secret", "totp_secret_ciphertext", "token_version", "is_superuser"} & payload.keys()
