from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.brand import BrandAlias, BrandProfile
from app.services.company_catalog import ensure_company_catalog, require_company_rls
from app.services.demo_access import demo_read_only
from app.utils.org_scope import (
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)


def test_catalog_prerequisite_is_idempotent_and_tenant_scoped(db):
    result = ensure_company_catalog(db, get_org_id())
    assert result.created > 0
    db.commit()
    first = [(row.id, row.key) for row in db.query(BrandProfile).all()]
    aliases = db.query(BrandAlias).count()
    replay = ensure_company_catalog(db, get_org_id())
    assert replay.created == replay.updated == 0
    assert replay.unchanged == result.created
    assert first == [(row.id, row.key) for row in db.query(BrandProfile).all()]
    assert db.query(BrandAlias).count() == aliases
    token = set_current_context(RequestContext("other-org", "operator"))
    try:
        other = ensure_company_catalog(db, "other-org")
        assert other.created == result.created
        assert db.query(BrandProfile).filter_by(organization_id="other-org").count() == result.created
    finally:
        reset_current_context(token)


def test_catalog_prerequisite_rejects_wrong_scope_and_demo(db):
    with pytest.raises(ValueError, match="explicit current tenant"):
        ensure_company_catalog(db, "foreign-org")
    token = demo_read_only.set(True)
    try:
        with pytest.raises(PermissionError, match="Demo"):
            ensure_company_catalog(db, get_org_id())
    finally:
        demo_read_only.reset(token)
    assert db.query(BrandProfile).count() == 0


@pytest.mark.parametrize("rows", [[], [("brand_profiles", True)],
    [("brand_profiles", True), ("brand_aliases", False)]])
def test_runtime_guard_rejects_missing_or_ineffective_rls(rows):
    db = Mock(no_autoflush=nullcontext())
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.execute.return_value.all.return_value = rows
    with pytest.raises(PermissionError, match="row security"):
        require_company_rls(db, ("brand_profiles", "brand_aliases"))
