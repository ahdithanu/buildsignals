"""Bounded, non-publishing qualification of official Biloxi DRC agenda items.

This is technical evidence, not a license determination or source activation.
Run with PYTHONPATH=. python scripts/qualify_biloxi.py --live.
"""
from __future__ import annotations

import argparse
import json

from app.services.ingestion.connectors.base import RetryingHttpClient
from app.services.ingestion.connectors.planning_documents import PlanningDocumentsConnector

ENDPOINT = "https://biloxi.ms.us/category/agendas-drc/"


def decode_archive(body: bytes) -> str:
    # Official archive mixes valid UTF-8 with legacy Windows smart-quote bytes.
    text = body.decode("utf-8-sig", errors="surrogateescape")
    return "".join(bytes([ord(char) - 0xDC00]).decode("cp1252")
                   if 0xDC80 <= ord(char) <= 0xDCFF else char for char in text)


class BiloxiQualificationClient(RetryingHttpClient):
    def get_text(self, url, *, params=None, headers=None, encoding="utf-8-sig"):
        body, _ = self.get_bytes(url, max_bytes=2_000_000, params=params, headers=headers)
        return decode_archive(body)


SETTINGS = {
    "href_pattern": r"/agendas/DRC/20\d{2}/[^/?]+\.pdf$",
    "index_page_pattern": r"https://biloxi\.ms\.us/drc-agenda[^/?]*/$",
    "item_pattern": r"^\s*(?P<item_number>\d+)\.\s+\d{1,2}:\d{2}\b",
    "file_pattern": r"\b(?P<file_number>20\d{2}-\d{3})\b",
    "value_patterns": {
        "project_name": r"^(?:New|Resubmit)\s*\n(?P<value>[^\n]+)",
        "address": r"^(?:New|Resubmit)\s*\n[^\n]+\n(?P<value>[^\n]+)",
        "parcel_id": r"^(?P<value>\d{4}[A-Z]-\d{2}-\d{3}\.\d{3})\s*$",
        "parcel_reference": r"^(?P<value>\d{4}[A-Z]-\d{2}-\d{3}\.\d{3}[^\n]*)$",
        "review_type": r"^(?P<value>New|Resubmit)\s*$",
    },
    # In this table, the individual representative line immediately precedes ward.
    "suppression_patterns": [r"^(?:(?!\d|New|Resubmit)[^\n]+\n){1,3}(?=\d+(?:&\d+)*\s*(?:\n|$))"],
    "document_type_patterns": {"agenda": r"DRC"},
    "meeting_name": "Development Review Committee",
    "governing_body": "City of Biloxi",
    "document_allowed_hosts": frozenset({"biloxi.ms.us"}),
    "max_documents": 3,
    "max_index_pages": 4,
    "max_document_bytes": 2_000_000,
    "max_items_per_document": 25,
    "max_item_characters": 5_000,
    "max_records": 75,
    "page_size": 75,
    "timeout": 25,
    "max_retries": 1,
}


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
    client = BiloxiQualificationClient(timeout=25, max_retries=1, allowed_hosts=frozenset({"biloxi.ms.us"}))
    records = list(PlanningDocumentsConnector(ENDPOINT, http_client=client, **SETTINGS).iter_records())
    receipt = qualification_receipt(records)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt["status"] == "verified" else 1)
