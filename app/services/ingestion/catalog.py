from __future__ import annotations

import json
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.schemas.ingestion import IngestionSourceCreate, IngestionSourceUpdate
from app.services.ingestion.service import create_source, update_source
from app.utils.org_scope import active_query


DEFAULT_CATALOG_PATH = Path(__file__).with_name("catalog.json")
DEFAULT_CANDIDATE_CATALOG_PATH = Path(__file__).with_name("candidate_catalog.json")
_CATALOG_ADAPTER = TypeAdapter(list[IngestionSourceCreate])
_CANDIDATE_CATALOG_ADAPTER = TypeAdapter(list[IngestionSourceCandidate])
US_STATE_CODES = (
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
)
_STATE_BY_NAME = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "washington state": "WA",
}
_STATE_SUFFIX = re.compile(r",\s*([A-Z]{2})\s*$")


@dataclass(frozen=True)
class CoverageJurisdictionBucket:
    jurisdiction: str
    live_sources: int
    candidate_sources: int


@dataclass(frozen=True)
class StateCoverageBucket:
    state: str
    live_sources: int
    candidate_sources: int
    retailer_opening_sources: int
    pre_approval_sources: int
    approved_only_sources: int


@dataclass(frozen=True)
class RetailerOpeningCoverageSource:
    source_key: str
    source_name: str
    jurisdiction: str | None
    signal_stage: str | None
    official_landing_page: str | None


@dataclass(frozen=True)
class ApprovedOnlyCoverageSource:
    source_key: str
    source_name: str
    jurisdiction: str | None
    signal_stage: str | None
    official_landing_page: str | None


@dataclass(frozen=True)
class IngestionCoverageSummary:
    live_source_count: int
    candidate_count: int
    jurisdiction_count: int
    retailer_opening_source_count: int
    retailer_opening_sources: list[RetailerOpeningCoverageSource]
    approved_only_sources: list[ApprovedOnlyCoverageSource]
    pre_approval_source_count: int
    approved_only_source_count: int
    live_signal_stage_counts: dict[str, int]
    live_signal_sources_by_stage: dict[str, list[RetailerOpeningCoverageSource]]
    candidate_status_counts: dict[str, int]
    top_jurisdictions: list[CoverageJurisdictionBucket]
    state_buckets: list[StateCoverageBucket]
    activation_queue: list[StateCoverageBucket]
    candidate_only_state_count: int
    candidate_only_states: list[str]
    covered_state_count: int
    missing_state_count: int
    covered_states: list[str]
    missing_states: list[str]


@dataclass(frozen=True)
class CatalogSyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


def load_catalog(path: Path | str | None = None) -> list[IngestionSourceCreate]:
    catalog_path = Path(path) if path else DEFAULT_CATALOG_PATH
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = _CATALOG_ADAPTER.validate_python(payload)
    keys = [entry.key for entry in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"Duplicate ingestion catalog keys: {duplicates}")
    urls: dict[str, list[str]] = {}
    for entry in entries:
        normalized_url = entry.base_url.strip().rstrip("/").casefold()
        urls.setdefault(normalized_url, []).append(entry.key)
    duplicate_urls = {
        url: keys
        for url, keys in urls.items()
        if url and len(keys) > 1
    }
    if duplicate_urls:
        raise ValueError(f"Duplicate ingestion catalog base URLs: {duplicate_urls}")
    for entry in entries:
        settings = entry.settings or {}
        missing = [
            key for key in ("official_landing_page", "license", "reconciliation_mode")
            if not isinstance(settings.get(key), str) or not settings[key].strip()
        ]
        if missing:
            raise ValueError(
                f"Production catalog source {entry.key} is missing reviewed metadata: {missing}"
            )
        _validate_suppressed_fields(entry)
        _validate_field_allowlist(entry)
        _validate_freshness_metadata(entry)
        _validate_opening_signal_metadata(entry)
    return entries


