from datetime import datetime, timezone
from uuid import uuid4

from app.models.ingestion import IngestionSource, PermitRecord
from app.services import frontier_hotspots as fh
from app.services import investment_areas as areas
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)


def test_rank_hotspots_scores_acceleration_and_respects_min_recent():
    # One igniting cell (lots of recent, little prior) and one quiet cell.
    recs = []
    for _ in range(6):
        recs.append((44.012, -121.271, 2025, True, "27TH ST"))
    recs.append((44.012, -121.271, 2021, False, "27TH ST"))        # prior
    for _ in range(2):
        recs.append((44.050, -121.300, 2024, False, "QUIET RD"))   # below min_recent
    out = fh.rank_hotspots(recs, min_recent=3)
    assert out["reference_year"] == 2025
    assert len(out["hotspots"]) == 1                 # quiet cell filtered out
    hot = out["hotspots"][0]
    assert hot["recent"] == 6 and hot["prior"] == 1
    assert hot["acceleration"] == 6.0
    assert hot["dev_share"] == 1.0
    assert hot["sample_address"] == "27TH ST"


def test_rank_hotspots_ignores_malformed_rows_and_is_clockless_with_reference_year():
    recs = [(1000, -121, 2025, False, None),         # bad lat
            ("x", 0, 2025, False, None),             # bad type
            (44.0, -121.0, 2025, False, "A"),
            (44.0, -121.0, 2025, True, "A"),
            (44.0, -121.0, 2025, False, "A")]
    out = fh.rank_hotspots(recs, reference_year=2025, min_recent=3)
    assert out["hotspots"][0]["recent"] == 3


def _seed(db, org, key, coords_years):
    source = IngestionSource(organization_id=org, key=key, name="Synthetic", adapter="arcgis",
                             record_type="permit", is_active=True)
    db.add(source); db.flush()
    for i, (lat, lon, year, ptype) in enumerate(coords_years):
        db.add(PermitRecord(
            organization_id=org, source_id=source.id, latest_raw_record_id=str(uuid4()),
            external_record_id=f"r{i}", normalization_hash="c" * 64, latitude=lat, longitude=lon,
            permit_type=ptype, address="27TH ST",
            filed_at=datetime(year, 6, 1, tzinfo=timezone.utc)))
    db.commit()


def test_frontier_disabled_by_default_but_keeps_parcel_preview(db, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "FRONTIER_HOTSPOTS_ENABLED", False)
    token = set_current_context(RequestContext(str(uuid4()), SYSTEM_USER_ID))
    try:
        out = areas.frontier(db, "36100")
        assert out["status"] == "disabled"
        assert out["parcel_candidates"]["status"] == "research_preview"
    finally:
        reset_current_context(token)


def test_frontier_enabled_ranks_tenant_evidence_and_is_org_scoped(db, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "FRONTIER_HOTSPOTS_ENABLED", True)
    org_a, org_b = str(uuid4()), str(uuid4())
    recent = [(44.012, -121.271, y, "New Subdivision") for y in (2023, 2024, 2024, 2025)]
    _seed(db, org_a, "ocala_fl_gis_new_building_projects", recent + [(44.012, -121.271, 2021, "Alteration")])

    token = set_current_context(RequestContext(org_a, SYSTEM_USER_ID))
    try:
        out = areas.frontier(db, "36100")
        assert out["status"] == "research"
        assert out["hotspots"][0]["recent"] == 4 and out["hotspots"][0]["prior"] == 1
        assert out["hotspots"][0]["dev_share"] == 1.0          # subdivision keyword
        assert out["evidence_points"] == 5
    finally:
        reset_current_context(token)

    token = set_current_context(RequestContext(org_b, SYSTEM_USER_ID))
    try:
        out = areas.frontier(db, "36100")        # other tenant sees nothing
        assert out["status"] == "insufficient_data" and out["hotspots"] == []
    finally:
        reset_current_context(token)
