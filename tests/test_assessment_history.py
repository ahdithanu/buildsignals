from datetime import datetime, timezone

import pytest

from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.routes import auth
from app.schemas.buildsignal import BuildSignalAssessmentDraft
from app.services.buildsignal_assessment import save_revision
from app.services.rate_limiter import InMemoryRateLimiter
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_buildsignal_assessment import setup_draft


@pytest.fixture()
def history_workspace(client, db, monkeypatch):
    monkeypatch.setattr(auth, "limiter", InMemoryRateLimiter())
    response = client.post("/v1/auth/register", json={
        "email": "history@example.com", "password": "SyntheticValidation42!", "full_name": "History Analyst",
    })
    assert response.status_code == 201, response.text
    identity = response.json()
    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    context = set_current_context(RequestContext(org_id=identity["organization_id"], user_id=identity["user_id"]))
    try:
        payload = setup_draft(db)
        rows = [save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), identity["user_id"]) for _ in range(3)]
        same_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for row in rows:
            row.created_at = same_time
        selected = rows[0]
        for index in range(3):
            db.add(BuildSignalReview(id=f"review-{index}", revision_id=selected.id,
                                     organization_id=identity["organization_id"], reviewer_id=identity["user_id"],
                                     decision="changes_requested", rationale=f"Historical fixture {index}", created_at=same_time))
            db.add(BuildSignalPublication(id=f"publication-{index}", revision_id=selected.id,
                                         organization_id=identity["organization_id"], actor_id=identity["user_id"],
                                         action="published" if index % 2 == 0 else "withdrawn", version=index + 1,
                                         rationale="Synthetic pagination fixture", created_at=same_time))
        db.commit()
        return headers, selected.id, sorted([row.id for row in rows], reverse=True), payload
    finally:
        reset_current_context(context)


@pytest.mark.parametrize("history", ["revisions", "reviews", "publication"])
def test_history_pages_are_bounded_and_stably_ordered(client, history_workspace, history):
    headers, revision_id, revision_ids, _ = history_workspace
    path = "/v1/signals/signal/assessment-revisions" if history == "revisions" else f"/v1/assessment-revisions/{revision_id}/{history}"
    expected = revision_ids if history == "revisions" else [f"{'review' if history == 'reviews' else 'publication'}-{i}" for i in (2, 1, 0)]
    first = client.get(path, params={"limit": 2, "skip": 0}, headers=headers)
    second = client.get(path, params={"limit": 2, "skip": 2}, headers=headers)
    assert first.status_code == second.status_code == 200
    assert [row["id"] for row in first.json()] == expected[:2]
    assert [row["id"] for row in second.json()] == expected[2:]
    assert client.get(path, params={"limit": 2, "skip": 4}, headers=headers).json() == []
    for params in ({"limit": 101}, {"limit": 0}, {"skip": -1}):
        assert client.get(path, params=params, headers=headers).status_code == 422
    assert client.get(path).status_code == 401


def test_multi_entity_event_date_and_source_snapshot_are_preserved(client, db, history_workspace):
    headers, _, _, payload = history_workspace
    payload["event_at"] = "2026-08-01T14:30:00-04:00"
    payload["implications"].append({
        "entity_id": "city", "mechanism": "Potential infrastructure demand", "direction": "mixed",
        "horizon": "Unknown", "evidence_ids": ["evidence"],
    })
    created = client.post("/v1/signals/signal/assessment-revisions", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    snapshot = created.json()["snapshot"]
    assert datetime.fromisoformat(snapshot["event_at"]) == datetime(2026, 8, 1, 18, 30, tzinfo=timezone.utc)
    assert [row["entity_name"] for row in snapshot["implications"]] == ["Parcel A", "City A"]
    assert snapshot["citations"][0]["excerpt"] == "Rezoning application submitted"
    assert not any("Event date is unknown" in flag for flag in snapshot["review_flags"])
    db.expire_all()
    assert db.get(BuildSignalRevision, created.json()["id"]).snapshot == snapshot


@pytest.mark.parametrize("history", ["revisions", "reviews", "publication"])
def test_history_cross_tenant_ids_are_not_disclosed(client, history_workspace, history):
    _, revision_id, _, _ = history_workspace
    other = client.post("/v1/auth/register", json={
        "email": "other-history@example.com", "password": "SyntheticValidation42!", "full_name": "Other Analyst",
    })
    assert other.status_code == 201
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    path = "/v1/signals/signal/assessment-revisions" if history == "revisions" else f"/v1/assessment-revisions/{revision_id}/{history}"
    assert client.get(path, params={"limit": 1, "skip": 1}, headers=headers).status_code == 404
