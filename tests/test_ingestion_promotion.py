from __future__ import annotations

import json
from datetime import date

import pytest

from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion import promotion
from app.services.ingestion.promotion import (
    PromotionReview,
    build_promotion_entry,
    prepare_promotion_manifest,
)


def _candidate() -> IngestionSourceCandidate:
    return IngestionSourceCandidate(
        key="test_or_planning_applications",
        name="Test Planning Applications",
        adapter="csv",
        record_type="permit",
        jurisdiction="Test, OR",
        base_url="https://example.test/planning.csv",
        official_landing_page="https://example.test/planning",
        license="Test Open Data Terms",
        status="operational_retry",
        blocker_summary="Awaiting review.",
        early_warning_value="Pre-approval applications.",
        candidate_source_fields=["id", "status"],
        probe_settings={
            "connector": {"page_size": 10},
            "defaults": {"state": "OR", "approval_stage": "pre_approval"},
        },
        probe_field_mappings=[
            {"source_field": "id", "canonical_field": "source_record_id"},
            {"source_field": "status", "canonical_field": "status"},
        ],
        production_page_size=500,
        last_checked_on=date(2026, 8, 1),
        next_audit_on=date(2026, 8, 8),
        notes="Test candidate.",
    )


def _review(**updates) -> PromotionReview:
    payload = {
        "schema_version": 1,
        "candidate_key": "test_or_planning_applications",
        "decision": "approved_for_production",
        "reviewed_by": "Data Governance",
        "reviewed_on": "2026-08-09",
        "candidate_canary_completed_on": "2026-08-08",
        "rights_approved": True,
        "data_minimization_approved": True,
        "settings": {
            "official_landing_page": "https://example.test/planning",
            "license": "Test Open Data Terms",
            "reconciliation_mode": "daily_incremental",
            "freshness_sla_hours": 24,
            "freshness_semantics": "ingestion_observed_at",
            "signal_stage": "pre_approval_and_approved",
            "connector": {"page_size": 500},
            "rights_basis": "Reviewed for commercial derived intelligence use.",
            "export_policy": "derived_intelligence_only_no_raw_export",
            "field_allowlist": ["id", "status"],
            "suppressed_fields": [],
        },
        "field_mappings": [
            {
                "source_field": "id",
                "canonical_field": "source_record_id",
                "is_required": True,
            },
            {"source_field": "status", "canonical_field": "status"},
        ],
    }
    payload.update(updates)
    return PromotionReview.model_validate(payload)


def test_build_promotion_entry_uses_complete_reviewed_production_configuration():
    entry = build_promotion_entry(_candidate(), _review())

    assert entry.settings["connector"]["page_size"] == 500
    assert "defaults" not in entry.settings
    assert entry.settings["candidate_key"] == "test_or_planning_applications"
    assert entry.settings["candidate_status"] == "approved_for_production"
    assert entry.settings["promotion_rights_approved"] is True
    assert len(entry.field_mappings) == 2


def test_build_promotion_entry_rejects_stale_canary_and_predated_review():
    with pytest.raises(ValueError, match="older than the candidate audit date"):
        build_promotion_entry(
            _candidate(),
            _review(candidate_canary_completed_on="2026-08-07"),
        )
    with pytest.raises(ValueError, match="cannot predate"):
        build_promotion_entry(
            _candidate(),
            _review(reviewed_on="2026-08-07"),
        )


def test_build_promotion_entry_rejects_key_mismatch_and_missing_identity_mapping():
    with pytest.raises(ValueError, match="does not match"):
        build_promotion_entry(
            _candidate(),
            _review(candidate_key="different_candidate"),
        )
    with pytest.raises(ValueError, match="source_record_id mapping"):
        build_promotion_entry(
            _candidate(),
            _review(
                field_mappings=[
                    {"source_field": "status", "canonical_field": "status"}
                ]
            ),
        )


def test_build_promotion_entry_rejects_duplicate_mapping_sources():
    mappings = _review().field_mappings
    with pytest.raises(ValueError, match="duplicate source fields"):
        build_promotion_entry(
            _candidate(),
            _review(field_mappings=[*mappings, mappings[0]]),
        )


def test_build_promotion_entry_requires_governance_evidence():
    for setting, expected in (
        ("rights_basis", "governance evidence"),
        ("export_policy", "governance evidence"),
        ("field_allowlist", "field_allowlist"),
        ("suppressed_fields", "suppressed_fields"),
    ):
        settings = dict(_review().settings)
        settings.pop(setting)
        with pytest.raises(ValueError, match=expected):
            build_promotion_entry(_candidate(), _review(settings=settings))


def test_build_promotion_entry_rejects_connector_url_override():
    settings = {
        **_review().settings,
        "connector": {
            "source": "https://attacker.example/unreviewed.csv",
            "page_size": 500,
        },
    }

    with pytest.raises(ValueError, match="must match the canaried candidate"):
        build_promotion_entry(_candidate(), _review(settings=settings))


