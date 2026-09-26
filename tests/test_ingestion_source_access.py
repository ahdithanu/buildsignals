from datetime import date

from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.source_access import (
    build_source_access_contract,
    source_access_contract_json,
    source_access_contract_markdown,
)


def _candidate() -> IngestionSourceCandidate:
    return IngestionSourceCandidate(
        key="test_ak_records",
        name="Test Alaska Records",
        adapter="portal",
        record_type="permit",
        jurisdiction="Test, AK",
        base_url="https://example.gov/search",
        official_landing_page="https://example.gov/permits",
        license="Public data policy",
        status="technical_hold",
        blocker_summary="No supported recurring export.",
        early_warning_value="Application-stage records.",
        candidate_source_fields=["record_id", "status", "record_id"],
        last_checked_on=date(2026, 8, 15),
        next_audit_on=date(2026, 9, 12),
        notes="Request a supported export.",
    )


def test_source_access_contract_preserves_candidate_scope_and_deduplicates_fields():
    contract = build_source_access_contract(_candidate())

    assert contract.candidate_key == "test_ak_records"
    assert contract.requested_fields == ("record_id", "status")
    assert any("durable source record ID" in item for item in contract.reconciliation_requirements)
    assert any("Commercial SaaS" in item for item in contract.rights_confirmation)
    assert any("personal phone" in item for item in contract.privacy_limits)


def test_source_access_contract_renders_markdown_and_json():
    contract = build_source_access_contract(_candidate())

    markdown = source_access_contract_markdown(contract)
    json_content = source_access_contract_json(contract)

    assert "# Source Access Request: Test Alaska Records" in markdown
    assert "## Reconciliation requirements" in markdown
    assert '"candidate_key": "test_ak_records"' in json_content
