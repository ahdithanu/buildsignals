"""The browser fixture must populate real normalizers without source/model I/O."""
from app.models.graph import GraphEntityLink
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.parcel import NearbyParcelSearch, ParcelRecord
from app.models.planning import PlanningRecord
from e2e.coverage_map_fixture import seed_coverage_map_fixture


def test_synthetic_browser_inventory_exceeds_first_page_and_retains_unmapped(db, tmp_path):
    if db.get(Organization, 'default-org') is None:
        db.add(Organization(id='default-org', name='Synthetic coverage browser', slug='synthetic-coverage-browser'))
        db.commit()
    seed_coverage_map_fixture(db, 'default-org', 'synthetic-user', tmp_path)
    assert db.query(PermitRecord).count() == 145
    assert db.query(PlanningRecord).count() == 2
    assert db.query(ParcelRecord).count() == 70
    assert db.query(PermitRecord).filter(PermitRecord.latitude.is_(None)).count() == 54
    assert db.query(GraphEntityLink).filter_by(record_type='parcel').count() == 70
    assert db.query(RawSourceRecord).count() == 217
    assert db.query(NearbyParcelSearch).count() == 0
