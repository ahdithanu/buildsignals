"""Bounded graph/assessment exports, using only isolated synthetic databases."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.browser_session import BrowserSession
from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.document import Document
from app.models.graph import (
    GraphEntity,
    GraphEntityAlias,
    GraphEntityLink,
    GraphEntityMerge,
    GraphEntitySourceIdentity,
    GraphRelationship,
    GraphRelationshipEvidence,
)
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.organization_membership import OrganizationMembership
from app.models.parcel import ParcelRecord
from app.models.password_reset_token import PasswordResetToken
from app.models.planning import PlanningRecord
from app.models.signal import Signal
from app.routes import data_portability as routes
from app.schemas.buildsignal import BuildSignalAssessmentResponse
from app.services.buildsignal_assessment import assessment_source_version
from app.services.organization_export import EXPORT_TABLES, serialize
from tests.test_data_export_bounds import _assert_no_download, _deal, _export, _identity


def _graph_assessment(db, org, user):
    deal = _deal(db, org)
    common = {"organization_id": org.id}
    first = GraphEntity(id=str(uuid4()), **common, entity_type="property",
                        display_name=f"Property {org.name}", normalized_name="property",
                        attributes={"credential": "EXCLUDED-ENTITY-ATTRIBUTES"})
    second = GraphEntity(id=str(uuid4()), **common, entity_type="city",
                         display_name=f"City {org.name}", normalized_name="city")
    signal = Signal(id=str(uuid4()), **common, deal_id=deal.id, signal_type="planning")
    db.add_all([first, second, signal])
    db.flush()
    relationship = GraphRelationship(
        id=str(uuid4()), **common, source_entity_id=first.id, target_entity_id=second.id,
        relationship_type="related_to", is_current=False,
        valid_to=datetime.now(timezone.utc), attributes={"raw": "EXCLUDED-RELATIONSHIP-ATTRIBUTES"},
    )
    db.add(relationship)
    db.flush()
    evidence = GraphRelationshipEvidence(
        id=str(uuid4()), **common, relationship_id=relationship.id,
        source_system="public-register", source_id="external-42",
        source_url="https://example.com/filing", evidence_type="planning",
        excerpt=f"Original filing for {org.name}", payload={"raw": "EXCLUDED-EVIDENCE-PAYLOAD"},
    )
    db.add(evidence)
    db.flush()
    snapshot = {
        "schema_version": "1", "signal_id": signal.id, "status": "draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "detected_change": "An application was filed", "event_at": None,
        "investment_thesis": "A saved analyst hypothesis",
        "change_confidence": {"level": "high", "rationale": "Official source"},
        "thesis_confidence": {"level": "low", "rationale": "Requires investigation"},
        "citations": [{
            "evidence_id": evidence.id, "stance": "supports", "claim": "change",
            "rationale": "Recorded application", "source_system": evidence.source_system,
            "source_id": evidence.source_id, "source_url": evidence.source_url,
            "excerpt": evidence.excerpt, "observed_at": None,
            "relationship_id": relationship.id, "relationship_is_current": False,
            "relationship_last_verified_at": relationship.last_verified_at.isoformat(),
        }],
        "implications": [{
            "entity_id": first.id, "entity_name": first.display_name, "entity_type": "property",
            "mechanism": "Possible zoning change", "direction": "uncertain", "horizon": "Two years",
            "evidence_ids": [evidence.id],
        }],
        "further_investigation": ["Check the next hearing"], "review_flags": ["Historical relationship"],
        "source_precondition": {"schema_version": "1", "evidence": [
            assessment_source_version(evidence, relationship).model_dump(mode="json"),
        ]},
    }
    BuildSignalAssessmentResponse.model_validate(snapshot)
    revision = BuildSignalRevision(id=str(uuid4()), **common, signal_id=signal.id,
                                   author_id=user.id, snapshot=snapshot)
    alias = GraphEntityAlias(id=str(uuid4()), **common, entity_id=first.id,
                             alias="Property alias", normalized_alias="property alias")
    identity = GraphEntitySourceIdentity(id=str(uuid4()), **common, entity_id=first.id,
                                         source_system="registry", source_id="external-identity")
    link = GraphEntityLink(id=str(uuid4()), **common, entity_id=first.id,
                           record_type="deal", record_id=deal.id)
    merge = GraphEntityMerge(id=str(uuid4()), **common, survivor_entity_id=first.id,
                             merged_entity_id=str(uuid4()), entity_type="property",
                             merged_display_name="Retired name", reason="Verified duplicate",
                             snapshot={"raw": "EXCLUDED-MERGE-SNAPSHOT"})
    db.add_all([revision, alias, identity, link, merge])
    db.flush()
    review = BuildSignalReview(id=str(uuid4()), **common, revision_id=revision.id,
                               reviewer_id=None, decision="approved", rationale="Historic review")
    db.add(review)
    db.flush()
    publication = BuildSignalPublication(id=str(uuid4()), **common, revision_id=revision.id,
                                         review_id=review.id, actor_id=user.id, version=1,
                                         action="published", rationale="Approved for internal use")
    db.add(publication)
    db.commit()
    return dict(deal=deal, first=first, second=second, signal=signal, relationship=relationship,
                evidence=evidence, revision=revision, review=review, publication=publication,
                alias=alias, identity=identity, link=link, merge=merge)


def _no_receipt(db, org):
    assert db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").count() == 0


def test_graph_assessment_history_and_manifest_exclude_foreign_rows(client, db):
    org, user, headers = _identity(db, "graph-own")
    foreign, other, _ = _identity(db, "graph-foreign")
    own = _graph_assessment(db, org, user)
    theirs = _graph_assessment(db, foreign, other)
    frozen = copy.deepcopy(own["revision"].snapshot)
    own["evidence"].excerpt = "A later corrected filing"
    db.commit()

    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    for row in own.values():
        assert row.id in {item["id"] for item in body[row.__tablename__]}
    for row in theirs.values():
        assert row.id not in response.text
    assert foreign.id not in response.text
    assert other.email not in response.text
    assert body["buildsignal_revisions"][0]["snapshot"] == frozen
    assert body["graph_relationship_evidence"][0]["excerpt"] == "A later corrected filing"
    assert body["graph_relationships"][0]["is_current"] is False
    assert body["graph_relationships"][0]["valid_to"] is not None
    assert body["buildsignal_reviews"][0]["reviewer_id"] is None
    assert body["buildsignal_publications"][0]["review_id"] == own["review"].id

    manifest = body["manifest"]
    assert manifest["schema_version"] == "2"
    assert manifest["scope"] == "bounded_organization_data"
    assert manifest["complete_account_export"] is False
    assert manifest["assessment_snapshot_schema"] == "1"
    assert manifest["limits"] == {"total_database_rows": 10_000, "encoded_json_bytes": 20 * 1024 * 1024,
                                  "overflow": "all_or_nothing"}
    assert set(manifest["tables"]) == {"organization", "members", *(item.name for item in EXPORT_TABLES)}
    for entry in EXPORT_TABLES:
        assert manifest["tables"][entry.name]["row_count"] == len(body[entry.name])
        assert manifest["tables"][entry.name]["columns"] == list(entry.columns)
        for row in body[entry.name]:
            assert set(row) == set(entry.columns)
    expected_rows = 3 + sum(len(body[entry.name]) for entry in EXPORT_TABLES)
    assert manifest["row_count"] == expected_rows
    assert sum(table["row_count"] for table in manifest["tables"].values()) == expected_rows
    receipt = db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").one()
    metadata = json.loads(receipt.new_values)
    assert metadata["row_count"] == expected_rows
    assert metadata["byte_count"] == len(response.content)
    assert metadata["schema_version"] == "2"
    assert metadata["scopes"] == manifest["scopes"]
    assert receipt.id not in response.text


@pytest.mark.parametrize(("row_name", "field", "target"), [
    ("alias", "entity_id", "first"), ("identity", "entity_id", "first"),
    ("link", "entity_id", "first"), ("link", "record_id", "deal"),
    ("relationship", "source_entity_id", "first"), ("relationship", "target_entity_id", "second"),
    ("evidence", "relationship_id", "relationship"), ("merge", "survivor_entity_id", "first"),
    ("merge", "merged_entity_id", "first"), ("revision", "signal_id", "signal"),
    ("review", "revision_id", "revision"), ("publication", "revision_id", "revision"),
    ("publication", "review_id", "review"), ("signal", "deal_id", "deal"),
])
def test_cross_tenant_graph_and_assessment_references_fail_closed(client, db, row_name, field, target):
    # The merged_entity_id case is SQLite defense in depth, not a claim that a
    # negative foreign-row query can see through PostgreSQL forced RLS.
    org, user, headers = _identity(db, "cross-own")
    foreign, other, _ = _identity(db, "cross-other")
    own = _graph_assessment(db, org, user)
    theirs = _graph_assessment(db, foreign, other)
    setattr(own[row_name], field, theirs[target].id)
    if row_name == "publication" and field == "revision_id":
        own["publication"].version = 2
    db.commit()
    response = _export(client, org, headers)
    _assert_no_download(response, 500)
    assert theirs[target].id not in response.text
    assert "Original filing" not in response.text
    _no_receipt(db, org)


@pytest.mark.parametrize("path,target", [
    (("signal_id",), "signal"),
    (("citations", 0, "evidence_id"), "evidence"),
    (("citations", 0, "relationship_id"), "relationship"),
    (("implications", 0, "entity_id"), "first"),
    (("implications", 0, "evidence_ids", 0), "evidence"),
    (("source_precondition", "evidence", 0, "evidence_id"), "evidence"),
    (("source_precondition", "evidence", 0, "relationship_id"), "relationship"),
    (("source_precondition", "evidence", 0, "source_entity_id"), "first"),
    (("source_precondition", "evidence", 0, "target_entity_id"), "second"),
])
def test_snapshot_embedded_foreign_references_never_leak(client, db, path, target):
    org, user, headers = _identity(db, "snapshot-own")
    foreign, other, _ = _identity(db, "snapshot-other")
    own = _graph_assessment(db, org, user)
    theirs = _graph_assessment(db, foreign, other)
    snapshot = copy.deepcopy(own["revision"].snapshot)
    node = snapshot
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = theirs[target].id
    own["revision"].snapshot = snapshot
    db.commit()
    response = _export(client, org, headers)
    _assert_no_download(response, 500)
    assert theirs[target].id not in response.text
    _no_receipt(db, org)


def test_publication_cannot_reference_a_different_local_revision_review(client, db):
    org, user, headers = _identity(db, "publication")
    rows = _graph_assessment(db, org, user)
    second = BuildSignalRevision(organization_id=org.id, signal_id=rows["signal"].id,
                                  snapshot=rows["revision"].snapshot)
    db.add(second)
    db.flush()
    rows["review"].revision_id = second.id
    db.commit()
    _assert_no_download(_export(client, org, headers), 500)
    _no_receipt(db, org)


@pytest.mark.parametrize("corruption", ["unknown-field", "unknown-citation-field", "bad-schema", "missing-reference"])
def test_invalid_snapshot_has_no_partial_download(client, db, corruption):
    org, user, headers = _identity(db, "malformed")
    rows = _graph_assessment(db, org, user)
    snapshot = copy.deepcopy(rows["revision"].snapshot)
    if corruption == "unknown-field":
        snapshot["credential"] = "SYNTHETIC-SNAPSHOT-SECRET"
    elif corruption == "unknown-citation-field":
        snapshot["citations"][0]["raw_payload"] = "SYNTHETIC-SNAPSHOT-SECRET"
    elif corruption == "bad-schema":
        snapshot["schema_version"] = "999"
    else:
        snapshot["citations"][0]["relationship_id"] = str(uuid4())
    rows["revision"].snapshot = snapshot
    db.commit()
    response = _export(client, org, headers)
    _assert_no_download(response, 500)
    assert "SYNTHETIC-SNAPSHOT-SECRET" not in response.text
    _no_receipt(db, org)


def test_legacy_snapshot_and_chained_merge_history_remain_exportable(client, db):
    org, user, headers = _identity(db, "legacy")
    rows = _graph_assessment(db, org, user)
    retired = str(uuid4())
    original = rows["merge"].merged_entity_id
    rows["merge"].survivor_entity_id = retired
    db.add(GraphEntityMerge(organization_id=org.id, survivor_entity_id=rows["first"].id,
                            merged_entity_id=retired, entity_type="property", merged_display_name="Later duplicate",
                            reason="Second merge", snapshot={}))
    snapshot = copy.deepcopy(rows["revision"].snapshot)
    snapshot.pop("source_precondition")
    snapshot["implications"][0]["entity_id"] = original
    rows["revision"].snapshot = snapshot
    db.commit()
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert response.json()["buildsignal_revisions"][0]["snapshot"] == snapshot
    assert len(response.json()["graph_entity_merges"]) == 2


def test_cyclic_merge_history_fails_without_hanging(client, db):
    org, user, headers = _identity(db, "cyclic")
    rows = _graph_assessment(db, org, user)
    rows["merge"].survivor_entity_id = rows["merge"].merged_entity_id
    db.commit()
    _assert_no_download(_export(client, org, headers), 500)
    _no_receipt(db, org)


def test_nonmember_actor_ids_and_unknown_link_targets_are_explicitly_redacted(client, db):
    org, user, headers = _identity(db, "redaction")
    _, outsider, _ = _identity(db, "former-member")
    rows = _graph_assessment(db, org, user)
    rows["revision"].author_id = outsider.id
    rows["review"].reviewer_id = outsider.id
    rows["publication"].actor_id = outsider.id
    rows["link"].record_type = "unregistered-record-kind"
    rows["link"].record_id = "UNKNOWN-PRIVATE-TARGET"
    db.commit()
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert outsider.id not in response.text
    assert outsider.email not in response.text
    assert "UNKNOWN-PRIVATE-TARGET" not in response.text
    body = response.json()
    assert body["buildsignal_revisions"][0]["author_id"] is None
    assert body["buildsignal_reviews"][0]["reviewer_id"] is None
    assert body["buildsignal_publications"][0]["actor_id"] is None
    assert body["graph_entity_links"][0]["record_id"] is None
    assert body["manifest"]["redactions"] == {
        "nonmember_user_references": 3, "unsupported_graph_link_targets": 1,
    }


@pytest.mark.parametrize("kind,model", [("permit", PermitRecord), ("parcel", ParcelRecord), ("planning", PlanningRecord)])
@pytest.mark.parametrize("foreign_target", [False, True])
def test_normalized_ingestion_links_verify_ownership_without_exporting_target_data(client, db, kind, model, foreign_target):
    org, user, headers = _identity(db, "link-own")
    foreign, _, _ = _identity(db, "link-foreign")
    rows = _graph_assessment(db, org, user)
    fields = dict(id=str(uuid4()), organization_id=foreign.id if foreign_target else org.id,
                  source_id=str(uuid4()), latest_raw_record_id=str(uuid4()), normalization_hash="synthetic")
    fields["external_parcel_id" if kind == "parcel" else "external_record_id"] = "EXCLUDED-NORMALIZED-RECORD"
    if kind == "planning":
        fields.update(event_type="application", title="Synthetic planning item", stage="proposed")
    target = model(**fields)
    db.add(target)
    rows["link"].record_type = kind
    rows["link"].record_id = target.id
    db.commit()
    loaded = []

    def on_load(session, obj):
        if isinstance(obj, model):
            loaded.append(obj.id)

    event.listen(Session, "loaded_as_persistent", on_load)
    try:
        response = _export(client, org, headers)
    finally:
        event.remove(Session, "loaded_as_persistent", on_load)
    assert loaded == []
    if foreign_target:
        _assert_no_download(response, 500)
        _no_receipt(db, org)
    else:
        assert response.status_code == 200, response.text
        assert response.json()["graph_entity_links"][0]["record_id"] == target.id
        assert model.__tablename__ not in response.json()
        assert "EXCLUDED-NORMALIZED-RECORD" not in response.text


def test_excluded_payloads_credentials_and_operational_tables_are_not_selected(client, db):
    org, user, headers = _identity(db, "exclusions")
    rows = _graph_assessment(db, org, user)
    user.totp_secret_ciphertext = "EXCLUDED-ENCRYPTED-MFA"
    source = IngestionSource(id=str(uuid4()), organization_id=org.id, key="synthetic",
                              name="EXCLUDED-SOURCE", adapter="csv", settings={"credential": "EXCLUDED-CONFIG"})
    run = IngestionRun(id=str(uuid4()), organization_id=org.id, source_id=source.id,
                        parameters={"credential": "EXCLUDED-RUN"})
    raw = RawSourceRecord(organization_id=org.id, source_id=source.id, run_id=run.id,
                           external_record_id="synthetic", content_hash="synthetic",
                           payload={"raw": "EXCLUDED-RAW-BLOB"})
    db.add_all([source, run, raw,
                BrowserSession(organization_id=org.id, user_id=user.id, browser_id="EXCLUDED-BROWSER",
                               expires_at=datetime.now(timezone.utc)),
                PasswordResetToken(user_id=user.id, token_hash="EXCLUDED-RESET-HASH",
                                   expires_at=datetime.now(timezone.utc)),
                Document(organization_id=org.id, deal_id=rows["deal"].id, filename="filing.pdf",
                         file_path="EXCLUDED-PRIVATE-STORAGE"),
                AuditLog(organization_id=org.id, entity_type="organization", entity_id=org.id,
                         action="update", old_values='{"token":"EXCLUDED-AUDIT-OLD"}',
                         new_values='{"credential":"EXCLUDED-AUDIT-NEW"}', request_id="EXCLUDED-REQUEST-ID")])
    db.commit()
    statements = []

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", record_select)
    try:
        response = _export(client, org, headers)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record_select)
    assert response.status_code == 200, response.text
    assert "EXCLUDED-" not in response.text
    assert "synthetic-password-hash" not in response.text
    body = response.json()
    for model in (IngestionSource, IngestionRun, RawSourceRecord, BrowserSession, PasswordResetToken):
        assert model.__tablename__ not in body
        assert not any(f"FROM {model.__tablename__}" in sql for sql in statements)
    excluded_columns = {
        "graph_entities": "attributes", "graph_relationships": "attributes",
        "graph_relationship_evidence": "payload", "graph_entity_merges": "snapshot",
        "audit_logs": "new_values", "documents": "file_path",
    }
    for table, column in excluded_columns.items():
        selects = [sql for sql in statements if f"FROM {table}" in sql]
        assert selects
        assert all(f"{table}.{column}" not in sql for sql in selects)
    assert body["audit_logs"][0]["action"] == "update"
    assert len(body["manifest"]["exclusions"]) >= 8
    assert any("merge history is trusted" in item for item in body["manifest"]["exclusions"])


def test_explicit_columns_do_not_export_future_model_fields():
    node = GraphEntity(id="synthetic", organization_id="tenant", entity_type="company",
                        display_name="Company", normalized_name="company")
    node.future_secret = "FUTURE-SECRET"
    result = serialize(node)
    assert "future_secret" not in result
    assert "FUTURE-SECRET" not in json.dumps(result)


def test_shared_row_cap_counts_graph_and_assessment_rows(client, db, monkeypatch):
    org, user, headers = _identity(db, "new-cap")
    _graph_assessment(db, org, user)
    expected = 3 + sum(db.query(entry.model).filter_by(organization_id=org.id).count() for entry in EXPORT_TABLES)
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", expected - 1)
    _assert_no_download(_export(client, org, headers), 413)
    _no_receipt(db, org)
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", expected)
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert response.json()["manifest"]["row_count"] == expected


def test_large_graph_dataset_uses_limit_and_shared_budget(client, db, monkeypatch):
    org, _, headers = _identity(db, "large-graph")
    db.execute(insert(GraphEntity), [dict(id=str(uuid4()), organization_id=org.id,
                                          entity_type="company", display_name="Private large graph",
                                          normalized_name=str(index)) for index in range(1_000)])
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 20)
    loaded = []
    selects = []

    def on_load(session, obj):
        if isinstance(obj, GraphEntity):
            loaded.append(obj.id)

    def on_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM graph_entities" in statement:
            selects.append(statement)

    event.listen(Session, "loaded_as_persistent", on_load)
    event.listen(db.get_bind(), "before_cursor_execute", on_select)
    try:
        response = _export(client, org, headers)
    finally:
        event.remove(Session, "loaded_as_persistent", on_load)
        event.remove(db.get_bind(), "before_cursor_execute", on_select)
    _assert_no_download(response, 413)
    assert len(loaded) <= 18
    assert selects and all("LIMIT" in sql for sql in selects)
    _no_receipt(db, org)


def test_foreign_graph_and_assessment_rows_do_not_consume_local_budget(client, db, monkeypatch):
    org, _, headers = _identity(db, "small-graph-tenant")
    foreign, other, _ = _identity(db, "large-graph-tenant")
    _graph_assessment(db, foreign, other)
    db.execute(insert(GraphEntity), [dict(id=str(uuid4()), organization_id=foreign.id,
                                          entity_type="company", display_name="FOREIGN-BULK-GRAPH",
                                          normalized_name=str(index)) for index in range(1_000)])
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_ROW_CAP", 3)
    response = _export(client, org, headers)
    assert response.status_code == 200, response.text
    assert response.json()["manifest"]["row_count"] == 3
    assert response.json()["graph_entities"] == []
    assert response.json()["buildsignal_revisions"] == []
    assert foreign.id not in response.text
    assert "FOREIGN-BULK-GRAPH" not in response.text


def test_exact_utf8_byte_limit_includes_new_manifest_and_snapshot(client, db, monkeypatch):
    org, user, headers = _identity(db, "exact-byte")
    rows = _graph_assessment(db, org, user)
    rows["evidence"].excerpt = "\u00e9\u6771\u4eac" * 100
    db.commit()
    first = _export(client, org, headers)
    assert first.status_code == 200, first.text
    expected = first.json()
    timestamp = datetime.fromisoformat(expected["exported_at"])
    monkeypatch.setattr(routes, "datetime", SimpleNamespace(now=lambda tz: timestamp))

    # The cap itself is in the manifest, so solve for its encoded digit length.
    cap = len(first.content)
    for _ in range(5):
        expected["manifest"]["limits"]["encoded_json_bytes"] = cap
        encoded_size = len(json.dumps(expected, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).encode("utf-8"))
        if encoded_size == cap:
            break
        cap = encoded_size
    assert encoded_size == cap
    assert len(json.dumps(expected, ensure_ascii=False, separators=(",", ":"))) < cap

    for limit, status in ((cap, 200), (cap - 1, 413)):
        db.query(AuditLog).filter_by(organization_id=org.id, action="data_export").delete()
        db.commit()
        monkeypatch.setattr(routes, "EXPORT_BYTE_CAP", limit)
        response = _export(client, org, headers)
        if status == 200:
            assert response.status_code == 200, response.text
            assert len(response.content) == cap
            assert response.json() == expected
        else:
            _assert_no_download(response, 413)
            _no_receipt(db, org)


@pytest.mark.parametrize("section", ["graph", "assessment"])
def test_new_text_and_snapshot_bytes_consume_the_same_budget(client, db, monkeypatch, section):
    org, user, headers = _identity(db, "new-bytes")
    rows = _graph_assessment(db, org, user)
    if section == "graph":
        rows["evidence"].excerpt = "PRIVATE-GRAPH-TEXT" * 10_000
    else:
        snapshot = copy.deepcopy(rows["revision"].snapshot)
        snapshot["citations"][0]["excerpt"] = "PRIVATE-SNAPSHOT-TEXT" * 10_000
        rows["revision"].snapshot = snapshot
    db.commit()
    monkeypatch.setattr(routes, "EXPORT_BYTE_CAP", 30_000)
    response = _export(client, org, headers)
    _assert_no_download(response, 413)
    assert "PRIVATE-" not in response.text
    _no_receipt(db, org)


@pytest.mark.parametrize("state", ["removed-membership", "inactive-user", "inactive-org"])
def test_export_rechecks_active_identity_and_membership(client, db, state):
    org, user, headers = _identity(db, "revoked")
    _graph_assessment(db, org, user)
    if state == "removed-membership":
        db.query(OrganizationMembership).filter_by(organization_id=org.id, user_id=user.id).delete()
    elif state == "inactive-user":
        user.is_active = False
    else:
        org.is_active = False
    db.commit()
    response = _export(client, org, headers)
    assert response.status_code in (401, 403)
    _assert_no_download(response, response.status_code)
    _no_receipt(db, org)
