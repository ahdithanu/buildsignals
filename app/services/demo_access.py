"""Fixed demo identity and deny-by-default API policy. No tenant is client-selected."""
import re
from contextvars import ContextVar

from app import config

DEMO_ORG_ID = "3f0b7431-00d4-4a58-8b66-bac5d9f16986"
DEMO_USER_ID = "961ae491-ec19-4f8d-ae32-f7fe46d8a91c"
DEMO_EMAIL = "demo@buildsignals.invalid"
DEMO_MINUTES = 60
demo_read_only: ContextVar[bool] = ContextVar("demo_read_only", default=False)


def is_demo_identity(claims: dict) -> bool:
    return bool(claims.get("demo")) or claims.get("sub") == DEMO_USER_ID or claims.get("org_id") == DEMO_ORG_ID


def valid_demo_claims(claims: dict) -> bool:
    return (
        config.DEMO_ENABLED
        and claims.get("demo") is True
        and claims.get("read_only") is True
        and claims.get("sub") == DEMO_USER_ID
        and claims.get("org_id") == DEMO_ORG_ID
    )


def demo_path_allowed(method: str, path: str) -> bool:
    path = path.removeprefix("/v1").rstrip("/")
    if method == "POST" and path == "/auth/logout":
        return True
    if method not in {"GET", "HEAD"}:
        return False
    # New endpoints are inaccessible until explicitly audited as side-effect-free.
    return path in {
        "/auth/me", "/demo/summary", "/demo/parcel-references", "/demo/parcel-filings", "/demo/map",
        "/ingestion/permits",
    } or bool(re.fullmatch(
        r"/(?:ingestion/permits/[a-f0-9-]{36}|graph/entities/[a-f0-9-]{36}(?:/related)?|graph/relationships/[a-f0-9-]{36})",
        path,
    ))
