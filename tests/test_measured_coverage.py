from datetime import datetime, timedelta, timezone

from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.parcel import ParcelRecord
from app.services.ingestion.measured_coverage import measured_coverage
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def seed(db, org, key, *, count=0, source_date=None, now=None):
    if not db.get(Organization, org):
        db.add(Organization(id=org, name=org, slug=org))
        db.flush()
    source = IngestionSource(organization_id=org, key=key, name=key, adapter="csv", record_type="parcel", jurisdiction="Florida")
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id=org, source_id=source.id, status="completed", trigger="manual")
    db.add(run)
    db.flush()
    for i in range(count):
        raw = RawSourceRecord(organization_id=org, source_id=source.id, run_id=run.id,
                              external_record_id=str(i), content_hash=str(i), record_type="parcel",
                              payload={}, source_updated_at=source_date)
        db.add(raw)
        db.flush()
        db.add(ParcelRecord(organization_id=org, source_id=source.id, latest_raw_record_id=raw.id,
                            external_parcel_id=str(i), state="FL" if i == 0 else None,
                            latitude=27.1 if i == 0 else 200, longitude=-82,
                            jurisdiction="County A", last_seen_at=now))
    db.commit()
    return source


def test_counts_are_measured_scoped_and_do_not_confuse_collection_with_freshness(db):
    now = datetime.now(timezone.utc)
    seed(db, "org-a", "populated", count=2, source_date=now - timedelta(days=365), now=now)
    seed(db, "org-a", "empty", now=now)
    seed(db, "org-b", "private", count=3, now=now)
    token = set_current_context(RequestContext("org-a", "test"))
    try:
        report = measured_coverage(db, record_type="parcel", now=now)
    finally:
        reset_current_context(token)
    assert [s["source_key"] for s in report["sources"]] == ["empty", "populated"]
    assert report["sources"][0]["stored_records"] == 0
    states = report["sources"][1]["observed_states"]
    assert {s["state"] for s in states} == {None, "FL"}
    assert sum(s["geocoded_records"] for s in states) == 1
    assert next(s for s in states if s["state"] == "FL")["min_latitude"] == 27.1
    assert next(s for s in states if s["state"] is None)["max_latitude"] is None
    assert sum(s["recently_seen_records"] for s in states) == 2
    assert sum(s["recent_source_date_records"] for s in states) == 0


def test_unknown_dates_pagination_and_no_synthetic_rows(db):
    now = datetime.now(timezone.utc)
    seed(db, "org-a", "a", count=1, now=now)
    seed(db, "org-a", "b", now=now)
    token = set_current_context(RequestContext("org-a", "test"))
    try:
        first = measured_coverage(db, record_type="parcel", limit=1, now=now)
        empty = measured_coverage(db, record_type="parcel", offset=2)
    finally:
        reset_current_context(token)
    assert first["has_more"]
    assert first["sources"][0]["observed_states"][0]["unknown_source_date_records"] == 1
    assert not empty["sources"] and not empty["has_more"]


def test_route_requires_authentication_even_in_demo_mode(client):
    assert client.get("/v1/ingestion/coverage/measured").status_code == 401


def test_authenticated_route_returns_only_the_callers_sources(client, db):
    body = client.post("/auth/register", json={"email": "coverage@example.com", "password": "CorrectHorseBattery42",
                                              "full_name": "Coverage", "organization_name": "Coverage"}).json()
    seed(db, body["organization_id"], "mine", now=datetime.now(timezone.utc))
    seed(db, "another-org", "not-mine", now=datetime.now(timezone.utc))
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    response = client.get("/v1/ingestion/coverage/measured", headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert [s["source_key"] for s in response.json()["sources"]] == ["mine"]
    assert client.get("/v1/ingestion/coverage/measured?record_type=other", headers=headers).status_code == 422