def test_build_promotion_entry_rejects_unknown_canonical_field():
    mappings = [
        mapping.model_dump(mode="json") for mapping in _review().field_mappings
    ]
    mappings.append(
        {"source_field": "bad", "canonical_field": "developer_nmae"}
    )

    with pytest.raises(ValueError, match="unknown permit canonical fields"):
        build_promotion_entry(_candidate(), _review(field_mappings=mappings))


def test_prepare_promotion_manifest_writes_valid_deterministic_catalog(
    tmp_path, monkeypatch
):
    candidate = _candidate()
    monkeypatch.setattr(
        promotion,
        "load_candidate_catalog",
        lambda *args, **kwargs: [candidate],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(_review().model_dump_json(), encoding="utf-8")
    existing_path = tmp_path / "existing.json"
    existing_path.write_text("[]\n", encoding="utf-8")
    output_path = tmp_path / "promoted.json"

    result = prepare_promotion_manifest(
        candidate_key=candidate.key,
        review_path=review_path,
        output_path=output_path,
        promoted_catalog_path=existing_path,
    )

    assert [entry.key for entry in result] == [candidate.key]
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["settings"]["candidate_status"] == "approved_for_production"
    assert not (tmp_path / ".promoted.json.tmp").exists()

    reordered_review = _review(
        settings=dict(reversed(list(_review().settings.items())))
    )
    reordered_path = tmp_path / "reordered-review.json"
    reordered_path.write_text(reordered_review.model_dump_json(), encoding="utf-8")
    reordered_output = tmp_path / "reordered-promoted.json"
    prepare_promotion_manifest(
        candidate_key=candidate.key,
        review_path=reordered_path,
        output_path=reordered_output,
        promoted_catalog_path=existing_path,
    )
    assert reordered_output.read_bytes() == output_path.read_bytes()

    original = output_path.read_bytes()
    prepare_promotion_manifest(
        candidate_key=candidate.key,
        review_path=review_path,
        output_path=output_path,
        promoted_catalog_path=output_path,
    )
    assert output_path.read_bytes() == original

    review_path.write_text(
        _review(
            settings={
                **_review().settings,
                "connector": {"page_size": 501},
            }
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="use --replace"):
        prepare_promotion_manifest(
            candidate_key=candidate.key,
            review_path=review_path,
            output_path=output_path,
            promoted_catalog_path=output_path,
        )

    replaced = prepare_promotion_manifest(
        candidate_key=candidate.key,
        review_path=review_path,
        output_path=output_path,
        promoted_catalog_path=output_path,
        replace=True,
    )
    assert replaced[0].settings["connector"]["page_size"] == 501


def test_promotion_review_requires_explicit_approvals():
    payload = _review().model_dump(mode="json")
    payload["rights_approved"] = False

    with pytest.raises(ValueError, match="rights_approved"):
        PromotionReview.model_validate(payload)

    payload = _review().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unexpected"):
        PromotionReview.model_validate(payload)


def test_failed_production_validation_leaves_manifest_unchanged(tmp_path, monkeypatch):
    candidate = _candidate()
    monkeypatch.setattr(
        promotion,
        "load_candidate_catalog",
        lambda *args, **kwargs: [candidate],
    )
    review = _review()
    invalid_settings = dict(review.settings)
    invalid_settings.pop("freshness_sla_hours")
    review_path = tmp_path / "review.json"
    review_path.write_text(
        _review(settings=invalid_settings).model_dump_json(),
        encoding="utf-8",
    )
    manifest = tmp_path / "promoted.json"
    manifest.write_text("[]\n", encoding="utf-8")
    original = manifest.read_bytes()

    with pytest.raises(ValueError, match="freshness_sla_hours"):
        prepare_promotion_manifest(
            candidate_key=candidate.key,
            review_path=review_path,
            output_path=manifest,
            promoted_catalog_path=manifest,
        )

    assert manifest.read_bytes() == original
    assert list(tmp_path.glob(".promoted.json.*.tmp")) == []


def test_concurrent_destination_change_aborts_and_cleans_temp(tmp_path, monkeypatch):
    candidate = _candidate()
    monkeypatch.setattr(
        promotion,
        "load_candidate_catalog",
        lambda *args, **kwargs: [candidate],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(_review().model_dump_json(), encoding="utf-8")
    output = tmp_path / "promoted.json"
    output.write_text("[]\n", encoding="utf-8")
    fingerprints = iter(["before", "after"])
    monkeypatch.setattr(promotion, "_file_fingerprint", lambda _path: next(fingerprints))

    with pytest.raises(RuntimeError, match="changed while preparing"):
        prepare_promotion_manifest(
            candidate_key=candidate.key,
            review_path=review_path,
            output_path=output,
            promoted_catalog_path=output,
        )

    assert output.read_text(encoding="utf-8") == "[]\n"
    assert list(tmp_path.glob(".promoted.json.*.tmp")) == []
