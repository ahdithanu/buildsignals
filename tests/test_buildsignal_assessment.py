from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.signal import Signal
from app.utils.org_scope import get_org_id


def setup_draft(db):
    org = get_org_id()
    db.add(Signal(id="signal", organization_id=org, signal_type="zoning_update"))
    db.add_all([
        GraphEntity(id="parcel", organization_id=org, entity_type="parcel",
                    display_name="Parcel A", normalized_name="parcel a"),
        GraphEntity(id="city", organization_id=org, entity_type="city",
                    display_name="City A", normalized_name="city a"),
    ])
    db.flush()
    db.add(GraphRelationship(id="relationship", organization_id=org,
                             source_entity_id="parcel", target_entity_id="city",
                             relationship_type="related_to"))
    db.flush()
    db.add(GraphRelationshipEvidence(id="evidence", organization_id=org,
                                     relationship_id="relationship", source_system="planning",
                                     excerpt="Rezoning application submitted"))
    db.commit()
    return {
        "detected_change": "A rezoning application was submitted",
        "investment_thesis": "Additional density could increase development potential",
        "change_confidence": {"level": "high", "rationale": "Public filing"},
        "thesis_confidence": {"level": "low", "rationale": "Approval and feasibility unknown"},
        "citations": [{"evidence_id": "evidence", "stance": "supports", "claim": "change",
                       "rationale": "Records the submission"}],
        "implications": [{"entity_id": "parcel", "mechanism": "Potential density increase",
                          "direction": "uncertain", "horizon": "12-24 months",
                          "evidence_ids": ["evidence"]}],
        "further_investigation": ["Check utility capacity and planning opposition"],
    }


def test_preview_resolves_evidence_and_flags_unsupported_thesis(client, db):
    payload = setup_draft(db)
    response = client.post("/signals/signal/assessment-preview", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "draft"
    assert result["citations"][0]["excerpt"] == "Rezoning application submitted"
    assert result["implications"][0]["entity_name"] == "Parcel A"
    assert "Investment thesis has no supporting citation." in result["review_flags"]
    assert db.query(Signal).count() == 1


def test_preview_rejects_unlinked_evidence(client, db):
    payload = setup_draft(db)
    payload["implications"][0]["evidence_ids"] = ["invented"]
    assert client.post("/signals/signal/assessment-preview", json=payload).status_code == 422


def test_preview_rejects_cross_tenant_evidence(client, db):
    payload = setup_draft(db)
    db.get(GraphRelationshipEvidence, "evidence").organization_id = "another-org"
    db.commit()
    response = client.post("/signals/signal/assessment-preview", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment reference not found"


def test_preview_rejects_cross_tenant_signal(client, db):
    payload = setup_draft(db)
    db.get(Signal, "signal").organization_id = "another-org"
    db.commit()
    assert client.post("/signals/signal/assessment-preview", json=payload).status_code == 404


def test_counterevidence_is_preserved(client, db):
    payload = setup_draft(db)
    payload["citations"].append({"evidence_id": "evidence", "stance": "contradicts",
                                 "claim": "thesis", "rationale": "Filing does not grant density"})
    result = client.post("/signals/signal/assessment-preview", json=payload).json()
    assert result["citations"][1]["stance"] == "contradicts"
    assert not any("counterevidence review required" in flag and "thesis" in flag
                   for flag in result["review_flags"])
