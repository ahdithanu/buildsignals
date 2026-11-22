"""SYNTHETIC engineering E2E only: disposable CSV ingestion, never real inventory."""

import csv
from datetime import datetime, timezone
from pathlib import Path

from app.models.audit_log import AuditLog
from app.models.brand import PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import GraphRelationship
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.models.user import User
from app.schemas.ingestion import IngestionSourceCreate
from app.services.brand_intelligence import backfill_brand_matches_batch, list_deal_brand_matches
from app.services.company_catalog import ensure_company_catalog
from app.services.graph_service import entity_for_record, upsert_deal_graph_context
from app.services.ingestion.service import create_source, execute_source_run
from app.services.security import hash_password
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def seed_reviewed_anchor_fixture(db, directory):
    """Seed two untouched editor tenants; all record/raw/graph writes use ingestion."""
    for width in (1440, 390):
        org = Organization(name=f"SYNTHETIC reviewed anchor {width}", slug=f"synthetic-anchor-{width}")
        user = User(
            email=f"synthetic-reviewed-anchor-{width}@example.com",
            full_name=f"SYNTHETIC anchor editor {width}",
            password_hash=hash_password("E2eReviewedAnchorOnly42!"),
            is_active=True, is_superuser=False,
        )
        db.add_all([org, user])
        db.flush()
        db.add(OrganizationMembership(
            organization_id=org.id, user_id=user.id, role=MemberRole.editor, is_default=True,
        ))
        db.commit()
        token = set_current_context(RequestContext(org.id, user.id))
        try:
            ensure_company_catalog(db, org.id)
            now = datetime.now(timezone.utc).isoformat()
            address = "100 Synthetic Anchor Road"
            shared = {"city": "Synthetic Test City", "state": "FL"}
            parcel_reference = f"SYNTHETIC-ANCHOR-{width}-A"
            groups = {
                "permit": [{
                    "source_record_id": f"SYNTHETIC-ALDI-{width}",
                    "application_number": f"SYNTHETIC-ALDI-{width}",
                    "project_name": "SYNTHETIC ALDI retail build-out - engineering fixture only",
                    "description": "SYNTHETIC ALDI grocery retail tenant improvement, not a real filing",
                    "approval_stage": "pre_approval", "status": "Under Review", "filed_at": now,
                    "parcel_id": parcel_reference, "address": address, **shared,
                }],
                "parcel": [{
                    "source_record_id": parcel_reference, "parcel_group_id": parcel_reference,
                    "address": address, "latitude": 28.46, "longitude": -81.27,
                    "land_area_sq_ft": 25000, "observed_at": now, **shared,
                }, {
                    "source_record_id": f"SYNTHETIC-ANCHOR-{width}-B",
                    "parcel_group_id": f"SYNTHETIC-ANCHOR-{width}-B",
                    "address": "102 Synthetic Anchor Road", "latitude": 28.461, "longitude": -81.27,
                    "land_area_sq_ft": 18000, "observed_at": now, **shared,
                }],
            }
            for kind, rows in groups.items():
                path = Path(directory) / f"synthetic-reviewed-anchor-{width}-{kind}.csv"
                with path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                source = create_source(db, IngestionSourceCreate(
                    key=f"synthetic-reviewed-anchor-{width}-{kind}",
                    name=f"SYNTHETIC reviewed-anchor {kind} CSV", adapter="csv", record_type=kind,
                    base_url=str(path), jurisdiction="SYNTHETIC engineering fixture, FL",
                    settings={"synthetic_e2e_fixture": True, "schedule_mode": "manual",
                              "schedule": {"enabled": False}, "canary_enabled": False},
                    field_mappings=[{"source_field": field, "canonical_field": field} for field in rows[0]],
                ))
                db.commit()
                result = execute_source_run(db, source, max_pages=1)
                assert result.status == "completed" and result.records_failed == 0, (
                    "SYNTHETIC ingestion failed", kind, result.status, result.error_message,
                )
                assert result.records_inserted == len(rows)
            backfill_brand_matches_batch(db, batch_size=10)
            permit = db.query(PermitRecord).filter_by(organization_id=org.id).one()
            parcels = db.query(ParcelRecord).filter_by(organization_id=org.id).all()
            assert len(parcels) == 2
            assert permit.latitude is None and permit.longitude is None
            match = db.query(PermitBrandMatch).filter_by(organization_id=org.id).one()
            assert match.brand.name == "ALDI" and match.review_status == "candidate"
            assert permit.approval_stage == "pre_approval"
            for kind, records in (("permit", [permit]), ("parcel", parcels)):
                for record in records:
                    raw = db.query(RawSourceRecord).filter_by(id=record.latest_raw_record_id).one()
                    assert raw.organization_id == org.id and raw.source_id == record.source_id
                    assert raw.record_type == kind and record.normalization_hash
                    assert entity_for_record(db, kind, record.id) is not None
            deal = Deal(
                id=f"synthetic-anchor-deal-{width}", organization_id=org.id, created_by=user.id,
                name=f"SYNTHETIC ALDI anchor workflow {width}", address=address, **shared,
                property_type="Retail", source="SYNTHETIC engineering E2E only",
            )
            db.add(deal)
            db.flush()
            upsert_deal_graph_context(db, deal)
            assert [item.id for item in list_deal_brand_matches(db, deal.id)] == [match.id]
            for model in (NearbyParcelSearch, NearbyParcelCandidate):
                assert db.query(model).filter_by(organization_id=org.id).count() == 0
            assert db.query(GraphRelationship).filter_by(
                organization_id=org.id, source_system="reviewed_parcel_reference",
            ).count() == 0
            assert db.query(AuditLog).filter_by(
                organization_id=org.id, action="parcel_reference_accepted",
            ).count() == 0
            assert db.query(Deal).filter_by(organization_id=org.id).count() == 1
            db.commit()
        finally:
            reset_current_context(token)
