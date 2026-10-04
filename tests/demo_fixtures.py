"""One real CC0 Columbus record, captured 2026-09-19; not demo inventory totals.

Source: City of Columbus Building Permits FeatureServer/0, OBJECTID 161293.
Only reviewed permit/site/lifecycle fields; no personal contact information.
"""
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models.ingestion import IngestionRun
from app.models.organization import Organization
from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate
from app.services.ingestion.service import create_source, replay_permit_snapshot
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

RECORD = {
    "OBJECTID": 161293, "B1_ALT_ID": "ACS2402169", "B1_PARCEL_NBR": "010066782",
    "SITE_ADDRESS": "55 E STATE ST", "PERMIT_STATUS": "Permit Issued",
    "ISSUED_DT": 1704758400000, "VALUE_DESC": "Mechanical Permits or NA",
    "APPLICANT_BUS_NAME": "FIRE SYSTEMS PROFESSIONALS INC",
    "ACA_URL": "https://ca.columbus.gov/permits/urlrouting.ashx?type=1000&Module=Building&capID1=24CAP&capID2=00000&capID3=0006L&AgencyCode=COLUMBUS",
}
CAPTURED = datetime(2026, 9, 19, 19, 12, 53, 477985, tzinfo=timezone.utc)


def create_snapshot(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    context = set_current_context(RequestContext("fixture-columbus", "fixture-user"))
    try:
        with Session(engine) as db:
            db.add(Organization(id="fixture-columbus", name="Test snapshot", slug="test-snapshot"))
            db.flush()
            source = create_source(db, IngestionSourceCreate(
                key="columbus_oh_commercial_building_permits", name="Columbus commercial permits",
                adapter="arcgis", jurisdiction="Columbus", is_active=False,
                settings={"field_allowlist": list(RECORD),
                          "defaults": {"city": "Columbus", "state": "OH", "approval_stage": "approved"},
                          "historical_qualification": {"start_inclusive": "2024-01-01", "end_exclusive": "2024-02-01"}},
                field_mappings=[FieldMappingCreate(source_field=key, canonical_field=value,
                                                  value_semantics="legal_entity" if value == "applicant_name" else "unknown") for key, value in {
                    "B1_ALT_ID": "source_record_id", "B1_PARCEL_NBR": "parcel_id", "SITE_ADDRESS": "address",
                    "PERMIT_STATUS": "status", "ISSUED_DT": "issued_at", "VALUE_DESC": "description", "ACA_URL": "source_url",
                    "APPLICANT_BUS_NAME": "applicant_name",
                }.items()],
            ))
            run = IngestionRun(organization_id="fixture-columbus", source_id=source.id,
                               status="completed", records_seen=1, records_inserted=1)
            db.add(run)
            db.flush()
            replay_permit_snapshot(db, source, run.id, RECORD, CAPTURED)
            db.commit()
    finally:
        reset_current_context(context)
        engine.dispose()
