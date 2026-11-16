"""Synthetic local-only saved nearby parcel, not retained market inventory."""
from datetime import datetime, timedelta, timezone


def seed_parcel_use_fixture(db, org_id, user_id):
    from app.models.deal import Deal
    from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
    from app.models.parcel import (
        NearbyParcelCandidate,
        NearbyParcelSearch,
        ParcelFact,
        ParcelRecord,
    )
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

    token = set_current_context(RequestContext(org_id, user_id))
    try:
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        source = IngestionSource(
            id='synthetic-use-source', organization_id=org_id, key='synthetic-use-evidence',
            name='SYNTHETIC zoning fixture', adapter='manual', record_type='parcel', is_active=False,
            settings={'synthetic_e2e_fixture': True, 'schedule': {'enabled': False}},
        )
        db.add(source); db.flush()
        run = IngestionRun(organization_id=org_id, source_id=source.id, status='completed')
        db.add(run); db.flush()
        raw = RawSourceRecord(
            organization_id=org_id, source_id=source.id, run_id=run.id,
            external_record_id='SYNTHETIC-use', record_type='parcel', content_hash='b' * 64,
            payload={'synthetic_e2e_fixture': True, 'zoning_code': 'SYNTHETIC-B2'}, received_at=now,
        )
        db.add(raw); db.flush()
        parcel = ParcelRecord(
            id='synthetic-use-parcel', organization_id=org_id, source_id=source.id,
            latest_raw_record_id=raw.id, external_parcel_id='SYNTHETIC-use',
            jurisdiction='SYNTHETIC authority', state='NJ', address='SYNTHETIC nearby lot',
            latitude=39.92, longitude=-75.03, zoning_code='SYNTHETIC-B2',
        )
        permit = PermitRecord(
            id='synthetic-use-permit', organization_id=org_id, source_id=source.id,
            latest_raw_record_id=raw.id, external_record_id='SYNTHETIC-use-anchor',
            normalization_hash='c' * 64, latitude=39.921, longitude=-75.031,
        )
        deal = Deal(id='synthetic-use-deal', organization_id=org_id, created_by=user_id,
                    name='SYNTHETIC nearby parcel journey', city='SYNTHETIC', state='NJ')
        db.add_all([parcel, permit, deal]); db.flush()
        db.add(ParcelFact(
            organization_id=org_id, parcel_id=parcel.id, raw_source_record_id=raw.id,
            fact_type='zoning', value={'zoning_code': 'SYNTHETIC-B2'}, source_system=source.key,
            confidence=1, observed_at=now, last_verified_at=now, valid_from=now, is_current=True,
        ))
        search = NearbyParcelSearch(
            id='synthetic-use-search', organization_id=org_id, deal_id=deal.id,
            anchor_permit_id=permit.id, anchor_latitude=permit.latitude, anchor_longitude=permit.longitude,
            radius_miles=0.25, persona='developer', as_of=now, ranker_version='synthetic-test',
        )
        db.add(search); db.flush()
        db.add(NearbyParcelCandidate(
            organization_id=org_id, search_id=search.id, parcel_id=parcel.id,
            rank=1, distance_miles=0.1, score=0, score_confidence=0,
            explanation={'synthetic_e2e_fixture': True}, ranker_version='synthetic-test',
        ))
        db.commit()
    finally:
        reset_current_context(token)
