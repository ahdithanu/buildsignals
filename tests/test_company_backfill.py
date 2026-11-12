from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from app.models.brand import BrandProfile
from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphRelationship,
    GraphRelationshipEvidence,
    GraphRelationshipType,
)
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.company_backfill import backfill_planning_company_matches_batch
from app.services.demo_access import demo_read_only
from app.services.ingestion.service import _project_planning_to_graph
from app.services.planning_intelligence import enrich_planning_record
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

CAPTURED = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)


def seed(db, *, org="default-org", count=1):
    if db.get(Organization, org) is None:
        db.add(Organization(id=org, name="Synthetic planning", slug=org))
    token = set_current_context(RequestContext(org, "stored-replay-test"))
    try:
        sync_brand_catalog(db, load_brand_catalog())
        source = IngestionSource(
            organization_id=org, key="stored-planning", name="Stored planning",
            record_type="planning", adapter="json_api", is_active=False,
            base_url="https://example.invalid/never-fetch", created_at=CAPTURED, updated_at=CAPTURED,
        )
        db.add(source)
        db.flush()
        run = IngestionRun(organization_id=org, source_id=source.id, status="completed")
        db.add(run)
        db.flush()
        records = []
        for index in range(count):
            identity = f"{org}-planning-{index}"
            raw = RawSourceRecord(
                organization_id=org, source_id=source.id, run_id=run.id,
                external_record_id=identity, record_type="planning", content_hash=f"{index + 1:064x}",
                payload={"synthetic": True, "title": "Starbucks site plan"},
                received_at=CAPTURED, source_updated_at=CAPTURED,
            )
            db.add(raw)
            db.flush()
            record = PlanningRecord(
                id=identity, organization_id=org, source_id=source.id,
                latest_raw_record_id=raw.id, external_record_id=identity,
                normalization_hash="f" * 64, reference_number=f"CASE-{index}",
                event_type="site_plan", stage="scheduled", title="Starbucks site plan",
                summary="Retail tenant improvement", project_name="Synthetic project",
                address=f"{index + 1}00 Main St", city="Test City", state="TX", parcel_id=f"001-{index:03d}",
                source_url="https://example.invalid/planning-evidence", published_at=CAPTURED,
                meeting_at=CAPTURED, decision_at=CAPTURED, first_seen_at=CAPTURED,
                last_seen_at=CAPTURED, created_at=CAPTURED, updated_at=CAPTURED,
            )
            db.add(record)
            records.append(record)
        db.commit()
        return source, records
    finally:
        reset_current_context(token)


def snapshot(row, *, exclude=()):
    return deepcopy({column.name: getattr(row, column.name)
                     for column in row.__table__.columns if column.name not in exclude})


def graph_counts(db):
    return tuple(db.query(model).count() for model in (
        GraphEntity, GraphEntityLink, GraphRelationship, GraphRelationshipEvidence,
    ))


def named_edges(db, source, record):
    return db.query(GraphRelationship).filter(
        GraphRelationship.organization_id == record.organization_id,
        GraphRelationship.source_system == source.key,
        GraphRelationship.relationship_type == GraphRelationshipType.related_to,
        GraphRelationship.attributes["planning_record_id"].as_string() == record.id,
        GraphRelationship.attributes["role"].as_string().in_(
            ("tracked_company", "applicant", "owner", "developer"),
        ),
    ).all()


@pytest.mark.parametrize("transition", ["dismissed", "retracted"])
def test_replay_retires_previously_projected_ineligible_match_and_keeps_evidence(db, transition):
    source, records = seed(db)
    record = records[0]
    backfill_planning_company_matches_batch(db)
    db.commit()
    match = db.query(PlanningCompanyMatch).one()
    edge = named_edges(db, source, record)[0]
    edge_id = edge.id
    original_evidence = {row.id: snapshot(row) for row in edge.evidence}
    assert edge.is_current and original_evidence
    if transition == "dismissed":
        match.review_status = "dismissed"
    else:
        record.title = "Unidentified retail tenant site plan"
    db.commit()

    backfill_planning_company_matches_batch(db)
    db.commit()
    db.expire_all()
    assert db.get(PlanningCompanyMatch, match.id).review_status == transition
    edge = db.get(GraphRelationship, edge_id)
    assert not edge.is_current and edge.valid_to is not None
    assert {row.id: snapshot(row) for row in edge.evidence} == original_evidence
    assert not any(row.is_current for row in named_edges(db, source, record))
    counts, retired_at = graph_counts(db), edge.valid_to
    backfill_planning_company_matches_batch(db)
    db.commit()
    db.expire_all()
    assert graph_counts(db) == counts
    assert db.get(GraphRelationship, edge_id).valid_to == retired_at
    assert {row.id: snapshot(row) for row in db.get(GraphRelationship, edge_id).evidence} == original_evidence

    db.get(PlanningCompanyMatch, match.id).review_status = "confirmed"
    db.commit()
    backfill_planning_company_matches_batch(db)
    db.commit()
    db.expire_all()
    edge = db.get(GraphRelationship, edge_id)
    assert edge.is_current and edge.valid_to is None
    assert graph_counts(db) == counts
    assert {row.id: snapshot(row) for row in edge.evidence} == original_evidence


