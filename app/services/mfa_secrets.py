"""Authenticated MFA encryption with a separately provisioned, versioned key ring."""
import json
import os
import re

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def _unavailable():
    return HTTPException(503, "Authenticator service unavailable; contact support")


def _keyring() -> tuple[str, dict[str, Fernet]]:
    try:
        values = json.loads(os.environ.get("MFA_ENCRYPTION_KEYS", "{}"))
        active = os.environ.get("MFA_ACTIVE_KEY_ID", "")
        if not isinstance(values, dict) or not values or active not in values:
            raise ValueError
        keys = {}
        for key_id, value in values.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key_id) or not isinstance(value, str):
                raise ValueError
            if value == os.environ.get("SECRET_KEY"):
                raise ValueError
            keys[key_id] = Fernet(value.encode("ascii"))
        return active, keys
    except (ValueError, TypeError, UnicodeError):
        raise _unavailable() from None


def enrollment_ready() -> bool:
    """Check the existing encryption configuration without reading user secrets."""
    try:
        _keyring()
    except HTTPException:
        return False
    return True


def encrypt_secret(user_id: str, secret: str) -> str:
    active, keys = _keyring()
    payload = json.dumps({"user_id": user_id, "secret": secret}).encode("utf-8")
    return f"v1:{active}:" + keys[active].encrypt(payload).decode("ascii")


def decrypt_secret(user_id: str, ciphertext: str) -> str:
    _, keys = _keyring()
    try:
        version, key_id, token = ciphertext.split(":", 2)
        if version != "v1" or key_id not in keys:
            raise ValueError
        payload = json.loads(keys[key_id].decrypt(token.encode("ascii")))
        if not isinstance(payload, dict) or payload.get("user_id") != user_id:
            raise ValueError
        secret = payload.get("secret")
        if not isinstance(secret, str) or not re.fullmatch(r"[A-Z2-7]{16,64}", secret):
            raise ValueError
        return secret
    except (ValueError, TypeError, UnicodeError, InvalidToken):
        raise _unavailable() from None


def read_secret(user) -> str | None:
    # Ciphertext always wins; never fall back after a decryption failure.
    if user.totp_secret_ciphertext:
        return decrypt_secret(user.id, user.totp_secret_ciphertext)
    if user.totp_secret:
        if os.environ.get("MFA_ALLOW_LEGACY_PLAINTEXT", "true").lower() != "true":
            raise _unavailable()
        if not re.fullmatch(r"[A-Z2-7]{16,64}", user.totp_secret):
            raise _unavailable()
    return user.totp_secret


def store_secret(user, secret: str) -> None:
    ciphertext = encrypt_secret(user.id, secret)
    user.totp_secret_ciphertext = ciphertext
    user.totp_secret = None


def reencrypt_secrets(db, *, apply: bool = False, batch_size: int = 200) -> dict:
    """Validate all enrollments; optional atomic rewrite under the active key.

    The caller owns commit/rollback. No secrets, IDs, or ciphertext are reported.
    """
    from app.models.user import User

    if isinstance(batch_size, bool) or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    active, _ = _keyring()
    result = {"legacy": 0, "encrypted": 0, "rewritten": 0, "apply": apply}
    after = ""
    while True:
        rows = db.query(User).filter(
            User.id > after,
            (User.totp_secret.isnot(None) | User.totp_secret_ciphertext.isnot(None)),
        ).order_by(User.id).limit(batch_size).with_for_update().all()
        if not rows:
            break
        for user in rows:
            if user.totp_secret_ciphertext:
                secret = decrypt_secret(user.id, user.totp_secret_ciphertext)
                result["encrypted"] += 1
            else:
                secret = user.totp_secret
                if not re.fullmatch(r"[A-Z2-7]{16,64}", secret):
                    raise _unavailable()
                result["legacy"] += 1
            needs_rewrite = (user.totp_secret is not None or
                             not user.totp_secret_ciphertext.startswith(f"v1:{active}:"))
            if apply and needs_rewrite:
                store_secret(user, secret)
                result["rewritten"] += 1
        after = rows[-1].id
        db.flush()
    return result
