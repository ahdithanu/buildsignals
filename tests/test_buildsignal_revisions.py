import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.buildsignal import BuildSignalRevision
from app.models.graph import GraphRelationshipEvidence
from app.schemas.buildsignal import BuildSignalAssessmentDraft, BuildSignalReviewCreate
from app.services.buildsignal_assessment import get_revision, review_revision, save_revision
from tests.test_buildsignal_assessment import setup_draft


def test_revision_freezes_evidence_and_records_audit(db):
    draft = BuildSignalAssessmentDraft(**setup_draft(db))
    first = save_revision(db, "signal", draft, "author")
    db.get(GraphRelationshipEvidence, "evidence").excerpt = "Updated public record"
    db.commit()
    second = save_revision(db, "signal", draft, "author")
    assert first.id != second.id
    assert first.snapshot["citations"][0]["excerpt"] == "Rezoning application submitted"
    assert second.snapshot["citations"][0]["excerpt"] == "Updated public record"
    assert db.query(AuditLog).filter_by(entity_type="buildsignal_revision").count() == 2


def test_review_requires_independent_reviewer_and_keeps_draft(db):
    revision = save_revision(db, "signal", BuildSignalAssessmentDraft(**setup_draft(db)), "author")
    review = BuildSignalReviewCreate(decision="approved", rationale="Reviewed assumptions and counterevidence")
    with pytest.raises(HTTPException) as exc:
        review_revision(db, revision.id, review, "author")
    assert exc.value.status_code == 409
    result = review_revision(db, revision.id, review, "reviewer")
    assert result.revision_id == revision.id
    assert result.decision == "approved"
    assert revision.snapshot["status"] == "draft"


def test_cross_tenant_revision_is_hidden(db):
    revision = save_revision(db, "signal", BuildSignalAssessmentDraft(**setup_draft(db)), "author")
    db.get(BuildSignalRevision, revision.id).organization_id = "other-org"
    db.commit()
    with pytest.raises(HTTPException) as exc:
        get_revision(db, revision.id)
    assert exc.value.status_code == 404


def test_persistence_requires_authentication(client):
    assert client.get("/signals/unknown/assessment-revisions").status_code == 401
    assert client.post("/assessment-revisions/unknown/reviews", json={
        "decision": "approved", "rationale": "reviewed",
    }).status_code == 401
