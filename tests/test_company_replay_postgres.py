"""Real operator replay with forced RLS and rollback-only PostgreSQL fixtures."""
import hashlib
import os
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app.db import _set_rls_org
from app.models.brand import BrandAlias, BrandProfile, PermitBrandMatch
from app.models.graph import GraphEntityLink, GraphRelationshipEvidence
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.services.brand_intelligence import list_brand_expansion_summaries, load_brand_catalog
from app.services.demo_access import demo_read_only
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from scripts.backfill_company_intelligence import run

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires migrated disposable restricted-role PostgreSQL")


@contextmanager
def tenant_session(factory, org):
    token = set_current_context(RequestContext(org, "company-replay-postgres-test"))
    try:
        with factory() as db:
            yield db
    finally:
        reset_current_context(token)


@pytest.fixture
def postgres_replay():
    org, other = str(uuid4()), str(uuid4())
    token = set_current_context(RequestContext(org, "company-replay-postgres-test"))
    demo_token = demo_read_only.set(False)
    engine = create_engine(URL)
    assert engine.dialect.name == "postgresql"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            factory = sessionmaker(bind=connection, autoflush=False,
                                   join_transaction_mode="create_savepoint")
            event.listen(factory, "after_begin", _set_rls_org)
            try:
                role = connection.execute(text(
                    "SELECT rolsuper, rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user"
                )).one()
                assert role == (False, False)
                yield factory, org, other
                assert transaction.is_active, "Worker commits must not escape the outer transaction"
            finally:
                event.remove(factory, "after_begin", _set_rls_org)
                if transaction.is_active:
                    transaction.rollback()
        with engine.connect() as connection:
            assert connection.scalar(text(
                "SELECT count(*) FROM public.organizations WHERE id=ANY(:ids)"
            ), {"ids": [org, other]}) == 0
    finally:
        engine.dispose()
        demo_read_only.reset(demo_token)
        reset_current_context(token)


def snapshot(row, *, exclude=()):
    return deepcopy({column.name: getattr(row, column.name)
                     for column in row.__table__.columns if column.name not in exclude})


def stored_evidence(db, ids):
    return {
        "permit": snapshot(db.get(PermitRecord, ids["permit"])),
        "planning": snapshot(db.get(PlanningRecord, ids["planning"]), exclude=(
            "signal_categories", "priority_reasons", "priority_score",
        )),
        "sources": [snapshot(db.get(IngestionSource, identity)) for identity in ids["sources"]],
        "raw": [snapshot(db.get(RawSourceRecord, identity)) for identity in ids["raw"]],
        "runs": [snapshot(db.get(IngestionRun, identity)) for identity in ids["runs"]],
    }


def seed_stored_records(factory, org, city):
    now = datetime.now(timezone.utc)
    observed = now - timedelta(days=7)
    ids = {"sources": [], "raw": [], "runs": []}
    with tenant_session(factory, org) as db:
        db.add(Organization(id=org, name="Synthetic replay tenant", slug=f"company-replay-{org}"))
        db.flush()
        for kind, company in (("permit", "Starbucks"), ("planning", "Costco")):
            source = IngestionSource(
                organization_id=org, key=f"stored-{kind}", name=f"Synthetic stored {kind}",
                record_type=kind, adapter="json_api", is_active=True,
                base_url="https://example.invalid/never-fetch",
                created_at=observed, updated_at=observed,
            )
            db.add(source)
            db.flush()
            ingestion_run = IngestionRun(
                organization_id=org, source_id=source.id, status="completed", trigger="manual",
                started_at=observed, heartbeat_at=observed, completed_at=observed,
                records_seen=1, records_inserted=1,
            )
            db.add(ingestion_run)
            db.flush()
            identity = str(uuid4())
            payload = {"synthetic": True, "company": company, "record_id": identity}
            raw = RawSourceRecord(
                organization_id=org, source_id=source.id, run_id=ingestion_run.id,
                external_record_id=identity, record_type=kind,
                content_hash=hashlib.sha256(identity.encode()).hexdigest(), payload=payload,
                received_at=observed, source_updated_at=observed - timedelta(days=1),
            )
            db.add(raw)
            db.flush()
            common = dict(
                id=identity, organization_id=org, source_id=source.id,
                latest_raw_record_id=raw.id, external_record_id=identity,
                normalization_hash="a" * 64, project_name=f"{company} retail site",
                address="100 Synthetic Main St", city=city, state="TX", parcel_id="001-0007",
                source_url="https://example.invalid/evidence", first_seen_at=observed,
                last_seen_at=observed, created_at=observed, updated_at=observed,
            )
            if kind == "permit":
                record = PermitRecord(
                    **common, approval_stage="pre_approval", status="Under Review",
                    permit_type="Commercial Retail", description="Retail tenant improvement",
                    filed_at=observed - timedelta(days=1), status_updated_at=observed,
                )
            else:
                record = PlanningRecord(
                    **common, title="Costco retail site plan", summary="New retail store site plan",
                    event_type="site_plan", stage="scheduled", reference_number="CASE-001",
                    published_at=observed - timedelta(days=1), meeting_at=observed + timedelta(days=1),
                )
            db.add(record)
            ids[kind] = identity
            ids["sources"].append(source.id)
            ids["raw"].append(raw.id)
            ids["runs"].append(ingestion_run.id)
        db.commit()
        before = stored_evidence(db, ids)
    return ids, before