def load_candidate_catalog(path: Path | str | None = None) -> list[IngestionSourceCandidate]:
    catalog_path = Path(path) if path else DEFAULT_CANDIDATE_CATALOG_PATH
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = _CANDIDATE_CATALOG_ADAPTER.validate_python(payload)
    keys = [entry.key for entry in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"Duplicate candidate catalog keys: {duplicates}")
    urls: dict[str, list[str]] = {}
    for entry in entries:
        normalized_url = entry.base_url.strip().rstrip("/").casefold()
        urls.setdefault(normalized_url, []).append(entry.key)
    duplicate_urls = {
        url: entry_keys for url, entry_keys in urls.items() if url and len(entry_keys) > 1
    }
    if duplicate_urls:
        raise ValueError(f"Duplicate candidate catalog base URLs: {duplicate_urls}")
    production_keys = {entry.key for entry in load_catalog()}
    overlap = sorted(production_keys & set(keys))
    if overlap:
        raise ValueError(
            f"Candidate catalog keys already exist in production catalog: {overlap}"
        )
    for entry in entries:
        if entry.next_audit_on < entry.last_checked_on:
            raise ValueError(
                f"Candidate catalog source {entry.key} next_audit_on cannot be earlier "
                "than last_checked_on"
            )
    return entries