def test_ingestion_order_replay_has_one_current_edge_per_role_entity_and_preserves_other_edges(db):
    source, records = seed(db)
    record = records[0]
    record.title = "Starbucks ALDI retail site plan"
    record.applicant_name = "Synthetic Applicant LLC"
    record.owner_name = "Synthetic Owner LLC"
    record.developer_name = "Synthetic Developer LLC"
    matches = enrich_planning_record(db, record, record.latest_raw_record)
    assert len(matches) == 2
    # Ingestion does not promise the brand-ID ordering used by stored replay.
    ingestion_order = sorted(matches, key=lambda match: match.brand_id, reverse=True)
    _project_planning_to_graph(db, source, record, record.latest_raw_record, ingestion_order)
    db.commit()
    initial = named_edges(db, source, record)
    assert len(initial) == 5
    initial_ids = {row.id for row in initial}
    original_evidence = {row.id: snapshot(row) for edge in initial for row in edge.evidence}
    expected_pairs = {(edge.attributes["role"], edge.target_entity_id) for edge in initial}

    db.add(Organization(id="unrelated-replay-org", name="Unrelated", slug="unrelated-replay-org"))
    db.flush()
    unrelated = []
    for index, overrides in enumerate((
        {"organization_id": "unrelated-replay-org"},
        {"source_system": "another-planning-source"},
        {"attributes": {"role": "tracked_company", "planning_record_id": "another-record"}},
        {"attributes": {"role": "planning_subject", "planning_record_id": record.id}},
        {"relationship_type": GraphRelationshipType.developed_by},
    )):
        values = {
            "organization_id": record.organization_id,
            "source_entity_id": initial[0].source_entity_id,
            "target_entity_id": initial[0].target_entity_id,
            "source_system": source.key, "source_id": f"unrelated-{index}",
            "relationship_type": GraphRelationshipType.related_to,
            "attributes": {"role": "tracked_company", "planning_record_id": record.id},
        }
        values.update(overrides)
        unrelated.append(GraphRelationship(**values))
    db.add_all(unrelated)
    db.commit()
    unrelated_before = {row.id: snapshot(row) for row in unrelated}

    backfill_planning_company_matches_batch(db)
    db.commit()
    db.expire_all()
    current = [edge for edge in named_edges(db, source, record) if edge.is_current]
    pairs = [(edge.attributes["role"], edge.target_entity_id) for edge in current]
    assert len(pairs) == len(set(pairs)) == 5
    assert set(pairs) == expected_pairs
    retired = [edge for edge in named_edges(db, source, record) if not edge.is_current]
    assert len(retired) == 2
    assert all(edge.id in initial_ids and edge.valid_to is not None for edge in retired)
    assert {identity: snapshot(db.get(GraphRelationshipEvidence, identity))
            for identity in original_evidence} == original_evidence
    assert {identity: snapshot(db.get(GraphRelationship, identity))
            for identity in unrelated_before} == unrelated_before

    counts = graph_counts(db)
    current_ids = {edge.id for edge in current}
    backfill_planning_company_matches_batch(db)
    db.commit()
    db.expire_all()
    assert graph_counts(db) == counts
    assert {edge.id for edge in named_edges(db, source, record) if edge.is_current} == current_ids
    assert {identity: snapshot(db.get(GraphRelationship, identity))
            for identity in unrelated_before} == unrelated_before

    record.applicant_name, record.owner_name = "Replacement Applicant LLC", None
    db.commit()
    backfill_planning_company_matches_batch(db)
    db.commit()
    current = [edge for edge in named_edges(db, source, record) if edge.is_current]
    assert {(edge.attributes["role"], edge.target_entity.display_name) for edge in current} == {
        ("tracked_company", "Starbucks"), ("tracked_company", "ALDI"),
        ("applicant", "Replacement Applicant LLC"), ("developer", "Synthetic Developer LLC"),
    }
    assert {identity: snapshot(db.get(GraphRelationship, identity))
            for identity in unrelated_before} == unrelated_before


