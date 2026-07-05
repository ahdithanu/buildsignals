"""JWT codec contract (app/services/security.py).

These lock the security-critical invariants of token encode/decode so a
library swap (this suite was added when auth migrated python-jose→PyJWT)
can't silently regress them. Every rejection path must return None, never
raise and never accept.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import ALGORITHM, SECRET_KEY
from app.services.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def test_access_token_round_trips():
    tok = create_access_token(user_id="u1", org_id="o1", token_version=3)
    claims = decode_access_token(tok)
    assert claims is not None
    assert claims["sub"] == "u1"
    assert claims["org_id"] == "o1"
    assert claims["typ"] == ACCESS_TOKEN_TYPE
    assert claims["tv"] == 3
    assert "jti" in claims and claims["jti"]


def test_refresh_token_round_trips():
    tok = create_refresh_token(user_id="u1", org_id="o1", token_version=1)
    claims = decode_refresh_token(tok)
    assert claims is not None
    assert claims["typ"] == REFRESH_TOKEN_TYPE
    assert claims["sub"] == "u1"


def test_tokens_are_str_not_bytes():
    # PyJWT 1.x returned bytes; 2.x returns str. Cookies/headers need str.
    assert isinstance(create_access_token(user_id="u", org_id="o"), str)
    assert isinstance(create_refresh_token(user_id="u", org_id="o"), str)


def test_access_decoder_rejects_a_refresh_token():
    # Type confusion: a stolen refresh cookie must not work as a bearer token.
    refresh = create_refresh_token(user_id="u1", org_id="o1")
    assert decode_access_token(refresh) is None


def test_refresh_decoder_rejects_an_access_token():
    access = create_access_token(user_id="u1", org_id="o1")
    assert decode_refresh_token(access) is None


def test_expired_token_is_rejected():
    # Mint a token that expired an hour ago, signed with the real secret.
    payload = {
        "sub": "u1",
        "org_id": "o1",
        "typ": ACCESS_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "jti": "x",
        "tv": 0,
    }
    expired = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    assert decode_access_token(expired) is None


def test_tampered_signature_is_rejected():
    # Same claims, signed with the WRONG secret → signature check fails.
    payload = {
        "sub": "u1",
        "org_id": "o1",
        "typ": ACCESS_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "jti": "x",
        "tv": 0,
    }
    forged = jwt.encode(payload, "not-the-real-secret", algorithm=ALGORITHM)
    assert decode_access_token(forged) is None


def test_garbage_string_is_rejected():
    assert decode_access_token("not.a.jwt") is None
    assert decode_access_token("") is None
    assert decode_refresh_token("garbage") is None


def test_legacy_token_without_typ_accepted_as_access():
    # Back-compat branch: a token minted before the typ claim existed is
    # still valid as an access token (it could only ever be one).
    payload = {
        "sub": "u1",
        "org_id": "o1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    legacy = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    claims = decode_access_token(legacy)
    assert claims is not None
    assert claims["sub"] == "u1"
