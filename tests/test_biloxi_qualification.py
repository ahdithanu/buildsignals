from datetime import date

from app.services.ingestion.connectors.planning_documents import PlanningDocumentsConnector
from app.services.ingestion.planning_items import PageText, segment_planning_items
from scripts.qualify_biloxi import ENDPOINT, SETTINGS, decode_archive, qualification_receipt


def test_biloxi_mixed_archive_encoding_preserves_valid_utf8():
    assert decode_archive(b"City\x92s caf\xc3\xa9") == "City\u2019s caf\u00e9"


def test_biloxi_rules_keep_projects_and_suppress_individual_representatives():
    connector = PlanningDocumentsConnector(ENDPOINT, **SETTINGS)
    text = "1. 9:00\n2026-101\nNew\nExample Coffee LLC\n123 Example Road\n1234A-01-001.000\nPrivate Representative\n2\n2. 9:30\n"
    suppressed = connector._suppress(text)
    assert "Private Representative" not in suppressed
    items = segment_planning_items(
        [PageText(1, suppressed)], meeting_date=date(2026, 10, 14),
        document_hash="a" * 64, source_url="https://biloxi.ms.us/agendas/DRC/2026/DRC-10-14-26.pdf",
        rules=connector.rules,
    )
    assert len(items) == 1
    assert items[0].reference_number == "2026-101"
    assert items[0].values == {"project_name": "Example Coffee LLC", "address": "123 Example Road",
                               "parcel_id": "1234A-01-001.000", "parcel_reference": "1234A-01-001.000", "review_type": "New"}


def test_biloxi_compound_references_are_not_a_single_parcel_identity():
    connector = PlanningDocumentsConnector(ENDPOINT, **SETTINGS)
    text = "1. 9:00\n2026-102\nNew\nExample Store\nHighway 1 & Example Road\n1234A-01-001.000 & 1234A-01-002.000\nPrivate Person and Architect\nAnother Representative\n1&2\n"
    suppressed = connector._suppress(text)
    assert "Private Person" not in suppressed and "Another Representative" not in suppressed
    items = segment_planning_items([PageText(1, suppressed)], meeting_date=date(2026, 10, 14),
        document_hash="a" * 64, source_url=ENDPOINT, rules=connector.rules)
    assert items[0].values["address"] == "Highway 1 & Example Road"
    assert "parcel_id" not in items[0].values
    assert " & " in items[0].values["parcel_reference"]


def test_biloxi_qualification_fails_closed_on_empty_or_incomplete_items():
    assert qualification_receipt([])["status"] == "failed"
    row = {"reference_number": "2026-101", "meeting_date": "2026-10-14",
           "source_url": ENDPOINT, "document_hash": "a" * 64, "source_pages": [1]}
    receipt = qualification_receipt([row])
    assert receipt["status"] == "failed"
    assert receipt["invalid_record_indexes"] == [0]
    assert receipt["not_evidence_of"] == ["permit_submission", "approval", "construction", "for_sale"]
