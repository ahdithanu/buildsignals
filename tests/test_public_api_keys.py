from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.utils.api_key_deps as api_key_deps
from app.models.api_key import OrganizationApiKey
from app.models.api_usage import OrganizationApiKeyUsageEvent
from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.deal import Deal
from app.models.evaluation import EvalCase, EvalDataset, EvalMetric, EvalResult, EvalRun
from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipEvidence,
    GraphRelationshipType,
)
from app.models.signal import Signal
from app.services.api_key_service import create_api_key, revoke_api_key
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email: str, org_name: str) -> dict:
    response = client.post("/auth/register", json={
        "email": email,
        "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _issue_key(db, *, org_id: str, user_id: str, scopes: list[str]) -> tuple[OrganizationApiKey, str]:
    api_key, secret = create_api_key(
        db,
        organization_id=org_id,
        name="Warehouse export",
        scopes=scopes,
        actor_id=user_id,
    )
    db.commit()
    db.refresh(api_key)
    return api_key, secret


def _seed_deal(db, *, org_id: str, name: str) -> Deal:
    deal = Deal(
        organization_id=org_id,
        name=name,
        address="100 Main St",
        city="Austin",
        state="TX",
        property_type="Industrial",
        source="fixture",
    )
    db.add(deal)
    db.flush()
    signal = Signal(
        organization_id=org_id,
        deal_id=deal.id,
        signal_type="permit",
        source="fixture",
        description=f"{name} permit movement",
        severity=8.2,
    )
    db.add(signal)
    db.commit()
    db.refresh(deal)
    return deal


def _seed_graph_context(db, *, org_id: str, deal: Deal, developer_name: str) -> None:
    opportunity = GraphEntity(
        organization_id=org_id,
        entity_type=GraphEntityType.property,
        display_name=deal.name,
        normalized_name=deal.name.lower(),
        normalized_address=(deal.address or "").lower(),
        address=deal.address,
        city=deal.city,
        state=deal.state,
        confidence=1.0,
    )
    developer = GraphEntity(
        organization_id=org_id,
        entity_type=GraphEntityType.developer,
        display_name=developer_name,
        normalized_name=developer_name.lower(),
        confidence=0.91,
    )
    db.add_all([opportunity, developer])
    db.flush()
    db.add(GraphEntityLink(
        organization_id=org_id,
        entity_id=opportunity.id,
        record_type="deal",
        record_id=deal.id,
        source_system="fixture",
    ))
    relationship = GraphRelationship(
        organization_id=org_id,
        source_entity_id=opportunity.id,
        target_entity_id=developer.id,
        relationship_type=GraphRelationshipType.developed_by,
        confidence=0.86,
        source_system="fixture",
        source_id=f"developer:{deal.id}",
    )
    db.add(relationship)
    db.flush()
    db.add(GraphRelationshipEvidence(
        organization_id=org_id,
        relationship_id=relationship.id,
        source_system="county_permits",
        source_id=f"permit:{deal.id}",
        evidence_type="permit_record",
        excerpt=f"{developer_name} listed on permit",
        confidence=0.88,
    ))
    db.commit()


def _seed_eval_run(db, *, org_id: str, name: str, gate_passed: bool = True) -> EvalRun:
    dataset = EvalDataset(
        organization_id=org_id,
        name=f"{name} dataset",
        workflow="copilot_answer",
    )
    db.add(dataset)
    db.flush()
    case = EvalCase(
        organization_id=org_id,
        dataset_id=dataset.id,
        name=f"{name} case",
        input_json={"question": "Why does this opportunity matter?"},
        expected_output={"required_phrases": ["permit"], "forbidden_phrases": []},
        retrieved_context=[{"id": "permit-a", "text": "Permit evidence"}],
        critical=True,
    )
    db.add(case)
    db.flush()
    run = EvalRun(
        organization_id=org_id,
        dataset_id=dataset.id,
        mode="replay",
        model="gpt-test",
        prompt_version="prompt-v1",
        status="completed",
        dataset_fingerprint="fixture",
        thresholds={
            "minimum_quality": 0.8,
            "minimum_citation_accuracy": 1.0,
            "minimum_factual_coverage": 0.8,
            "maximum_hallucination_risk": 0.0,
        },
        summary={
            "metrics": {
                "quality": 0.93,
                "citation_accuracy": 1.0,
                "hallucination_risk": 0.0,
                "factual_coverage": 0.91,
                "rule_compliance": 1.0,
            },
            "case_count": 1,
            "passed_count": 1,
            "error_count": 0,
            "critical_failed": False,
        },
        gate_passed=gate_passed,
    )
    db.add(run)
    db.flush()
    result = EvalResult(
        organization_id=org_id,
        run_id=run.id,
        case_id=case.id,
        case_snapshot={
            "id": case.id,
            "dataset_id": dataset.id,
            "name": case.name,
            "input_json": case.input_json,
            "expected_output": case.expected_output,
            "retrieved_context": case.retrieved_context,
            "critical": case.critical,
            "created_at": case.created_at.isoformat(),
        },
        actual_output={
            "text": "Permit evidence supports the opportunity.",
            "citations": [{"source_id": "permit-a", "quote": "Permit evidence"}],
        },
        retrieved_context=case.retrieved_context,
        status="passed",
        model=run.model,
        prompt_version=run.prompt_version,
        latency_ms=1200,
        tokens_input=100,
        tokens_output=80,
        cost_usd=0.01,
    )
    db.add(result)
    db.flush()
    db.add_all([
        EvalMetric(
            organization_id=org_id,
            result_id=result.id,
            name="quality",
            value=0.93,
        ),
        EvalMetric(
            organization_id=org_id,
            result_id=result.id,
            name="citation_accuracy",
            value=1.0,
        ),
    ])
    db.commit()
    db.refresh(run)
    return run


def _assessment_snapshot(signal_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1",
        "signal_id": signal_id,
        "status": "draft",
        "detected_change": "Industrial tenant improvement permit moved into review.",
        "event_at": now,
        "investment_thesis": "Permit movement suggests near-term occupancy demand.",
        "change_confidence": {"level": "high", "rationale": "Permit record names the site."},
        "thesis_confidence": {"level": "medium", "rationale": "Use still requires diligence."},
        "citations": [
            {
                "evidence_id": "evidence-public-api",
                "stance": "supports",
                "claim": "change",
                "rationale": "Permit status changed.",
                "source_system": "county_permits",
                "source_id": "PERMIT-1",
                "source_url": "https://example.test/permit",
                "excerpt": "Plan review opened for tenant improvement.",
                "observed_at": now,
                "relationship_id": "relationship-public-api",
                "relationship_is_current": True,
                "relationship_last_verified_at": now,
            }
        ],
        "implications": [
            {
                "entity_id": "entity-public-api",
                "mechanism": "Occupancy-triggered demand",
                "direction": "positive",
                "horizon": "0-6 months",
                "evidence_ids": ["evidence-public-api"],
                "entity_name": "Workflow Warehouse",
                "entity_type": "property",
            }
        ],
        "further_investigation": ["Confirm tenant identity."],
        "generated_at": now,
        "review_flags": ["Analyst-authored hypothesis; source linkage does not validate investment causality."],
    }


def _seed_workflow_history(db, *, org_id: str, deal: Deal) -> tuple[Signal, BuildSignalRevision]:
    signal = Signal(
        organization_id=org_id,
        deal_id=deal.id,
        signal_type="permit",
        source="fixture",
        description="Workflow permit signal",
        severity=8.7,
    )
    db.add(signal)
    db.flush()
    revision = BuildSignalRevision(
        organization_id=org_id,
        signal_id=signal.id,
        author_id="author-public-api",
        snapshot=_assessment_snapshot(signal.id),
    )
    db.add(revision)
    db.flush()
    review = BuildSignalReview(
        organization_id=org_id,
        revision_id=revision.id,
        reviewer_id="reviewer-public-api",
        decision="approved",
        rationale="Evidence chain is complete.",
    )
    db.add(review)
    db.flush()
    db.add(BuildSignalPublication(
        organization_id=org_id,
        revision_id=revision.id,
        actor_id="publisher-public-api",
        review_id=review.id,
        version=1,
        action="published",
        rationale="Ready for downstream warehouse export.",
    ))
    db.commit()
    db.refresh(signal)
    db.refresh(revision)
    return signal, revision


def test_public_api_key_reads_only_own_organization(client, db):
    first = _register(client, email="public-first@example.com", org_name="Public First")
    second = _register(client, email="public-second@example.com", org_name="Public Second")
    first_deal = _seed_deal(db, org_id=first["organization_id"], name="First org warehouse")
    _seed_deal(db, org_id=second["organization_id"], name="Second org warehouse")
    api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    listed = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [first_deal.id]

    detail = client.get(f"/public/deals/{first_deal.id}", headers={"X-API-Key": secret})
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "First org warehouse"

    signals = client.get("/public/signals", headers={"Authorization": f"Bearer {secret}"})
    assert signals.status_code == 200, signals.text
    assert len(signals.json()) == 1
    assert signals.json()[0]["deal_id"] == first_deal.id

    db.refresh(api_key)
    assert api_key.last_used_at is not None
    usage_events = (
        db.query(OrganizationApiKeyUsageEvent)
        .filter_by(api_key_id=api_key.id)
        .order_by(OrganizationApiKeyUsageEvent.created_at.asc())
        .all()
    )
    assert [(event.method, event.path, event.response_items) for event in usage_events] == [
        ("GET", "/public/deals", 1),
        ("GET", "/public/deals/{deal_id}", 1),
        ("GET", "/public/signals", 1),
    ]


def test_public_api_list_routes_include_pagination_headers(client, db):
    identity = _register(client, email="public-page@example.com", org_name="Public Page")
    for index in range(3):
        _seed_deal(db, org_id=identity["organization_id"], name=f"Paged warehouse {index}")
    _, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )

    deals = client.get(
        "/public/deals?skip=1&limit=1",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert deals.status_code == 200, deals.text
    assert len(deals.json()) == 1
    assert deals.headers["X-Total-Count"] == "3"
    assert deals.headers["X-Page-Skip"] == "1"
    assert deals.headers["X-Page-Limit"] == "1"
    assert deals.headers["X-Next-Skip"] == "2"

    signals = client.get(
        "/public/signals?skip=2&limit=1",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert signals.status_code == 200, signals.text
    assert len(signals.json()) == 1
    assert signals.headers["X-Total-Count"] == "3"
    assert signals.headers["X-Next-Skip"] == ""


def test_public_api_returns_tenant_scoped_graph_context(client, db):
    first = _register(client, email="public-graph-first@example.com", org_name="Public Graph First")
    second = _register(client, email="public-graph-second@example.com", org_name="Public Graph Second")
    first_deal = _seed_deal(db, org_id=first["organization_id"], name="First graph warehouse")
    second_deal = _seed_deal(db, org_id=second["organization_id"], name="Second graph warehouse")
    _seed_graph_context(
        db,
        org_id=first["organization_id"],
        deal=first_deal,
        developer_name="Riverstone Development",
    )
    _seed_graph_context(
        db,
        org_id=second["organization_id"],
        deal=second_deal,
        developer_name="Other Org Developer",
    )
    _api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    response = client.get(
        f"/public/deals/{first_deal.id}/graph-context",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["opportunity_id"] == first_deal.id
    assert body["root_entities"][0]["display_name"] == "First graph warehouse"
    assert body["developers"][0]["entity"]["display_name"] == "Riverstone Development"
    assert body["developers"][0]["relationship"]["evidence"][0]["source_system"] == "county_permits"

    cross_org = client.get(
        f"/public/deals/{second_deal.id}/graph-context",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert cross_org.status_code == 404


def test_public_api_returns_tenant_scoped_eval_runs(client, db):
    first = _register(client, email="public-eval-first@example.com", org_name="Public Eval First")
    second = _register(client, email="public-eval-second@example.com", org_name="Public Eval Second")
    first_run = _seed_eval_run(db, org_id=first["organization_id"], name="First")
    second_run = _seed_eval_run(db, org_id=second["organization_id"], name="Second")
    api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    listed = client.get("/public/eval-runs", headers={"Authorization": f"Bearer {secret}"})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [first_run.id]
    assert listed.headers["X-Total-Count"] == "1"

    detail = client.get(
        f"/public/eval-runs/{first_run.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == first_run.id
    assert body["summary"]["metrics"]["citation_accuracy"] == 1.0
    assert body["results"][0]["metrics"]["quality"] == 0.93
    assert body["results"][0]["actual_output"]["citations"][0]["source_id"] == "permit-a"

    cross_org = client.get(
        f"/public/eval-runs/{second_run.id}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert cross_org.status_code == 404

    usage_events = (
        db.query(OrganizationApiKeyUsageEvent)
        .filter_by(api_key_id=api_key.id)
        .order_by(OrganizationApiKeyUsageEvent.created_at.asc())
        .all()
    )
    assert [(event.method, event.path, event.response_items) for event in usage_events] == [
        ("GET", "/public/eval-runs", 1),
        ("GET", "/public/eval-runs/{run_id}", 2),
    ]


def test_public_api_returns_tenant_scoped_workflow_history(client, db):
    first = _register(client, email="public-workflow-first@example.com", org_name="Public Workflow First")
    second = _register(client, email="public-workflow-second@example.com", org_name="Public Workflow Second")
    first_deal = _seed_deal(db, org_id=first["organization_id"], name="First workflow warehouse")
    second_deal = _seed_deal(db, org_id=second["organization_id"], name="Second workflow warehouse")
    signal, revision = _seed_workflow_history(db, org_id=first["organization_id"], deal=first_deal)
    _, second_revision = _seed_workflow_history(db, org_id=second["organization_id"], deal=second_deal)
    api_key, secret = _issue_key(
        db,
        org_id=first["organization_id"],
        user_id=first["user_id"],
        scopes=["read"],
    )

    history = client.get(
        f"/public/deals/{first_deal.id}/workflow-history",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["deal_id"] == first_deal.id
    assert [item["signal"]["id"] for item in body["signals"]] == [signal.id, first_deal.signals[0].id]
    workflow_signal = body["signals"][0]
    assert workflow_signal["assessment_revisions"][0]["id"] == revision.id
    assert workflow_signal["reviews"][0]["decision"] == "approved"
    assert workflow_signal["publication_events"][0]["action"] == "published"
    assert workflow_signal["assessment_revisions"][0]["snapshot"]["citations"][0]["source_system"] == "county_permits"

    revisions = client.get(
        f"/public/signals/{signal.id}/assessment-revisions",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert revisions.status_code == 200, revisions.text
    assert [row["id"] for row in revisions.json()] == [revision.id]

    reviews = client.get(
        f"/public/assessment-revisions/{revision.id}/reviews",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert reviews.status_code == 200, reviews.text
    assert reviews.json()[0]["rationale"] == "Evidence chain is complete."

    publications = client.get(
        f"/public/assessment-revisions/{revision.id}/publication",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert publications.status_code == 200, publications.text
    assert publications.json()[0]["rationale"] == "Ready for downstream warehouse export."

    assert client.get(
        f"/public/deals/{second_deal.id}/workflow-history",
        headers={"Authorization": f"Bearer {secret}"},
    ).status_code == 404
    assert client.get(
        f"/public/assessment-revisions/{second_revision.id}/reviews",
        headers={"Authorization": f"Bearer {secret}"},
    ).status_code == 404

    usage_events = (
        db.query(OrganizationApiKeyUsageEvent)
        .filter_by(api_key_id=api_key.id)
        .order_by(OrganizationApiKeyUsageEvent.created_at.asc())
        .all()
    )
    assert [(event.method, event.path, event.response_items) for event in usage_events] == [
        ("GET", "/public/deals/{deal_id}/workflow-history", 5),
        ("GET", "/public/signals/{signal_id}/assessment-revisions", 1),
        ("GET", "/public/assessment-revisions/{revision_id}/reviews", 1),
        ("GET", "/public/assessment-revisions/{revision_id}/publication", 1),
    ]


def test_public_api_rejects_missing_revoked_or_under_scoped_keys(client, db):
    identity = _register(client, email="public-scope@example.com", org_name="Public Scope")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["write"],
    )

    missing = client.get("/public/deals")
    assert missing.status_code == 401

    write_can_read = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert write_can_read.status_code == 200

    api_key.scopes = "[]"
    db.commit()
    under_scoped = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert under_scoped.status_code == 403

    api_key.scopes = '["read"]'
    revoke_api_key(db, api_key=api_key, actor_id=identity["user_id"])
    db.commit()
    revoked = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert revoked.status_code == 401


def test_public_api_rejects_expired_api_keys(client, db):
    identity = _register(client, email="public-expired@example.com", org_name="Public Expired")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    api_key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 401


def test_public_api_key_rate_limit_headers_and_enforcement(client, db, monkeypatch):
    identity = _register(client, email="public-rate@example.com", org_name="Public Rate")
    _seed_deal(db, org_id=identity["organization_id"], name="Rate-limited warehouse")
    _, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    monkeypatch.setattr(api_key_deps, "PUBLIC_API_KEY_LIMIT", 1)
    monkeypatch.setattr(api_key_deps, "PUBLIC_API_KEY_WINDOW", 60)

    first = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert first.status_code == 200, first.text
    assert first.headers["X-API-Key-RateLimit-Limit"] == "1"
    assert first.headers["X-API-Key-RateLimit-Remaining"] == "0"

    limited = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]


def test_admin_can_view_api_key_usage_summary(client, db):
    identity = _register(client, email="public-usage@example.com", org_name="Public Usage")
    _seed_deal(db, org_id=identity["organization_id"], name="Usage warehouse")
    api_key, secret = _issue_key(
        db,
        org_id=identity["organization_id"],
        user_id=identity["user_id"],
        scopes=["read"],
    )
    for _ in range(2):
        response = client.get("/public/deals", headers={"Authorization": f"Bearer {secret}"})
        assert response.status_code == 200

    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    listed = client.get(f"/organizations/{identity['organization_id']}/api-keys", headers=headers)
    assert listed.status_code == 200, listed.text
    [listed_key] = listed.json()
    assert listed_key["usage_total_calls"] == 2
    assert listed_key["usage_last_called_at"]
    assert listed_key["rate_limit_limit"] > 0

    usage = client.get(
        f"/organizations/{identity['organization_id']}/api-keys/{api_key.id}/usage",
        headers=headers,
    )
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["total_calls"] == 2
    assert body["total_items"] == 2
    assert body["daily"][0]["total_calls"] == 2
    assert body["daily"][0]["total_items"] == 2
    assert body["daily"][0]["average_latency_ms"] >= 0
    assert body["endpoints"][0]["path"] == "/public/deals"

    rebuild = client.post(
        f"/organizations/{identity['organization_id']}/api-keys/{api_key.id}/usage/rebuild-rollups",
        headers=headers,
    )
    assert rebuild.status_code == 200, rebuild.text
    assert rebuild.json()["rebuilt_events"] == 2
