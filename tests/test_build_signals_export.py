from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models.ingestion import IngestionSource, PermitRecord
from app.services.ingestion.build_signals_export import (
    build_batches,
    publish_batch,
    serialize_permit,
    validate_target_url,
)
from app.services.ingestion.cli import build_parser


def _permit(*, external_record_id: str = "mesa-1001") -> PermitRecord:
    source = IngestionSource(
        id="source-1",
        organization_id="org-1",
        key="mesa_az_commercial_permit_submittals",
        name="Mesa Commercial Permit Submittals",
        adapter="socrata",
        record_type="permit",
        jurisdiction="Mesa, Arizona",
        base_url="https://data.mesaaz.gov/permits",
    )
    permit = PermitRecord(
        id="permit-1",
        organization_id="org-1",
        source_id=source.id,
        latest_raw_record_id="raw-1",
        external_record_id=external_record_id,
        normalization_hash="a" * 64,
        application_number="PMT25-1001",
        permit_number=None,
        approval_stage="pre_approval",
        permit_type="COMMERCIAL BUILDING",
        permit_subtype="Tenant Improvement",
        status="Plan Review",
        description="Tenant improvement for a Dutch Bros coffee shop.",
        project_name="Dutch Bros - East Main Street",
        address="1234 E Main St",
        city="Mesa",
        state="AZ",
        parcel_id="140-01-001",
        jurisdiction="City of Mesa",
        owner_name="Main Street Owner LLC",
        developer_name="Retail Growth Partners LLC",
        contractor_name="Desert Build Co",
        architect_name="Studio Retail Architects",
        engineer_name="Southwest Civil Engineering",
        valuation=Decimal("650000"),
        filed_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        status_updated_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        source_url="https://data.mesaaz.gov/permits/mesa-1001",
        attributes={"confidence": 0.93, "source_status": "In Review"},
        first_seen_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    permit.source = source
    return permit


def test_serializes_preapproval_record_with_parties_and_evidence():
    record = serialize_permit(_permit())

    assert record["marketId"] == "az-mesa"
    assert record["approvalStage"] == "pre_approval"
    assert record["applicationNumber"] == "PMT25-1001"
    assert record["parties"]["developer"] == "Retail Growth Partners LLC"
    assert record["parties"]["owner"] == "Main Street Owner LLC"
    assert record["parties"]["architect"] == "Studio Retail Architects"
    assert record["evidence"]["recordUrl"].endswith("/mesa-1001")
    assert record["confidence"] == 0.93
    assert record["attributes"]["valuation"] == 650000.0


def test_builds_versioned_source_batches():
    generated_at = datetime(2026, 8, 15, 22, 0, tzinfo=timezone.utc)
    batches = build_batches([_permit()], generated_at=generated_at)

    assert len(batches) == 1
    assert batches[0]["version"] == "1.0"
    assert batches[0]["batchId"] == (
        "mesa_az_commercial_permit_submittals-az-mesa-20260815T220000Z-1"
    )
    assert batches[0]["source"]["key"] == "mesa_az_commercial_permit_submittals"
    assert len(batches[0]["records"]) == 1


def test_publish_sends_bearer_auth_and_parses_acknowledgement():
    batch = build_batches([_permit()])[0]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({
                "ok": True,
                "result": {
                    "batchId": batch["batchId"],
                    "sourceKey": batch["source"]["key"],
                    "recordsFound": 1,
                    "recordsInserted": 1,
                    "recordsUpdated": 0,
                },
            }).encode()

    with patch(
        "app.services.ingestion.build_signals_export.urlopen",
        return_value=FakeResponse(),
    ) as open_request:
        result = publish_batch(
            "https://www.buildsignals.ai/api/internal/ingestion/import",
            "shared-secret",
            batch,
        )

    request = open_request.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer shared-secret"
    assert result.records_inserted == 1
    assert result.source_key == "mesa_az_commercial_permit_submittals"


def test_rejects_insecure_remote_target():
    with pytest.raises(ValueError, match="must use HTTPS"):
        validate_target_url("http://example.com/api/internal/ingestion/import")


def test_cli_supports_dry_run_publish_scope():
    args = build_parser().parse_args([
        "publish-build-signals",
        "--organization",
        "default",
        "--source-key",
        "mesa_az_commercial_permit_submittals",
        "--stage",
        "pre_approval_and_approved",
        "--dry-run",
    ])

    assert args.command == "publish-build-signals"
    assert args.source_keys == ["mesa_az_commercial_permit_submittals"]
    assert args.dry_run is True
