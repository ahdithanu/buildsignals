from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.api_key import OrganizationApiKey
from app.schemas.organization import ApiKeyResponse

KEY_PREFIX = "bs_live"


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"{KEY_PREFIX}_{secrets.token_urlsafe(32)}"


def _public_key_prefix(secret: str) -> str:
    parts = secret.split("_", 2)
    if len(parts) == 3:
        return f"{parts[0]}_{parts[1]}_{parts[2][:8]}"
    return secret[:18]


def serialize_scopes(scopes: list[str]) -> str:
    return json.dumps(sorted(set(scopes)))


def parse_scopes(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return sorted(str(scope) for scope in value)


def to_response(api_key: OrganizationApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=parse_scopes(api_key.scopes),
        created_by=api_key.created_by,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        revoked_by=api_key.revoked_by,
        last_used_at=api_key.last_used_at,
    )


def create_api_key(
    db: Session,
    *,
    organization_id: str,
    name: str,
    scopes: list[str],
    actor_id: str,
) -> tuple[OrganizationApiKey, str]:
    secret = generate_api_key()
    api_key = OrganizationApiKey(
        organization_id=organization_id,
        name=name.strip(),
        key_hash=hash_api_key(secret),
        key_prefix=_public_key_prefix(secret),
        scopes=serialize_scopes(scopes),
        created_by=actor_id,
    )
    db.add(api_key)
    return api_key, secret


def revoke_api_key(db: Session, *, api_key: OrganizationApiKey, actor_id: str) -> OrganizationApiKey:
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        api_key.revoked_by = actor_id
        db.add(api_key)
    return api_key


def authenticate_api_key(db: Session, *, secret: str) -> OrganizationApiKey | None:
    api_key = db.query(OrganizationApiKey).filter(
        OrganizationApiKey.key_hash == hash_api_key(secret),
        OrganizationApiKey.revoked_at.is_(None),
    ).first()
    if api_key is None:
        return None
    api_key.last_used_at = datetime.now(timezone.utc)
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def has_scope(api_key: OrganizationApiKey, required_scope: str) -> bool:
    scopes = set(parse_scopes(api_key.scopes))
    if "admin" in scopes:
        return True
    if required_scope == "read" and "write" in scopes:
        return True
    return required_scope in scopes
