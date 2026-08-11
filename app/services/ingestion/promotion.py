from __future__ import annotations

import fcntl
import hashlib
import json
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.catalog import (
    DEFAULT_CATALOG_PATH,
    PROMOTED_CATALOG_PATH,
    catalog_source_for_candidate,
    load_candidate_catalog,
    load_catalog,
    validate_catalog_entries,
)

_SOURCE_LIST_ADAPTER = TypeAdapter(list[IngestionSourceCreate])


class PromotionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    candidate_key: str = Field(min_length=1, max_length=120)
    decision: Literal["approved_for_production"]
    reviewed_by: str = Field(min_length=1, max_length=255)
    reviewed_on: date
    candidate_canary_completed_on: date
    rights_approved: Literal[True]
    data_minimization_approved: Literal[True]
    settings: dict[str, Any]
    field_mappings: list[FieldMappingCreate] = Field(min_length=1)


def load_promotion_review(path: Path | str) -> PromotionReview:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PromotionReview.model_validate(payload)


def build_promotion_entry(
    candidate: IngestionSourceCandidate,
    review: PromotionReview,
) -> IngestionSourceCreate:
    if review.candidate_key != candidate.key:
        raise ValueError(
            f"Promotion review candidate key {review.candidate_key} does not match "
            f"{candidate.key}"
        )
    if review.reviewed_on < review.candidate_canary_completed_on:
        raise ValueError("Promotion review cannot predate its candidate canary")
    if review.candidate_canary_completed_on < candidate.next_audit_on:
        raise ValueError(
            "Promotion review references a canary older than the candidate audit date"
        )
    if not candidate.can_run_canary:
        raise ValueError("Only runnable canary candidates can be prepared for promotion")

    required_policy_strings = ("rights_basis", "export_policy")
    missing_policy = [
        key
        for key in required_policy_strings
        if not isinstance(review.settings.get(key), str)
        or not review.settings[key].strip()
    ]
    allowlist = review.settings.get("field_allowlist")
    suppressed = review.settings.get("suppressed_fields")
    if missing_policy:
        raise ValueError(
            f"Promotion review is missing governance evidence: {missing_policy}"
        )
    if not isinstance(allowlist, list) or not allowlist or not all(
        isinstance(field, str) and field.strip() for field in allowlist
    ):
        raise ValueError("Promotion review requires a non-empty field_allowlist")
    if not isinstance(suppressed, list) or not all(
        isinstance(field, str) and field.strip() for field in suppressed
    ):
        raise ValueError("Promotion review requires a suppressed_fields decision")

    source_fields = [mapping.source_field for mapping in review.field_mappings]
    duplicates = sorted(
        {field for field in source_fields if source_fields.count(field) > 1}
    )
    if duplicates:
        raise ValueError(f"Promotion review contains duplicate source fields: {duplicates}")
    if not any(
        mapping.is_active
        and mapping.is_required
        and mapping.canonical_field == "source_record_id"
        for mapping in review.field_mappings
    ):
        raise ValueError(
            "Promotion review requires an active required source_record_id mapping"
        )

    settings = dict(review.settings)
    settings.update(
        {
            "candidate_key": candidate.key,
            "candidate_status": "approved_for_production",
            "candidate_canary_completed_on": review.candidate_canary_completed_on.isoformat(),
            "promotion_reviewed_by": review.reviewed_by,
            "promotion_reviewed_on": review.reviewed_on.isoformat(),
            "promotion_rights_approved": True,
            "promotion_data_minimization_approved": True,
        }
    )
    entry = IngestionSourceCreate(
        key=candidate.key,
        name=candidate.name,
        adapter=candidate.adapter,
        record_type=candidate.record_type,
        jurisdiction=candidate.jurisdiction,
        base_url=candidate.base_url,
        settings=settings,
        is_active=True,
        field_mappings=review.field_mappings,
    )
    catalog_source_for_candidate(candidate, [entry])
    return entry


def prepare_promotion_manifest(
    *,
    candidate_key: str,
    review_path: Path | str,
    output_path: Path | str,
    promoted_catalog_path: Path | str = PROMOTED_CATALOG_PATH,
    replace: bool = False,
) -> list[IngestionSourceCreate]:
    output = Path(output_path)
    with _promotion_lock(output):
        return _prepare_promotion_manifest_locked(
            candidate_key=candidate_key,
            review_path=review_path,
            output=output,
            promoted_catalog_path=Path(promoted_catalog_path),
            replace=replace,
        )


def _prepare_promotion_manifest_locked(
    *,
    candidate_key: str,
    review_path: Path | str,
    output: Path,
    promoted_catalog_path: Path,
    replace: bool,
) -> list[IngestionSourceCreate]:
    output_fingerprint = _file_fingerprint(output)
    candidate = next(
        (
            entry
            for entry in load_candidate_catalog(include_promoted=True)
            if entry.key == candidate_key
        ),
        None,
    )
    if candidate is None:
        raise ValueError(f"Ingestion candidate not found: {candidate_key}")

    review = load_promotion_review(review_path)
    new_entry = build_promotion_entry(candidate, review)
    promoted_path = promoted_catalog_path
    existing_payload = (
        json.loads(promoted_path.read_text(encoding="utf-8"))
        if promoted_path.exists()
        else []
    )
    existing = _SOURCE_LIST_ADAPTER.validate_python(existing_payload)
    existing_keys = [entry.key for entry in existing]
    duplicate_keys = sorted(
        {key for key in existing_keys if existing_keys.count(key) > 1}
    )
    if duplicate_keys:
        raise ValueError(f"Duplicate promoted catalog keys: {duplicate_keys}")
    existing_by_key = {entry.key: entry for entry in existing}
    base_catalog = load_catalog(DEFAULT_CATALOG_PATH)
    if candidate_key in {entry.key for entry in base_catalog}:
        raise ValueError(f"Base production catalog already contains {candidate_key}")
    current = existing_by_key.get(candidate_key)
    unchanged = current is not None and current.model_dump() == new_entry.model_dump()
    if current is not None and not unchanged and not replace:
        raise ValueError(
            f"Promoted catalog already contains {candidate_key}; use --replace to update it"
        )
    existing_by_key[candidate_key] = new_entry
    promoted = [existing_by_key[key] for key in sorted(existing_by_key)]

    validate_catalog_entries(
        [*base_catalog, *promoted],
        require_freshness_contract=True,
    )
    if unchanged and output.resolve() == promoted_path.resolve():
        return promoted
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        [entry.model_dump(mode="json", exclude_none=True) for entry in promoted],
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            temporary = Path(handle.name)
        if _file_fingerprint(output) != output_fingerprint:
            raise RuntimeError(
                f"Promotion manifest changed while preparing {candidate_key}; retry"
            )
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return promoted


def _file_fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _promotion_lock(output: Path):
    lock_key = hashlib.sha256(str(output.resolve()).encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"dealsignal-promotion-{lock_key}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
