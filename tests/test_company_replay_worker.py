from copy import deepcopy
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.brand import BrandAlias, BrandProfile, PermitBrandMatch
from app.models.graph import GraphRelationship
from app.models.organization import Organization
from app.services.brand_intelligence import list_brand_expansion_summaries
from app.services.demo_access import DEMO_ORG_ID
from scripts.backfill_company_intelligence import run
from tests.test_brand_backfill import _seed_permits


def fixture(db, count=2):
    db.add(Organization(id="default-org", slug="replay-test", name="Synthetic replay"))
    permits = _seed_permits(db, [{
        "project_name": "Coffee tenant improvement",
        "description": "Interior retail build-out for Starbucks Coffee",
    }] * count)
    return permits, sessionmaker(bind=db.get_bind())


def snapshot(row):
    return deepcopy({column.name: getattr(row, column.name) for column in row.__table__.columns})


def test_plan_does_not_initialize_catalog_or_write_evidence(db, monkeypatch):
    permits, factory = fixture(db)
    from scripts import backfill_company_intelligence as worker
    forbidden = Mock(side_effect=AssertionError("Plan cannot write"))
    monkeypatch.setattr(worker, "ensure_company_catalog", forbidden)
    before = snapshot(permits[0])
    result = run("default-org", permit_limit=1, session_factory=factory)
    assert result["status"] == "planned" and result["permits"]["planned"] == 1
    assert result["permits"]["has_more"]
    assert db.query(BrandProfile).count() == db.query(BrandAlias).count() == 0
    assert db.query(PermitBrandMatch).count() == 0
    assert snapshot(permits[0]) == before and not forbidden.called


def test_bounded_repair_populates_summary_without_changing_source_records(db):
    permits, factory = fixture(db)
    assert list_brand_expansion_summaries(db, days=180, signal_cohort="national_retail") == []
    before = [(snapshot(row), snapshot(row.latest_raw_record)) for row in permits]
    first = run("default-org", execute=True, permit_limit=1, batch_size=1, session_factory=factory)
    assert first["status"] == "partial" and first["permits"]["scanned"] == 1
    assert first["permits"]["matches_created"] == 1
    second = run("default-org", execute=True, permit_limit=1, batch_size=1,
                 after_permit_id=first["permits"]["next_cursor"], session_factory=factory)
    assert second["status"] == "completed" and second["permits"]["matches_created"] == 1
    db.expire_all()
    assert [(snapshot(row), snapshot(row.latest_raw_record)) for row in permits] == before
    summary = list_brand_expansion_summaries(db, days=180, signal_cohort="national_retail")
    assert len(summary) == 1 and summary[0].brand.key == "starbucks"
    assert summary[0].signal_count == 2
    assert db.query(GraphRelationship).count() > 0
    match = db.query(PermitBrandMatch).first()
    match.review_status = "dismissed"
    db.commit()
    identity = match.id
    third = run("default-org", execute=True, permit_limit=2, session_factory=factory)
    assert third["permits"]["matches_created"] == 0
    db.expire_all()
    assert db.get(PermitBrandMatch, identity).review_status == "dismissed"
    assert list_brand_expansion_summaries(db, days=180, signal_cohort="national_retail")[0].signal_count == 1


@pytest.mark.parametrize("kwargs", [
    {"organization_id": ""}, {"organization_id": DEMO_ORG_ID},
    {"permit_limit": 25001}, {"planning_limit": 101}, {"batch_size": 501},
    {"permit_limit": True}, {"permit_limit": 0, "planning_limit": 0},
    {"after_permit_id": ""},
    {"after_planning_id": "x" * 37},
])
def test_limits_fail_before_opening_database(kwargs):
    args = {"organization_id": "default-org", **kwargs}
    forbidden = Mock(side_effect=AssertionError("Database must not open"))
    with pytest.raises(ValueError, match="bounded"):
        run(**args, session_factory=forbidden)
    assert not forbidden.called


def test_inactive_or_missing_tenant_rejected(db):
    _, factory = fixture(db)
    with pytest.raises(ValueError, match="Active destination"):
        run("missing-org", execute=True, session_factory=factory)
    assert db.query(BrandProfile).count() == 0


def test_disabled_stream_is_skipped_not_reported_partial(db):
    _, factory = fixture(db)
    result = run("default-org", execute=True, permit_limit=0, planning_limit=1, session_factory=factory)
    assert result["status"] == "completed"
    assert result["permits"]["skipped"] and not result["permits"]["has_more"]
