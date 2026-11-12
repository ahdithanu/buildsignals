"""Tenant catalog prerequisite for direct ingestion workers and stored replay."""
from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.demo_access import demo_read_only
from app.utils.org_scope import get_org_id


def require_company_rls(db: Session, tables: tuple[str, ...]) -> None:
    """Fail closed if the PostgreSQL runtime can bypass any affected tenant table."""
    if db.get_bind().dialect.name != "postgresql":
        return
    with db.no_autoflush:
        rows = db.execute(text("""
            SELECT c.relname,
                   pg_catalog.row_security_active(c.oid) AND c.relrowsecurity
                   AND c.relforcerowsecurity AND NOT r.rolsuper AND NOT r.rolbypassrls
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_roles r ON r.rolname = current_user
            WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
        """), {"tables": list(tables)}).all()
    if {row[0] for row in rows} != set(tables) or any(row[1] is not True for row in rows):
        raise PermissionError("Company intelligence requires effective tenant row security")


def ensure_company_catalog(db: Session, organization_id: str):
    """Sync shipped definitions before ingestion; caller owns commit/rollback.

    Different source workers share a transaction lock for this tenant, preventing
    simultaneous first-time inserts. It is released by the caller's commit.
    """
    if not organization_id or organization_id != get_org_id():
        raise ValueError("Company catalog requires the explicit current tenant")
    if demo_read_only.get():
        raise PermissionError("Demo sessions cannot initialize company catalogs")
    require_company_rls(db, ("brand_profiles", "brand_aliases"))
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(
            ("company-catalog:" + organization_id).encode()
        ).digest()[:8], "big", signed=True)
        # Bound contention without changing connection/session defaults.
        previous_timeout = db.scalar(text("SELECT current_setting('lock_timeout')"))
        db.execute(text("SELECT set_config('lock_timeout', '5s', true)"))
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        db.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": previous_timeout})
    return sync_brand_catalog(db, load_brand_catalog())
