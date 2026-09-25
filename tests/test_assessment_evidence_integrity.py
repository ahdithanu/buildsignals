"""Authoring source preconditions and generic graph incidence, without provider logic."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, event, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.buildsignal import BuildSignalRevision
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.organization import Organization
from app.models.signal import Signal
from app.models.user import User
from app.schemas.buildsignal import BuildSignalAssessmentDraft
from app.services.buildsignal_assessment import assessment_source_version, save_revision
from app.utils.org_scope import (
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)
from tests.test_buildsignal_assessment import setup_draft


def graph_version(relationship, evidence):
    """Construct the browser contract from the existing graph HTTP representation."""
    content = [evidence.get(key) for key in (
        "source_system", "source_id", "source_url", "evidence_type", "excerpt",
    )]
    return {
        "evidence_id": evidence["id"], "relationship_id": relationship["id"],
        "content_sha256": hashlib.sha256(json.dumps(
            content, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
        "observed_at": evidence["observed_at"], "created_at": evidence["created_at"],
        "confidence": evidence["confidence"],
        "source_entity_id": relationship["source_entity_id"],
        "target_entity_id": relationship["target_entity_id"],
        "relationship_updated_at": relationship["updated_at"],
        "relationship_last_verified_at": relationship["last_verified_at"],
        "relationship_is_current": relationship["is_current"],
    }


def protected_draft(client, db, headers=None):
    payload = setup_draft(db)
    response = client.get("/v1/graph/entities/parcel", headers=headers)
    assert response.status_code == 200, response.text
    relationship = response.json()["related"][0]["relationship"]
    payload["source_precondition"] = {
        "schema_version": "1", "evidence": [graph_version(relationship, relationship["evidence"][0])],
    }
    return payload


def assert_rejected_without_write(db, payload, status):
    with pytest.raises(HTTPException) as exc:
        save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), "author")
    assert exc.value.status_code == status, exc.value.detail
    assert db.query(BuildSignalRevision).count() == 0
    assert db.query(AuditLog).filter_by(entity_type="buildsignal_revision").count() == 0
    return exc.value


def test_two_entities_share_one_relationship_and_one_source_version(client, db):
    payload = protected_draft(client, db)
    payload["implications"].append({**payload["implications"][0], "entity_id": "city"})
    row = save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), "author")
    assert [item["entity_id"] for item in row.snapshot["implications"]] == ["parcel", "city"]
    assert len(row.snapshot["source_precondition"]["evidence"]) == 1
    assert not any("precondition omitted" in flag for flag in row.snapshot["review_flags"])


@pytest.mark.parametrize("protected", [True, False])
def test_unrelated_entity_cannot_borrow_evidence_even_for_legacy_callers(client, db, protected):
    payload = protected_draft(client, db)
    db.add(GraphEntity(id="unrelated", organization_id=get_org_id(), entity_type="company",
                       display_name="Unrelated company", normalized_name="unrelated company"))
    db.commit()
    payload["implications"][0]["entity_id"] = "unrelated"
    if not protected:
        payload.pop("source_precondition")
    assert_rejected_without_write(db, payload, 422)


def test_every_implication_source_must_involve_the_entity(client, db):
    payload = protected_draft(client, db)
    payload.pop("source_precondition")
    db.add(GraphEntity(id="company", organization_id=get_org_id(), entity_type="company",
                       display_name="Company", normalized_name="company"))
    db.flush()
    db.add(GraphRelationship(id="unrelated-rel", organization_id=get_org_id(),
                             source_entity_id="company", target_entity_id="city", relationship_type="related_to"))
    db.flush()
    db.add(GraphRelationshipEvidence(id="other-source", organization_id=get_org_id(),
                                     relationship_id="unrelated-rel", source_system="test"))
    db.commit()
    payload["citations"].append({**payload["citations"][0], "evidence_id": "other-source"})
    payload["implications"][0]["evidence_ids"].append("other-source")
    assert_rejected_without_write(db, payload, 422)


@pytest.mark.parametrize(("model", "field", "value"), [
    (GraphRelationshipEvidence, "excerpt", "Application withdrawn"),
    (GraphRelationshipEvidence, "source_system", "corrected source"),
    (GraphRelationshipEvidence, "source_id", "new-source-id"),
    (GraphRelationshipEvidence, "source_url", "https://example.com/correction"),
    (GraphRelationshipEvidence, "evidence_type", "correction"),
    (GraphRelationshipEvidence, "observed_at", datetime(2026, 9, 10, tzinfo=timezone.utc)),
    (GraphRelationshipEvidence, "created_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    (GraphRelationshipEvidence, "confidence", 0.2),
    (GraphRelationship, "updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    (GraphRelationship, "last_verified_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    (GraphRelationship, "is_current", False),
    (GraphRelationship, "source_entity_id", "city"),
    (GraphRelationship, "target_entity_id", "parcel"),
])
def test_source_metadata_changed_after_graph_read_conflicts(client, db, model, field, value):
    payload = protected_draft(client, db)
    row_id = "evidence" if model is GraphRelationshipEvidence else "relationship"
    setattr(db.get(model, row_id), field, value)
    db.commit()
    exc = assert_rejected_without_write(db, payload, 409)
    assert exc.detail == "Source evidence changed. Refresh citations and review before saving again."


@pytest.mark.parametrize(("field", "value"), [
    ("content_sha256", "0" * 64), ("relationship_id", "invented"),
    ("confidence", 0.1), ("relationship_is_current", False),
    ("source_entity_id", "city"), ("target_entity_id", "parcel"),
])
def test_tampered_version_never_produces_a_revision(client, db, field, value):
    payload = protected_draft(client, db)
    payload["source_precondition"]["evidence"][0][field] = value
    assert_rejected_without_write(db, payload, 409)


@pytest.mark.parametrize("mutation", ["missing-field", "missing-entry", "extra-entry", "duplicate", "bad-hash", "bad-version", "unknown-field"])
def test_malformed_or_incomplete_preconditions_fail_validation(client, db, mutation):
    payload = protected_draft(client, db)
    precondition = payload["source_precondition"]
    version = precondition["evidence"][0]
    if mutation == "missing-field":
        version.pop("content_sha256")
    elif mutation == "missing-entry":
        payload["citations"].append({**payload["citations"][0], "evidence_id": "second-source"})
    elif mutation == "extra-entry":
        precondition["evidence"].append({**version, "evidence_id": "not-cited"})
    elif mutation == "duplicate":
        precondition["evidence"].append(dict(version))
    elif mutation == "bad-hash":
        version["content_sha256"] = "not-a-sha256"
    elif mutation == "bad-version":
        precondition["schema_version"] = "2"
    else:
        version["ignore_conflict"] = True
    with pytest.raises(ValidationError):
        BuildSignalAssessmentDraft(**payload)
    response = client.post("/signals/signal/assessment-preview", json=payload)
    assert response.status_code == 422, response.text
    assert db.query(BuildSignalRevision).count() == 0


def test_precondition_list_is_bounded_and_allows_two_claims_for_one_evidence(client, db):
    payload = protected_draft(client, db)
    payload["citations"].append({**payload["citations"][0], "claim": "thesis"})
    BuildSignalAssessmentDraft(**payload)
    payload["source_precondition"]["evidence"] *= 101
    with pytest.raises(ValidationError):
        BuildSignalAssessmentDraft(**payload)


@pytest.mark.parametrize(("model", "row_id"), [
    (Signal, "signal"), (GraphEntity, "parcel"), (GraphRelationship, "relationship"),
    (GraphRelationshipEvidence, "evidence"),
])
def test_reference_scope_is_checked_before_version_conflicts(client, db, model, row_id):
    payload = protected_draft(client, db)
    db.get(model, row_id).organization_id = "other-org"
    db.commit()
    payload["source_precondition"]["evidence"][0]["content_sha256"] = "0" * 64
    exc = assert_rejected_without_write(db, payload, 404)
    assert exc.detail in {"Signal not found", "Assessment reference not found"}


def test_deleted_source_is_not_hidden_by_a_precondition(client, db):
    payload = protected_draft(client, db)
    db.delete(db.get(GraphRelationshipEvidence, "evidence"))
    db.commit()
    assert_rejected_without_write(db, payload, 404)


def test_reused_session_does_not_compare_a_stale_identity_map(client, db):
    payload = protected_draft(client, db)
    cached = db.get(GraphRelationshipEvidence, "evidence")
    with Session(db.get_bind()) as writer:
        writer.execute(update(GraphRelationshipEvidence).where(
            GraphRelationshipEvidence.id == "evidence",
        ).values(excerpt="Concurrent corrected source"))
        writer.commit()
    assert cached.excerpt == "Rezoning application submitted"
    assert_rejected_without_write(db, payload, 409)
    assert cached.excerpt == "Concurrent corrected source"


def test_save_requests_row_locks_in_stable_order(client, db):
    payload = protected_draft(client, db)
    statements = []

    def capture(state):
        if state.is_select:
            statements.append(str(state.statement.compile(dialect=postgresql.dialect())))

    event.listen(db, "do_orm_execute", capture)
    try:
        save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), "author")
    finally:
        event.remove(db, "do_orm_execute", capture)
    locked = [statement for statement in statements if "FOR UPDATE" in statement]
    assert len(locked) == 3
    for statement, table in zip(locked, ["graph_entities", "graph_relationships", "graph_relationship_evidence"]):
        assert f"FROM {table}" in statement
        assert f"ORDER BY {table}.id" in statement
        assert f"{table}.organization_id" in statement


@pytest.mark.parametrize("explicit_null", [True, False])
def test_legacy_clients_remain_compatible_but_snapshot_records_the_missing_check(client, db, explicit_null):
    payload = protected_draft(client, db)
    payload.pop("source_precondition")
    if explicit_null:
        payload["source_precondition"] = None
    db.get(GraphRelationshipEvidence, "evidence").excerpt = "Changed since authoring"
    db.commit()
    row = save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), "author")
    assert row.snapshot["citations"][0]["excerpt"] == "Changed since authoring"
    assert any("precondition omitted" in flag for flag in row.snapshot["review_flags"])


def test_version_dates_preserve_microseconds_and_accept_equivalent_timezones(client, db):
    payload = protected_draft(client, db)
    timestamp = datetime(2026, 9, 10, 12, 30, 0, 123456, tzinfo=timezone.utc)
    source = db.get(GraphRelationshipEvidence, "evidence")
    source.observed_at = timestamp
    db.commit()
    version = assessment_source_version(source, db.get(GraphRelationship, "relationship")).model_dump(mode="json")
    version["observed_at"] = timestamp.astimezone(timezone(timedelta(hours=-7))).isoformat()
    payload["source_precondition"]["evidence"] = [version]
    save_revision(db, "signal", BuildSignalAssessmentDraft(**payload), "author")


def test_authenticated_save_accepts_graph_versions_then_rejects_a_stale_retry(client, db, monkeypatch):
    from app.routes import auth
    from app.services.rate_limiter import InMemoryRateLimiter

    monkeypatch.setattr(auth, "limiter", InMemoryRateLimiter())
    registration = client.post("/v1/auth/register", json={
        "email": "evidence-integrity@example.com", "password": "LocalIntegrityTest42!",
        "full_name": "Local Integrity Analyst",
        "organization_name": "Local integrity fixture",
    })
    assert registration.status_code == 201, registration.text
    identity = registration.json()
    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    token = set_current_context(RequestContext(org_id=identity["organization_id"], user_id="author"))
    try:
        payload = protected_draft(client, db, headers)
    finally:
        reset_current_context(token)
    saved = client.post("/v1/signals/signal/assessment-revisions", headers=headers, json=payload)
    assert saved.status_code == 201, saved.text
    assert saved.json()["snapshot"]["source_precondition"]["schema_version"] == "1"
    db.get(GraphRelationshipEvidence, "evidence").excerpt = "Changed after graph GET"
    db.commit()
    conflicted = client.post("/v1/signals/signal/assessment-revisions", headers=headers, json=payload)
    assert conflicted.status_code == 409, conflicted.text
    assert db.query(BuildSignalRevision).count() == 1


def test_null_and_empty_source_values_produce_distinct_content_versions(client, db):
    protected_draft(client, db)
    source = db.get(GraphRelationshipEvidence, "evidence")
    relationship = db.get(GraphRelationship, "relationship")
    first = assessment_source_version(source, relationship)
    source.source_url = ""
    second = assessment_source_version(source, relationship)
    assert first.content_sha256 != second.content_sha256
    source.excerpt = "R\u00e9sum\u00e9 \u2028quoted \"source\"\n"
    version = assessment_source_version(source, relationship)
    # Node WebCrypto/JSON.stringify produces this same UTF-8 digest, including U+2028.
    assert version.content_sha256 == "12d97d76f1bd8aa121d330c06ed0cf99d3034c52ff3855272d105404c7c4309d"


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required for real row locks")
@pytest.mark.parametrize("target", ["evidence", "relationship"])
def test_postgres_blocks_source_changes_until_revision_commits(target):
    """Use the existing migrated CI database; isolate and remove all synthetic rows."""
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    org_id, author_id, signal_id, first_id, second_id, rel_id, source_id = [str(uuid4()) for _ in range(7)]
    token = set_current_context(RequestContext(org_id=org_id, user_id=author_id))

    def session():
        db = Session(engine)

        def configure(_session, _transaction, connection):
            connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id})
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))

        event.listen(db, "after_begin", configure)
        return db

    model = GraphRelationshipEvidence if target == "evidence" else GraphRelationship
    row_id = source_id if target == "evidence" else rel_id
    changes = {"excerpt": "Concurrent source update"} if target == "evidence" else {"is_current": False}

    def attempt_update():
        with session() as writer:
            writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
            writer.execute(update(model).where(model.id == row_id, model.organization_id == org_id).values(**changes))
            writer.commit()

    try:
        with session() as db:
            db.add(Organization(id=org_id, name="Synthetic evidence lock test", slug=org_id))
            db.add(User(id=author_id, email=f"{author_id}@example.com", full_name="Synthetic analyst", password_hash="not-a-login-hash"))
            db.commit()
            db.add(Signal(id=signal_id, organization_id=org_id, signal_type="test"))
            db.add_all([GraphEntity(id=value, organization_id=org_id, entity_type="company",
                                    display_name="Synthetic company", normalized_name="synthetic company")
                        for value in (first_id, second_id)])
            db.flush()
            relationship = GraphRelationship(id=rel_id, organization_id=org_id, source_entity_id=first_id,
                                             target_entity_id=second_id, relationship_type="related_to")
            db.add(relationship)
            db.flush()
            evidence = GraphRelationshipEvidence(id=source_id, organization_id=org_id,
                                                 relationship_id=rel_id, source_system="synthetic", excerpt="Original")
            db.add(evidence)
            db.commit()
            draft = BuildSignalAssessmentDraft(
                detected_change="Synthetic change", investment_thesis="Synthetic hypothesis",
                change_confidence={"level": "unassessed", "rationale": "Test only"},
                thesis_confidence={"level": "unassessed", "rationale": "Test only"},
                citations=[{"evidence_id": source_id, "claim": "change", "stance": "supports", "rationale": "Test"}],
                implications=[{"entity_id": first_id, "mechanism": "Test", "horizon": "Unknown", "direction": "uncertain", "evidence_ids": [source_id]}],
                further_investigation=["Synthetic verification"],
                source_precondition={"schema_version": "1", "evidence": [assessment_source_version(evidence, relationship)]},
            )
            blocked = []

            def before_revision_flush(active, _context, _instances):
                if not any(isinstance(row, BuildSignalRevision) for row in active.new):
                    return
                with pytest.raises(DBAPIError) as exc:
                    attempt_update()
                assert exc.value.orig.pgcode == "55P03"
                blocked.append(True)

            event.listen(db, "before_flush", before_revision_flush)
            try:
                revision = save_revision(db, signal_id, draft, author_id)
            finally:
                event.remove(db, "before_flush", before_revision_flush)
            assert blocked == [True]
            assert revision.snapshot["citations"][0]["excerpt"] == "Original"
            attempt_update()
            assert revision.snapshot["citations"][0]["relationship_is_current"] is True
    finally:
        with session() as cleanup:
            cleanup.execute(delete(Organization).where(Organization.id == org_id))
            cleanup.execute(delete(User).where(User.id == author_id))
            cleanup.commit()
        reset_current_context(token)
        engine.dispose()