def test_stored_replay_preserves_source_provenance_and_uses_no_network_or_llm(db, monkeypatch):
    source, records = seed(db)
    record = records[0]
    raw = record.latest_raw_record
    original = (snapshot(source), snapshot(raw), snapshot(record, exclude=(
        "signal_categories", "priority_reasons", "priority_score",
    )))
    from app.services import llm_client
    from app.services.ingestion.connectors.base import RetryingHttpClient

    forbidden = Mock(side_effect=AssertionError("External work is forbidden"))
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr(RetryingHttpClient, "get_bytes", forbidden)
    monkeypatch.setattr(llm_client, "get_default_llm_client", forbidden)
    commit = Mock(wraps=db.commit)
    monkeypatch.setattr(db, "commit", commit)
    result = backfill_planning_company_matches_batch(db)
    assert result.scanned == result.matches_created == 1
    assert result.matches_refreshed == result.matches_retracted == 0
    assert result.next_cursor == record.id and not result.has_more
    assert not commit.called and not forbidden.called
    db.flush()
    db.expire_all()
    assert (snapshot(source), snapshot(raw), snapshot(record, exclude=(
        "signal_categories", "priority_reasons", "priority_score",
    ))) == original
    assert db.query(RawSourceRecord).count() == 1
    match = db.query(PlanningCompanyMatch).one()
    assert match.raw_record_id == raw.id and match.planning_record_id == record.id
    assert match.brand.key == "starbucks" and match.review_status == "candidate"
    assert db.query(GraphEntityLink).filter_by(record_type="planning", record_id=record.id).count() == 1
    for evidence in db.query(GraphRelationshipEvidence).all():
        assert evidence.source_id == raw.id
        assert evidence.observed_at == record.published_at
        assert evidence.payload["raw_record_id"] == raw.id
        assert evidence.payload["content_hash"] == raw.content_hash


def test_replay_is_idempotent_for_matches_and_graph(db):
    seed(db)
    first = backfill_planning_company_matches_batch(db)
    db.commit()
    match = db.query(PlanningCompanyMatch).one()
    identity, first_seen = match.id, match.first_seen_at
    counts = graph_counts(db)
    second = backfill_planning_company_matches_batch(db)
    db.commit()
    assert first.matches_created == 1
    assert second.matches_created == second.matches_retracted == 0
    assert second.matches_refreshed == 1
    assert graph_counts(db) == counts
    match = db.query(PlanningCompanyMatch).one()
    assert (match.id, match.first_seen_at) == (identity, first_seen)


def test_review_decisions_are_preserved_and_only_eligible_matches_are_projected(db):
    _, records = seed(db)
    record = records[0]
    record.title = "Starbucks Costco ALDI retail site plan"
    statuses = {"starbucks": "confirmed", "costco": "dismissed", "aldi": "retracted", "lidl": "candidate"}
    for key, status in statuses.items():
        brand = db.query(BrandProfile).filter_by(organization_id="default-org", key=key).one()
        db.add(PlanningCompanyMatch(
            organization_id="default-org", planning_record_id=record.id, brand_id=brand.id,
            raw_record_id=record.latest_raw_record_id, review_status=status, confidence=0.8,
            matched_alias=brand.name, matched_field="title", excerpt="Original evidence",
            detector_version="prior-detector", first_seen_at=CAPTURED, last_seen_at=CAPTURED,
        ))
    db.commit()
    identities = {match.brand.key: match.id for match in db.query(PlanningCompanyMatch).all()}
    result = backfill_planning_company_matches_batch(db)
    db.commit()
    assert result.matches_created == 0 and result.matches_retracted == 1
    for match in db.query(PlanningCompanyMatch).all():
        assert match.id == identities[match.brand.key]
        expected = {**statuses, "lidl": "retracted", "aldi": "candidate"}
        assert match.review_status == expected[match.brand.key]
    tracked = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["role"].as_string() == "tracked_company",
    ).all()
    assert {relationship.target_entity.display_name for relationship in tracked} == {"Starbucks", "ALDI"}


def test_confirmed_match_is_not_removed_when_alias_is_no_longer_detected(db):
    _, records = seed(db)
    backfill_planning_company_matches_batch(db)
    match = db.query(PlanningCompanyMatch).one()
    match.review_status = "confirmed"
    records[0].title = "Unidentified tenant site plan"
    db.commit()
    backfill_planning_company_matches_batch(db)
    db.commit()
    assert db.query(PlanningCompanyMatch).one().review_status == "confirmed"


