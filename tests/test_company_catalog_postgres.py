import os

import pytest
from sqlalchemy import text

from app.models.brand import BrandProfile
from app.services.company_catalog import ensure_company_catalog, require_company_rls
from tests.test_sf_map_postgres import _as_org
from tests.test_sf_map_postgres import pg_scope as pg_scope

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Requires disposable PostgreSQL")


def test_catalog_initialization_uses_effective_rls_and_transaction_lock(pg_scope):
    db, org, foreign = pg_scope
    previous_timeout = db.scalar(text("SELECT current_setting('lock_timeout')"))
    first = ensure_company_catalog(db, org)
    assert first.created > 0
    assert db.scalar(text("SELECT current_setting('lock_timeout')")) == previous_timeout
    assert db.scalar(text("SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'")) > 0
    second = ensure_company_catalog(db, org)
    assert second.created == second.updated == 0
    with _as_org(db, foreign):
        assert db.query(BrandProfile).count() == 0
        assert ensure_company_catalog(db, foreign).created == first.created
        assert db.scalar(text("SELECT count(*) FROM brand_profiles WHERE organization_id=:org"), {"org": org}) == 0
    assert db.query(BrandProfile).count() == first.created
    assert db.scalar(text("SELECT count(*) FROM brand_profiles WHERE organization_id=:org"), {"org": foreign}) == 0
    with pytest.raises(PermissionError, match="row security"):
        require_company_rls(db, ("missing_tenant_table",))
