import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.buildsignal import BuildSignalRevision
from app.schemas.buildsignal import (
    BuildSignalAssessmentDraft,
    BuildSignalReviewCreate,
    PublicationCreate,
)
from app.services.assessment_publication import change_publication, publication_history
from app.services.buildsignal_assessment import review_revision, save_revision
from tests.test_buildsignal_assessment import setup_draft


def setup_revision(db, approved=True):
    revision = save_revision(db, "signal", BuildSignalAssessmentDraft(**setup_draft(db)), "author")
    if approved:
        review_revision(db, revision.id, BuildSignalReviewCreate(decision="approved", rationale="Evidence reviewed"), "reviewer")
    return revision


def transition(db, revision_id, version=0, action="published"):
    return change_publication(db, revision_id, PublicationCreate(
        action=action, expected_version=version, rationale="Release decision",
    ), "admin")


def test_release_withdraw_and_republish_preserve_history(db):
    revision = setup_revision(db)
    first = transition(db, revision.id)
    assert first.review_id
    assert first.version == 1
    transition(db, revision.id, 1, "withdrawn")
    transition(db, revision.id, 2)
    assert [row.action for row in publication_history(db, revision.id)] == ["published", "withdrawn", "published"]
    assert revision.snapshot["status"] == "draft"
    assert db.query(AuditLog).filter_by(entity_type="buildsignal_publication").count() == 3


def test_publication_requires_approval(db):
    revision = setup_revision(db, approved=False)
    with pytest.raises(HTTPException) as exc:
        transition(db, revision.id)
    assert exc.value.status_code == 409
    assert not publication_history(db, revision.id)


def test_latest_rejection_invalidates_old_approval(db):
    revision = setup_revision(db)
    review_revision(db, revision.id, BuildSignalReviewCreate(decision="rejected", rationale="New contrary evidence"), "reviewer")
    with pytest.raises(HTTPException) as exc:
        transition(db, revision.id)
    assert "independent approval" in exc.value.detail


def test_stale_write_and_published_review_are_blocked(db):
    revision = setup_revision(db)
    transition(db, revision.id)
    with pytest.raises(HTTPException) as exc:
        transition(db, revision.id, 0, "withdrawn")
    assert "refresh" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        review_revision(db, revision.id, BuildSignalReviewCreate(decision="rejected", rationale="Reassess"), "reviewer")
    assert "Withdraw" in exc.value.detail
    assert len(publication_history(db, revision.id)) == 1


def test_cannot_withdraw_unpublished_revision(db):
    revision = setup_revision(db)
    with pytest.raises(HTTPException) as exc:
        transition(db, revision.id, action="withdrawn")
    assert exc.value.status_code == 409


def test_publication_is_tenant_scoped(db):
    revision = setup_revision(db)
    db.get(BuildSignalRevision, revision.id).organization_id = "other-org"
    db.commit()
    with pytest.raises(HTTPException) as exc:
        publication_history(db, revision.id)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        transition(db, revision.id)
    assert exc.value.status_code == 404


def test_publication_requires_authentication(client):
    assert client.get("/assessment-revisions/unknown/publication").status_code == 401
    assert client.post("/assessment-revisions/unknown/publication", json={
        "action": "published", "expected_version": 0, "rationale": "Release",
    }).status_code == 401


def test_authenticated_author_review_publish_withdraw_workflow(client, db, monkeypatch):
    from app.models.organization_membership import MemberRole, OrganizationMembership
    from app.routes import auth
    from app.services.rate_limiter import InMemoryRateLimiter
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

    monkeypatch.setattr(auth, "limiter", InMemoryRateLimiter())

    def register(email):
        result = client.post("/v1/auth/register", json={
            "email": email, "password": "LongDemoTestPassword42", "full_name": "Test Analyst",
            "organization_name": email,
        })
        assert result.status_code == 201, result.text
        headers = {"Authorization": f"Bearer {result.json()['access_token']}"}
        me = client.get("/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        return headers, me.json()

    author, identity = register("author-publication@example.com")
    _, reviewer_identity = register("reviewer-publication@example.com")
    membership = db.query(OrganizationMembership).filter_by(user_id=reviewer_identity["user"]["id"]).one()
    membership.organization_id = identity["organization_id"]
    db.commit()
    login = client.post("/v1/auth/login", json={"email": "reviewer-publication@example.com", "password": "LongDemoTestPassword42"})
    assert login.status_code == 200, login.text
    reviewer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    token = set_current_context(RequestContext(org_id=identity["organization_id"], user_id=identity["user"]["id"]))
    try:
        payload = setup_draft(db)
    finally:
        reset_current_context(token)
    saved = client.post("/v1/signals/signal/assessment-revisions", headers=author, json=payload)
    assert saved.status_code == 201, saved.text
    revision_id = saved.json()["id"]
    review_path = f"/v1/assessment-revisions/{revision_id}/reviews"
    publication_path = f"/v1/assessment-revisions/{revision_id}/publication"
    decision = {"decision": "approved", "rationale": "Independent source review"}
    assert client.post(review_path, headers=author, json=decision).status_code == 409
    assert client.post(review_path, headers=reviewer, json=decision).status_code == 201
    release = client.post(publication_path, headers=reviewer, json={"action": "published", "expected_version": 0, "rationale": "Ready"})
    assert release.status_code == 201, release.text
    membership.role = MemberRole.viewer
    db.commit()
    assert client.post(publication_path, headers=reviewer, json={"action": "withdrawn", "expected_version": 1, "rationale": "Correction"}).status_code == 403
    assert client.get(publication_path, headers=reviewer).status_code == 200
    assert client.post(publication_path, headers=author, json={"action": "withdrawn", "expected_version": 1, "rationale": "Correction"}).status_code == 201