def summarize_coverage(limit: int = 10) -> IngestionCoverageSummary:
    live_catalog = load_catalog()
    candidates = load_candidate_catalog()
    live_signal_stage_counts: dict[str, int] = {}
    live_signal_sources_by_stage: dict[str, list[RetailerOpeningCoverageSource]] = {}
    candidate_status_counts: dict[str, int] = {}
    jurisdictions: dict[str, dict[str, int]] = {}
    state_buckets: dict[str, dict[str, int]] = {}
    retailer_opening_sources: list[RetailerOpeningCoverageSource] = []
    approved_only_sources: list[ApprovedOnlyCoverageSource] = []
    covered_states: set[str] = set()
    retailer_opening_source_count = 0
    pre_approval_source_count = 0
    approved_only_source_count = 0

    for entry in live_catalog:
        stage = str((entry.settings or {}).get("signal_stage") or "unknown")
        live_signal_stage_counts[stage] = live_signal_stage_counts.get(stage, 0) + 1
        live_signal_sources_by_stage.setdefault(stage, []).append(
            RetailerOpeningCoverageSource(
                source_key=entry.key,
                source_name=entry.name,
                jurisdiction=entry.jurisdiction,
                signal_stage=stage,
                official_landing_page=(entry.settings or {}).get("official_landing_page") or (entry.settings or {}).get("source_url") or entry.base_url,
            )
        )
        if (entry.settings or {}).get("retailer_opening_signal"):
            retailer_opening_source_count += 1
            retailer_opening_sources.append(
                RetailerOpeningCoverageSource(
                    source_key=entry.key,
                    source_name=entry.name,
                    jurisdiction=entry.jurisdiction,
                    signal_stage=stage,
                    official_landing_page=(entry.settings or {}).get("official_landing_page") or (entry.settings or {}).get("source_url") or entry.base_url,
                )
            )
        if stage == "pre_approval_and_approved":
            pre_approval_source_count += 1
        elif stage == "approved_only":
            approved_only_source_count += 1
            approved_only_sources.append(
                ApprovedOnlyCoverageSource(
                    source_key=entry.key,
                    source_name=entry.name,
                    jurisdiction=entry.jurisdiction,
                    signal_stage=stage,
                    official_landing_page=(entry.settings or {}).get("official_landing_page") or (entry.settings or {}).get("source_url") or entry.base_url,
                )
            )
        jurisdiction = entry.jurisdiction or "Unknown"
        bucket = jurisdictions.setdefault(jurisdiction, {"live_sources": 0, "candidate_sources": 0})
        bucket["live_sources"] += 1
        state_code = extract_state_code(entry.jurisdiction, entry.settings or {})
        if state_code:
            covered_states.add(state_code)
            state_bucket = state_buckets.setdefault(
                state_code,
                {
                    "live_sources": 0,
                    "candidate_sources": 0,
                    "retailer_opening_sources": 0,
                    "pre_approval_sources": 0,
                    "approved_only_sources": 0,
                },
            )
            state_bucket["live_sources"] += 1
            if (entry.settings or {}).get("retailer_opening_signal"):
                state_bucket["retailer_opening_sources"] += 1
            if stage == "pre_approval_and_approved":
                state_bucket["pre_approval_sources"] += 1
            elif stage == "approved_only":
                state_bucket["approved_only_sources"] += 1

    for entry in candidates:
        candidate_status_counts[entry.status] = candidate_status_counts.get(entry.status, 0) + 1
        jurisdiction = entry.jurisdiction or "Unknown"
        bucket = jurisdictions.setdefault(jurisdiction, {"live_sources": 0, "candidate_sources": 0})
        bucket["candidate_sources"] += 1
        state_code = extract_state_code(entry.jurisdiction, entry.model_dump())
        if state_code:
            covered_states.add(state_code)
            state_bucket = state_buckets.setdefault(
                state_code,
                {
                    "live_sources": 0,
                    "candidate_sources": 0,
                    "retailer_opening_sources": 0,
                    "pre_approval_sources": 0,
                    "approved_only_sources": 0,
                },
            )
            state_bucket["candidate_sources"] += 1

    sorted_jurisdictions = sorted(
        jurisdictions.items(),
        key=lambda item: (item[1]["live_sources"] + item[1]["candidate_sources"], item[0]),
        reverse=True,
    )
    top_jurisdictions = [
        CoverageJurisdictionBucket(
            jurisdiction=jurisdiction,
            live_sources=bucket["live_sources"],
            candidate_sources=bucket["candidate_sources"],
        )
        for jurisdiction, bucket in sorted_jurisdictions[:limit]
    ]
    sorted_states = sorted(
        state_buckets.items(),
        key=lambda item: (
            item[1]["live_sources"] + item[1]["candidate_sources"],
            item[1]["retailer_opening_sources"],
            item[0],
        ),
        reverse=True,
    )
    state_buckets_list = [
        StateCoverageBucket(
            state=state,
            live_sources=bucket["live_sources"],
            candidate_sources=bucket["candidate_sources"],
            retailer_opening_sources=bucket["retailer_opening_sources"],
            pre_approval_sources=bucket["pre_approval_sources"],
            approved_only_sources=bucket["approved_only_sources"],
        )
        for state, bucket in sorted_states[:limit]
    ]
    candidate_only_states = [
        state
        for state, bucket in sorted_states
        if bucket["candidate_sources"] > 0 and bucket["live_sources"] == 0
    ]
    activation_queue = [
        StateCoverageBucket(
            state=state,
            live_sources=bucket["live_sources"],
            candidate_sources=bucket["candidate_sources"],
            retailer_opening_sources=bucket["retailer_opening_sources"],
            pre_approval_sources=bucket["pre_approval_sources"],
            approved_only_sources=bucket["approved_only_sources"],
        )
        for state, bucket in sorted_states
        if bucket["candidate_sources"] > 0 and bucket["live_sources"] == 0
    ]
    missing_states = [state for state in US_STATE_CODES if state not in covered_states]
    return IngestionCoverageSummary(
        live_source_count=len(live_catalog),
        candidate_count=len(candidates),
        jurisdiction_count=len(jurisdictions),
        retailer_opening_source_count=retailer_opening_source_count,
        retailer_opening_sources=retailer_opening_sources,
        approved_only_sources=approved_only_sources,
        pre_approval_source_count=pre_approval_source_count,
        approved_only_source_count=approved_only_source_count,
        live_signal_stage_counts=live_signal_stage_counts,
        live_signal_sources_by_stage=live_signal_sources_by_stage,
        candidate_status_counts=candidate_status_counts,
        top_jurisdictions=top_jurisdictions,
        state_buckets=state_buckets_list,
        activation_queue=activation_queue,
        candidate_only_state_count=len(activation_queue),
        candidate_only_states=candidate_only_states,
        covered_state_count=len(covered_states),
        missing_state_count=len(missing_states),
        covered_states=sorted(covered_states),
        missing_states=missing_states,
    )


