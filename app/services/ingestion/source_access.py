"""Build actionable access requests for candidate ingestion sources."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.schemas.ingestion_candidate import IngestionSourceCandidate


@dataclass(frozen=True)
class SourceAccessContract:
    candidate_key: str
    source_name: str
    jurisdiction: str
    record_type: str
    current_status: str
    official_landing_page: str
    requested_delivery: tuple[str, ...]
    requested_fields: tuple[str, ...]
    lifecycle_requirements: tuple[str, ...]
    reconciliation_requirements: tuple[str, ...]
    rights_confirmation: tuple[str, ...]
    privacy_limits: tuple[str, ...]
    acceptance_checks: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_source_access_contract(
    candidate: IngestionSourceCandidate,
) -> SourceAccessContract:
    return SourceAccessContract(
        candidate_key=candidate.key,
        source_name=candidate.name,
        jurisdiction=candidate.jurisdiction,
        record_type=candidate.record_type,
        current_status=candidate.status,
        official_landing_page=candidate.official_landing_page,
        requested_delivery=(
            "A supported HTTPS API or recurring CSV/JSON delivery",
            "A complete historical backfill plus an ongoing incremental feed",
            "A published refresh schedule, support contact, and change-notice process",
        ),
        requested_fields=tuple(dict.fromkeys(candidate.candidate_source_fields)),
        lifecycle_requirements=(
            "Include records from initial submission through final disposition",
            "Include created, submitted, modified, status-change, issued, and completed dates when available",
            "Provide status definitions and identify which statuses are pre-approval, approved, denied, withdrawn, expired, or void",
        ),
        reconciliation_requirements=(
            "Provide a durable source record ID that survives edits and status changes",
            "Provide a monotonic modification cursor or reliable last-modified timestamp",
            "Represent deletions, merges, withdrawals, and replaced records",
            "Provide row counts or another control total for each delivery",
            "Document pagination, rate limits, timezone, schema, and null semantics",
        ),
        rights_confirmation=(
            "Commercial SaaS storage and automated processing",
            "Normalization, entity matching, scoring, and other derived analysis",
            "Customer display of source-backed facts and evidence links",
            "Customer API and export of value-added results",
            "Retention of historical versions for audit and provenance",
        ),
        privacy_limits=(
            "Exclude personal phone numbers, personal email addresses, signatures, credentials, and payment data",
            "Exclude plan sheets and attached documents unless separately approved",
            "Permit suppression of personal party data while retaining organization names and public record identifiers",
        ),
        acceptance_checks=(
            "A sample delivery validates against the documented schema",
            "Record IDs are unique at the documented grain",
            "Incremental delivery reconciles to an authoritative control total",
            "Pre-approval and approved records are both present when the source tracks them",
            "Written rights cover the requested production uses",
        ),
    )


def source_access_contract_markdown(contract: SourceAccessContract) -> str:
    sections = (
        ("Requested delivery", contract.requested_delivery),
        ("Requested fields", contract.requested_fields),
        ("Lifecycle requirements", contract.lifecycle_requirements),
        ("Reconciliation requirements", contract.reconciliation_requirements),
        ("Rights confirmation", contract.rights_confirmation),
        ("Privacy limits", contract.privacy_limits),
        ("Acceptance checks", contract.acceptance_checks),
    )
    lines = [
        f"# Source Access Request: {contract.source_name}",
        "",
        f"- Candidate key: `{contract.candidate_key}`",
        f"- Jurisdiction: {contract.jurisdiction}",
        f"- Record type: {contract.record_type}",
        f"- Current status: `{contract.current_status}`",
        f"- Official source: {contract.official_landing_page}",
    ]
    for heading, items in sections:
        lines.extend(("", f"## {heading}"))
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- No source-specific fields have been identified yet")
    lines.extend(("", "## Requested response", ""))
    lines.append(
        "Please confirm the supported delivery method, field dictionary, refresh cadence, "
        "historical coverage, technical contact, and the production rights listed above."
    )
    return "\n".join(lines) + "\n"


def source_access_contract_json(contract: SourceAccessContract) -> str:
    return json.dumps(contract.as_dict(), indent=2, sort_keys=True) + "\n"
