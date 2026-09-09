"""Read-only reconciliation; catalog configuration is not measured coverage."""
import re
from datetime import datetime, timezone

from app.services.ingestion.catalog import extract_state_code


def build_parcel_readiness(sources, candidates, ledger: str) -> dict:
    parcels = sorted((row for row in sources if row.record_type == "parcel"), key=lambda row: row.key)
    pending = [row for row in candidates if row.record_type == "parcel"]
    keys = {row.key for row in parcels}
    sections = []
    # The decision ledger uses level-two headings and bold Decision paragraphs.
    for match in re.finditer(r"^## ([^\r\n]+)\r?\n(.*?)(?=^## |\Z)", ledger, re.MULTILINE | re.DOTALL):
        title, body = match.groups()
        decision = re.search(r"\*\*Decision:\s*(.*?)\*\*", body, re.DOTALL)
        referenced = sorted(keys.intersection(re.findall(r"`([a-z][a-z0-9_]+)`", body)))
        sections.append({
            "jurisdiction": title.strip(),
            "recorded_decision": " ".join(decision.group(1).split()) if decision else None,
            "explicit_catalog_references": referenced,
            "reconciliation_status": "catalog_reference_found" if referenced else "manual_reconciliation_required",
            "next_action": "Revalidate admission and run bounded canary; measure imported records"
            if referenced else "Resolve the ledger entry to a configured source or create a gated candidate",
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Configuration and historical ledger only; no live requests or database counts",
        "configured_source_count": len(parcels),
        "candidate_count": len(pending),
        "measured_imported_parcels": None,
        "sources": [{
            "key": row.key, "jurisdiction": row.jurisdiction,
            "state": extract_state_code(row.jurisdiction, row.settings or {}),
            "configured_active": row.is_active,
            "adapter": row.adapter,
            "canonical_fields": sorted({item.canonical_field for item in row.field_mappings if item.is_active}),
            "export_policy": (row.settings or {}).get("export_policy"),
            "live_validation": "not_run", "imported_parcel_count": None,
        } for row in parcels],
        "candidates": [{"key": row.key, "status": row.status, "blocker": row.blocker_summary} for row in pending],
        "ledger_sections": sections,
        "warnings": [
            "A catalog reference does not validate current rights, freshness, complete geography, or import success.",
            "Unmatched ledger entries may use different source names; manual review is required before promotion.",
            "Nearby acquisition candidates are not verified for-sale listings.",
        ],
    }
