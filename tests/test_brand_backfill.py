from __future__ import annotations

from app.models.brand import BrandProfile, PermitBrandMatch
from app.models.graph import GraphRelationship
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.services.brand_intelligence import (
    backfill_brand_matches_batch,
    load_brand_catalog,
    sync_brand_catalog,
)


def _seed_permits(db, permits: list[dict[str, str]]) -> list[PermitRecord]:
    source = IngestionSource(
        organization_id="default-org",
        key="brand-backfill-test",
        name="Brand backfill test",
        adapter="csv",
        record_type="permit",
    )
    db.add(source)
    db.flush()
    run = IngestionRun(
        organization_id="default-org",
        source_id=source.id,
        status="completed",
    )
    db.add(run)
    db.flush()

    rows = []
    for index, values in enumerate(permits, start=1):
        permit_id = f"00000000-0000-0000-0000-{index:012d}"
        external_id = f"backfill-{index}"
        raw = RawSourceRecord(
            organization_id="default-org",
            source_id=source.id,
            run_id=run.id,
            external_record_id=external_id,
            record_type="permit",
            content_hash=f"{index:064x}",
            payload=dict(values),
        )
        db.add(raw)
        db.flush()
        permit = PermitRecord(
            id=permit_id,
            organization_id="default-org",
            source_id=source.id,
            latest_raw_record_id=raw.id,
            external_record_id=external_id,
            normalization_hash=f"{index:064x}",
            approval_stage=values.get("approval_stage", "pre_approval"),
            status="Under Review",
            permit_type=values.get("permit_type", "Commercial Retail"),
            project_name=values.get("project_name"),
            description=values.get("description"),
            developer_name=values.get("developer_name"),
            address=f"{index}00 Main St",
            city="Austin",
            state="TX",
        )
        db.add(permit)
        rows.append(permit)
    db.commit()
    return rows


def _sync_catalog(db) -> None:
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()


def test_backfill_detects_brands_in_existing_permits(db):
    permits = _seed_permits(db, [{
        "project_name": "Coffee tenant improvement",
        "description": "Interior retail build-out for Starbucks Coffee",
    }])
    _sync_catalog(db)

    result = backfill_brand_matches_batch(db)
    db.commit()

    match = db.query(PermitBrandMatch).one()
    assert result.scanned == 1
    assert result.matches_created == 1
    assert result.matches_refreshed == 0
    assert result.matches_retracted == 0
    assert result.next_cursor == permits[0].id
    assert result.has_more is False
    assert match.brand.key == "starbucks"
    assert match.permit_id == permits[0].id
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).one()
    assert relationship.is_current is True
    assert relationship.attributes["signal_cohort"] == "national_retail"


def test_backfill_is_idempotent_and_refreshes_existing_match(db):
    _seed_permits(db, [{
        "project_name": "Starbucks tenant improvement",
        "description": "New retail store build-out",
    }])
    _sync_catalog(db)

    first = backfill_brand_matches_batch(db)
    db.commit()
    match_id = db.query(PermitBrandMatch.id).scalar()
    second = backfill_brand_matches_batch(db)
    db.commit()

    assert first.matches_created == 1
    assert second.matches_created == 0
    assert second.matches_refreshed == 1
    assert second.matches_retracted == 0
    assert db.query(PermitBrandMatch).count() == 1
    assert db.query(PermitBrandMatch.id).scalar() == match_id


def test_backfill_detects_toll_brothers_as_major_builder(db):
    permits = _seed_permits(db, [{
        "permit_type": "Residential Development",
        "project_name": "Oak Ridge residential subdivision",
        "description": "Site plan for a new single-family residential subdivision",
        "developer_name": "Toll Brothers",
    }])
    _sync_catalog(db)

    result = backfill_brand_matches_batch(db)
    db.commit()

    match = db.query(PermitBrandMatch).one()
    brand = db.query(BrandProfile).filter_by(id=match.brand_id).one()
    assert result.matches_created == 1
    assert match.permit_id == permits[0].id
    assert brand.key == "toll_brothers"
    assert brand.signal_cohort == "major_builder"
    assert "major_builder_exact_alias" in match.rule_ids


def test_backfill_paginates_and_resumes_after_cursor(db):
    permits = _seed_permits(db, [
        {
            "project_name": "Starbucks tenant improvement",
            "description": "New retail store build-out",
        },
        {
            "project_name": "Generic office renovation",
            "description": "Interior office alterations",
        },
        {
            "permit_type": "Residential Development",
            "project_name": "New residential subdivision",
            "description": "Single-family residential subdivision",
            "developer_name": "Toll Brothers",
        },
    ])
    _sync_catalog(db)

    first = backfill_brand_matches_batch(db, batch_size=2)
    db.commit()
    second = backfill_brand_matches_batch(
        db, after_id=first.next_cursor, batch_size=2
    )
    db.commit()

    assert first.scanned == 2
    assert first.next_cursor == permits[1].id
    assert first.has_more is True
    assert second.scanned == 1
    assert second.next_cursor == permits[2].id
    assert second.has_more is False
    assert db.query(PermitBrandMatch).count() == 2


def test_backfill_retracts_candidate_when_evidence_no_longer_matches(db):
    permits = _seed_permits(db, [{
        "project_name": "Starbucks tenant improvement",
        "description": "New retail store build-out",
    }])
    _sync_catalog(db)
    backfill_brand_matches_batch(db)
    db.commit()

    permits[0].project_name = "Main Street tenant improvement"
    permits[0].description = "Interior retail renovation for an unidentified tenant"
    db.commit()
    result = backfill_brand_matches_batch(db)
    db.commit()

    match = db.query(PermitBrandMatch).one()
    assert result.matches_created == 0
    assert result.matches_refreshed == 0
    assert result.matches_retracted == 1
    assert match.review_status == "retracted"


def test_backfill_validates_batch_size(db):
    for invalid_size in (0, 5_001):
        try:
            backfill_brand_matches_batch(db, batch_size=invalid_size)
        except ValueError as exc:
            assert "batch_size" in str(exc)
        else:
            raise AssertionError(f"batch_size={invalid_size} should be rejected")