def normalize_state_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) == 2 and normalized.upper() in US_STATE_CODES:
        return normalized.upper()
    lookup = _STATE_BY_NAME.get(normalized.casefold())
    if lookup:
        return lookup
    suffix = _STATE_SUFFIX.search(normalized.upper())
    if suffix and suffix.group(1) in US_STATE_CODES:
        return suffix.group(1)
    return None


def extract_state_code(jurisdiction: str | None, settings: dict[str, object]) -> str | None:
    candidates: list[str] = []
    state_setting = settings.get("state")
    if isinstance(state_setting, str):
        candidates.append(state_setting)
    defaults = settings.get("defaults")
    if isinstance(defaults, dict):
        default_state = defaults.get("state")
        if isinstance(default_state, str):
            candidates.append(default_state)
    if jurisdiction:
        candidates.append(jurisdiction)
    for value in candidates:
        normalized = value.strip()
        if not normalized:
            continue
        code = normalize_state_code(normalized)
        if code:
            return code
    return None


def _validate_suppressed_fields(entry: IngestionSourceCreate) -> None:
    settings = entry.settings or {}
    suppressed = settings.get("suppressed_fields")
    if not suppressed:
        return
    if not isinstance(suppressed, list) or not all(
        isinstance(field, str) for field in suppressed
    ):
        raise ValueError(f"Catalog source {entry.key} suppressed_fields must be a string list")
    suppressed_fields = {field.strip().casefold() for field in suppressed if field.strip()}
    connector = settings.get("connector") if isinstance(settings.get("connector"), dict) else {}
    out_fields = connector.get("out_fields")
    if isinstance(out_fields, str):
        if out_fields.strip() == "*":
            raise ValueError(
                f"Catalog source {entry.key} cannot fetch '*' while declaring suppressed_fields"
            )
        fetched_fields = {
            field.strip().casefold()
            for field in out_fields.split(",")
            if field.strip()
        }
        overlap = sorted(suppressed_fields & fetched_fields)
        if overlap:
            raise ValueError(
                f"Catalog source {entry.key} fetches suppressed fields: {overlap}"
            )
    mapped_fields = {mapping.source_field.strip().casefold() for mapping in entry.field_mappings}
    overlap = sorted(suppressed_fields & mapped_fields)
    if overlap:
        raise ValueError(
            f"Catalog source {entry.key} maps suppressed fields: {overlap}"
        )


def _validate_field_allowlist(entry: IngestionSourceCreate) -> None:
    settings = entry.settings or {}
    allowlist = settings.get("field_allowlist")
    if allowlist is None:
        return
    if not isinstance(allowlist, list) or not all(
        isinstance(field, str) for field in allowlist
    ):
        raise ValueError(f"Catalog source {entry.key} field_allowlist must be a string list")
    allowed_fields = {field.strip().casefold() for field in allowlist if field.strip()}
    if not allowed_fields:
        raise ValueError(f"Catalog source {entry.key} field_allowlist cannot be empty")

    suppressed = settings.get("suppressed_fields")
    if isinstance(suppressed, list):
        overlap = sorted(
            {field.strip().casefold() for field in suppressed if isinstance(field, str)}
            & allowed_fields
        )
        if overlap:
            raise ValueError(
                f"Catalog source {entry.key} allowlists suppressed fields: {overlap}"
            )

    fetched_fields = _explicit_fetched_fields(entry)
    if fetched_fields is not None:
        unexpected = sorted(fetched_fields - allowed_fields)
        if unexpected:
            raise ValueError(
                f"Catalog source {entry.key} fetches fields outside field_allowlist: "
                f"{unexpected}"
            )

    canary_fields = settings.get("canary_required_fields")
    if isinstance(canary_fields, list):
        unexpected_canary = sorted(
            field.strip().casefold()
            for field in canary_fields
            if isinstance(field, str)
            and field.strip()
            and field.strip().casefold() not in allowed_fields
        )
        if unexpected_canary:
            raise ValueError(
                f"Catalog source {entry.key} requires canary fields outside "
                f"field_allowlist: {unexpected_canary}"
            )


