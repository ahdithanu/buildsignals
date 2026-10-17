"""Bounded, non-publishing qualification of official Biloxi DRC agenda items.

This is technical evidence, not a license determination or source activation.
The reviewed connector configuration lives in the candidate catalog entry
``biloxi_ms_development_review_agendas`` (inert ``probe_settings``); this script
loads that single source of truth and runs it through the production
``planning_documents`` connector, including the shared source-specific mixed
UTF-8/Windows-1252 decoder. Run with ``PYTHONPATH=. python scripts/qualify_biloxi.py --live``.
"""
from __future__ import annotations

import argparse
import json

from app.services.ingestion.catalog import load_candidate_catalog
from app.services.ingestion.connectors.planning_documents import PlanningDocumentsConnector
from app.services.ingestion.text_decoding import decode_mixed_utf8_cp1252

# Backwards-compatible alias: the mixed-encoding handling now lives in the shared
# ingestion decoder so the deployed connector uses the exact same logic.
decode_archive = decode_mixed_utf8_cp1252

_CANDIDATE_KEY = "biloxi_ms_development_review_agendas"


def _load_connector_settings() -> tuple[str, dict]:
    entry = next(
        candidate
        for candidate in load_candidate_catalog()
        if candidate.key == _CANDIDATE_KEY
    )
    connector = dict((entry.probe_settings or {}).get("connector") or {})
    if not connector:
        raise RuntimeError(f"{_CANDIDATE_KEY} is missing a reviewed connector configuration")
    endpoint = connector.pop("endpoint")
    return endpoint, connector


ENDPOINT, SETTINGS = _load_connector_settings()


def qualification_receipt(records):
    required = ("reference_number", "project_name", "address",
                "meeting_date", "document_hash", "source_pages", "source_url")
    invalid = [index for index, row in enumerate(records) if any(not row.get(k) for k in required)]
    return {
        "source": ENDPOINT,
        "scope": "Technical qualification only; no database writes or production activation",
        "status": "verified" if records and not invalid else "failed",
        "records": len(records),
        "invalid_record_indexes": invalid,
        "documents": len({row["document_hash"] for row in records}),
        "exact_format_parcel_references": sum(bool(row.get("parcel_id")) for row in records),
        "compound_unresolved_references": sum(bool(row.get("parcel_reference")) and not row.get("parcel_id") for row in records),
        "unknown_parcel_references": sum(not row.get("parcel_reference") for row in records),
        "event_kind": "proposed_development_review_agenda_item",
        "not_evidence_of": ["permit_submission", "approval", "construction", "for_sale"],
        "evidence": [{k: row[k] for k in ("reference_number", "meeting_date", "source_url", "document_hash", "source_pages")} for row in records],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    records = list(PlanningDocumentsConnector(ENDPOINT, **SETTINGS).iter_records())
    receipt = qualification_receipt(records)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt["status"] == "verified" else 1)