def test_scoped_replay_and_cursor_do_not_touch_another_organization(db):
    _, own = seed(db, count=3)
    _, foreign = seed(db, org="foreign-org")
    first = backfill_planning_company_matches_batch(db, batch_size=2)
    assert first.scanned == 2 and first.has_more and first.next_cursor == own[1].id
    second = backfill_planning_company_matches_batch(db, batch_size=2, after_id=first.next_cursor)
    assert second.scanned == 1 and not second.has_more and second.next_cursor == own[2].id
    empty = backfill_planning_company_matches_batch(db, after_id=second.next_cursor)
    assert empty.scanned == 0 and empty.next_cursor == second.next_cursor and not empty.has_more
    assert db.query(PlanningCompanyMatch).filter_by(organization_id="foreign-org").count() == 0
    assert foreign[0].priority_score == 0
    token = set_current_context(RequestContext("foreign-org", "other-user"))
    try:
        assert backfill_planning_company_matches_batch(db).matches_created == 1
        assert db.query(PlanningCompanyMatch).filter_by(organization_id="default-org").count() == 3
    finally:
        reset_current_context(token)


def test_invalid_evidence_scope_stops_the_entire_batch_before_enrichment(db):
    _, records = seed(db, count=2)
    _, foreign = seed(db, org="foreign-org")
    records[1].latest_raw_record_id = foreign[0].latest_raw_record_id
    db.commit()
    with pytest.raises(ValueError, match="provenance"):
        backfill_planning_company_matches_batch(db)
    assert db.query(PlanningCompanyMatch).count() == 0
    assert graph_counts(db) == (0, 0, 0, 0)


@pytest.mark.parametrize("batch_size", [0, 5001, True, 1.5, "2", None])
def test_invalid_bounds_fail_before_query(batch_size):
    db = Mock()
    with pytest.raises(ValueError, match="batch_size"):
        backfill_planning_company_matches_batch(db, batch_size=batch_size)
    assert not db.query.called


def test_demo_replay_is_rejected_before_query():
    db = Mock()
    token = demo_read_only.set(True)
    try:
        with pytest.raises(PermissionError):
            backfill_planning_company_matches_batch(db)
        assert not db.query.called
    finally:
        demo_read_only.reset(token)


@pytest.mark.parametrize("after_id", ["", "x" * 37, 12])
def test_invalid_cursor_fails_before_query(after_id):
    db = Mock()
    with pytest.raises(ValueError, match="after_id"):
        backfill_planning_company_matches_batch(db, after_id=after_id)
    assert not db.query.called


def test_selection_and_existing_match_queries_compile_postgres_row_locks(db):
    seed(db)
    locked = []

    def capture(state):
        if state.is_select and state.statement._for_update_arg is not None:
            locked.append(str(state.statement.compile(dialect=postgresql.dialect())))

    event.listen(db, "do_orm_execute", capture)
    try:
        backfill_planning_company_matches_batch(db)
    finally:
        event.remove(db, "do_orm_execute", capture)
    assert any(sql.rstrip().endswith("FOR UPDATE OF planning_records") for sql in locked)
    assert any("FROM planning_company_matches" in sql and sql.rstrip().endswith("FOR UPDATE")
               for sql in locked)
    assert any("FROM graph_relationships" in sql and sql.rstrip().endswith("FOR UPDATE")
               for sql in locked)


def test_cached_planning_and_review_state_are_refreshed_before_replay(db):
    _, records = seed(db)
    record = records[0]
    backfill_planning_company_matches_batch(db)
    db.commit()
    match = db.query(PlanningCompanyMatch).one()
    assert match.review_status == "candidate" and record.title == "Starbucks site plan"
    db.execute(PlanningCompanyMatch.__table__.update().where(
        PlanningCompanyMatch.id == match.id,
    ).values(review_status="dismissed"))
    db.execute(PlanningRecord.__table__.update().where(
        PlanningRecord.id == record.id,
    ).values(title="ALDI retail site plan"))
    assert match.review_status == "candidate" and record.title == "Starbucks site plan"
    result = backfill_planning_company_matches_batch(db)
    assert result.matches_created == 1
    assert match.review_status == "dismissed" and record.title == "ALDI retail site plan"
    assert {row.brand.key: row.review_status for row in db.query(PlanningCompanyMatch).all()} == {
        "starbucks": "dismissed", "aldi": "candidate",
    }


def test_new_planning_match_has_brand_without_autoflush(db):
    _, records = seed(db)
    db.autoflush = False
    record = records[0]
    matches = enrich_planning_record(db, record, record.latest_raw_record)
    assert len(matches) == 1
    assert matches[0].brand.key == "starbucks"
    assert "Tracked company mentioned: Starbucks" in record.priority_reasons