def test_real_operator_repairs_missing_catalog_and_both_streams_without_cross_tenant_reads(
    postgres_replay, monkeypatch,
):
    factory, org, other = postgres_replay
    own, before = seed_stored_records(factory, org, "Own Test City")
    foreign, foreign_before = seed_stored_records(factory, other, "Other Test City")
    from app.services import llm_client
    from app.services.ingestion.connectors.base import RetryingHttpClient

    forbidden = Mock(side_effect=AssertionError("Stored replay must not fetch sources or models"))
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr(RetryingHttpClient, "get_bytes", forbidden)
    monkeypatch.setattr(RetryingHttpClient, "get_json", forbidden)
    monkeypatch.setattr(llm_client, "get_default_llm_client", forbidden)
    # Create a positive foreign-tenant control before the missing-catalog repair.
    foreign_result = run(other, execute=True, permit_limit=1, planning_limit=1,
                         batch_size=1, session_factory=factory)
    assert foreign_result["status"] == "completed"
    with tenant_session(factory, org) as db:
        assert db.query(BrandProfile).count() == db.query(BrandAlias).count() == 0
        assert db.query(PermitBrandMatch).count() == db.query(PlanningCompanyMatch).count() == 0
        assert list_brand_expansion_summaries(db, days=180, signal_cohort="national_retail") == []

    result = run(org, execute=True, permit_limit=1, planning_limit=1,
                 batch_size=1, session_factory=factory)
    assert result["status"] == "completed"
    assert result["catalog"]["created"] == len(load_brand_catalog())
    for kind in ("permits", "planning"):
        assert result[kind]["scanned"] == result[kind]["matches_created"] == 1
        assert result[kind]["matches_refreshed"] == result[kind]["matches_retracted"] == 0
        assert not result[kind]["has_more"]

    with tenant_session(factory, org) as db:
        assert stored_evidence(db, own) == before
        assert db.query(BrandProfile).count() == len(load_brand_catalog())
        assert db.query(BrandAlias).count() > 0
        permit_match = db.query(PermitBrandMatch).one()
        planning_match = db.query(PlanningCompanyMatch).one()
        assert permit_match.permit_id == own["permit"] and permit_match.latest_raw_record_id == own["raw"][0]
        assert planning_match.planning_record_id == own["planning"] and planning_match.raw_record_id == own["raw"][1]
        summaries = list_brand_expansion_summaries(db, days=180, signal_cohort="national_retail")
        assert {row.brand.key: (row.signal_count, row.planning_count) for row in summaries} == {
            "starbucks": (1, 0), "costco": (1, 1),
        }
        assert all(market.city == "Own Test City" for row in summaries for market in row.markets)
        assert db.query(GraphEntityLink).filter(GraphEntityLink.record_id.in_([
            own["permit"], own["planning"],
        ])).count() == 2
        assert db.query(GraphRelationshipEvidence).filter(
            GraphRelationshipEvidence.source_id.in_(own["raw"]),
        ).count() > 0
        # These checks deliberately omit active_query and application tenant filters.
        assert db.scalars(select(PermitRecord.id)).all() == [own["permit"]]
        assert db.scalars(select(PlanningRecord.id)).all() == [own["planning"]]
        assert db.scalar(text("SELECT count(*) FROM public.permit_brand_matches WHERE permit_id=:id"),
                         {"id": foreign["permit"]}) == 0
        assert db.scalar(text("SELECT count(*) FROM public.planning_company_matches WHERE planning_record_id=:id"),
                         {"id": foreign["planning"]}) == 0
        assert db.scalar(text("SELECT count(*) FROM public.raw_source_records WHERE id=ANY(:ids)"),
                         {"ids": foreign["raw"]}) == 0
        assert db.scalar(text("SELECT count(*) FROM public.brand_profiles WHERE organization_id=:org"),
                         {"org": other}) == 0

    replay = run(org, execute=True, permit_limit=1, planning_limit=1,
                 batch_size=1, session_factory=factory)
    assert replay["status"] == "completed" and replay["catalog"]["created"] == 0
    assert replay["permits"]["matches_created"] == replay["planning"]["matches_created"] == 0
    with tenant_session(factory, org) as db:
        assert stored_evidence(db, own) == before
        assert db.query(PermitBrandMatch).count() == db.query(PlanningCompanyMatch).count() == 1
    with tenant_session(factory, other) as db:
        assert stored_evidence(db, foreign) == foreign_before
        assert db.query(PermitBrandMatch).count() == db.query(PlanningCompanyMatch).count() == 1
        assert db.scalar(text("SELECT count(*) FROM public.raw_source_records WHERE id=ANY(:ids)"),
                         {"ids": own["raw"]}) == 0
    assert not forbidden.called