def _validate_freshness_metadata(entry: IngestionSourceCreate) -> None:
    settings = entry.settings or {}
    freshness_field = settings.get("freshness_field")
    candidate = settings.get("freshness_field_candidate")
    hold = settings.get("freshness_enforcement_hold")
    freshness_probe = settings.get("canary_freshness_probe")

    if freshness_probe is not None:
        if not isinstance(freshness_probe, dict):
            raise ValueError(
                f"Catalog source {entry.key} canary_freshness_probe must be an object"
            )
        if not isinstance(freshness_field, str) or not freshness_field.strip():
            raise ValueError(
                f"Catalog source {entry.key} canary_freshness_probe requires "
                "freshness_field"
            )
        probe_sample_size = freshness_probe.get("sample_size")
        if probe_sample_size is not None and (
            not isinstance(probe_sample_size, int)
            or isinstance(probe_sample_size, bool)
            or probe_sample_size < 1
            or probe_sample_size > 100
        ):
            raise ValueError(
                f"Catalog source {entry.key} canary_freshness_probe sample_size "
                "must be between 1 and 100"
            )
        probe_connector = freshness_probe.get("connector")
        if not isinstance(probe_connector, dict) or not probe_connector:
            raise ValueError(
                f"Catalog source {entry.key} canary_freshness_probe requires "
                "a connector object"
            )

    if candidate is not None:
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError(
                f"Catalog source {entry.key} freshness_field_candidate must be a non-empty string"
            )
        if freshness_field is not None:
            raise ValueError(
                f"Catalog source {entry.key} cannot declare both freshness_field and "
                "freshness_field_candidate"
            )
        if not isinstance(hold, str) or not hold.strip():
            raise ValueError(
                f"Catalog source {entry.key} freshness_field_candidate requires a "
                "freshness_enforcement_hold"
            )
        _validate_fetched_field(entry, candidate, "freshness_field_candidate")
        return

    if hold is not None:
        raise ValueError(
            f"Catalog source {entry.key} declares freshness_enforcement_hold without "
            "freshness_field_candidate"
        )

    if freshness_field is None:
        return
    if not isinstance(freshness_field, str) or not freshness_field.strip():
        raise ValueError(
            f"Catalog source {entry.key} freshness_field must be a non-empty string"
        )
    sla_hours = settings.get("freshness_sla_hours")
    if not isinstance(sla_hours, (int, float)) or sla_hours <= 0:
        raise ValueError(
            f"Catalog source {entry.key} freshness_field requires positive freshness_sla_hours"
        )
    _validate_fetched_field(entry, freshness_field, "freshness_field")


def _validate_opening_signal_metadata(entry: IngestionSourceCreate) -> None:
    settings = entry.settings or {}
    if settings.get("retailer_opening_signal") is not True:
        return

    if settings.get("signal_stage") != "approved_only":
        raise ValueError(
            f"Catalog source {entry.key} retailer_opening_signal sources must be "
            "approved_only"
        )

    opening_field = settings.get("opening_signal_date_field")
    if not isinstance(opening_field, str) or not opening_field.strip():
        raise ValueError(
            f"Catalog source {entry.key} retailer_opening_signal requires "
            "opening_signal_date_field"
        )
    _validate_fetched_field(entry, opening_field, "opening_signal_date_field")

    export_policy = settings.get("export_policy")
    if (
        not isinstance(export_policy, str)
        or "opening_context" not in export_policy.casefold()
        or "raw" not in export_policy.casefold()
    ):
        raise ValueError(
            f"Catalog source {entry.key} retailer_opening_signal requires an "
            "opening-context export policy with raw-source limits"
        )


def _validate_fetched_field(
    entry: IngestionSourceCreate,
    field_name: str,
    metadata_key: str,
) -> None:
    fetched_fields = _explicit_fetched_fields(entry)
    if fetched_fields is None:
        return
    normalized = field_name.strip().casefold()
    if normalized not in fetched_fields:
        raise ValueError(
            f"Catalog source {entry.key} {metadata_key} field {field_name!r} is not "
            "selected by the connector"
        )


def _explicit_fetched_fields(entry: IngestionSourceCreate) -> set[str] | None:
    settings = entry.settings or {}
    connector = settings.get("connector") if isinstance(settings.get("connector"), dict) else {}

    out_fields = connector.get("out_fields")
    if isinstance(out_fields, str) and out_fields.strip():
        if out_fields.strip() == "*":
            return None
        return {
            _normalize_selected_field(field)
            for field in out_fields.split(",")
            if _normalize_selected_field(field)
        }

    query = connector.get("query")
    if isinstance(query, dict):
        select = query.get("$select")
        if isinstance(select, str) and select.strip():
            if select.strip() == "*":
                return None
            return {
                _normalize_selected_field(field)
                for field in select.split(",")
                if _normalize_selected_field(field)
            }

    return None


def _normalize_selected_field(field: str) -> str:
    normalized = field.strip()
    if normalized.casefold().startswith("distinct "):
        normalized = normalized[9:].strip()
    return normalized.casefold()


def sync_catalog(
    db: Session,
    entries: Iterable[IngestionSourceCreate],
    *,
    dry_run: bool = False,
) -> CatalogSyncResult:
    created = updated = unchanged = 0
    for entry in entries:
        source = active_query(db.query(IngestionSource), IngestionSource).filter(
            IngestionSource.key == entry.key
        ).first()
        if source is None:
            created += 1
            if not dry_run:
                create_source(db, entry)
            continue

        if source.adapter != entry.adapter.lower() or source.record_type != entry.record_type:
            raise ValueError(
                f"Catalog cannot change adapter or record type for existing source: {entry.key}"
            )
        if _source_snapshot(source) == _payload_snapshot(entry):
            unchanged += 1
            continue

        updated += 1
        if not dry_run:
            update_source(
                db,
                source,
                IngestionSourceUpdate(
                    name=entry.name,
                    jurisdiction=entry.jurisdiction,
                    base_url=entry.base_url,
                    settings=entry.settings,
                    is_active=entry.is_active,
                    field_mappings=entry.field_mappings,
                ),
            )

    return CatalogSyncResult(created=created, updated=updated, unchanged=unchanged)


def _mapping_snapshot(mapping: object) -> dict:
    if hasattr(mapping, "model_dump"):
        return mapping.model_dump()
    return {
        "source_field": mapping.source_field,
        "canonical_field": mapping.canonical_field,
        "transform": mapping.transform,
        "transform_options": mapping.transform_options,
        "default_value": mapping.default_value,
        "is_required": mapping.is_required,
        "is_active": mapping.is_active,
    }


def _payload_snapshot(payload: IngestionSourceCreate) -> dict:
    return {
        "name": payload.name,
        "jurisdiction": payload.jurisdiction,
        "base_url": payload.base_url,
        "settings": payload.settings or None,
        "is_active": payload.is_active,
        "field_mappings": sorted(
            (_mapping_snapshot(mapping) for mapping in payload.field_mappings),
            key=lambda mapping: mapping["source_field"],
        ),
    }


def _source_snapshot(source: IngestionSource) -> dict:
    return {
        "name": source.name,
        "jurisdiction": source.jurisdiction,
        "base_url": source.base_url,
        "settings": source.settings or None,
        "is_active": source.is_active,
        "field_mappings": sorted(
            (_mapping_snapshot(mapping) for mapping in source.field_mappings),
            key=lambda mapping: mapping["source_field"],
        ),
    }
