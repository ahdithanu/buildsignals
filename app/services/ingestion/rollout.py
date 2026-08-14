from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from app.schemas.ingestion import IngestionSourceCreate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.catalog import ROLLOUT_CLUSTERS, extract_state_code
from app.services.ingestion.host_policy import (
    audit_ingestion_hosts,
    candidate_host_policy_entries,
)
from app.services.ingestion.scheduling import source_shard

ROLLOUT_WAVE_LABELS = {
    1: "Texas, Washington, New York",
    2: "California, North Carolina, Florida",
    3: "Colorado, Massachusetts, Maryland",
    4: "Nationwide expansion queue",
}
DEFAULT_ROLLOUT_MANIFEST_PATH = Path(__file__).with_name("production_rollout.json")


@dataclass(frozen=True)
class RolloutShardManifest:
    shard_index: int
    source_count: int
    source_keys: list[str]


@dataclass(frozen=True)
class RolloutWaveManifest:
    wave: int
    label: str
    states: list[str]
    source_count: int
    permit_source_count: int
    parcel_source_count: int
    pre_approval_source_count: int
    approved_only_source_count: int
    manual_source_count: int
    required_hosts: list[str]
    source_keys: list[str]
    shards: list[RolloutShardManifest]


@dataclass(frozen=True)
class CandidateRetryManifest:
    candidate_catalog_fingerprint: str
    candidate_count: int
    candidate_keys: list[str]
    sample_size: int
    required_hosts: list[str]
    allowed_hosts_value: str
    policy_digest: str


@dataclass(frozen=True)
class ProductionRolloutManifest:
    schema_version: int
    catalog_fingerprint: str
    source_count: int
    state_count: int
    required_hosts: list[str]
    allowed_hosts_value: str
    policy_digest: str
    shard_count: int
    waves: list[RolloutWaveManifest]
    candidate_retries: CandidateRetryManifest
    manifest_digest: str


def source_rollout_wave(entry: IngestionSourceCreate) -> int:
    return ROLLOUT_CLUSTERS.get(_source_rollout_region(entry), (4, ""))[0]


def _source_rollout_region(entry: IngestionSourceCreate) -> str:
    settings = entry.settings or {}
    state = extract_state_code(entry.jurisdiction, settings)
    if state is not None:
        return state
    defaults = settings.get("defaults")
    values = [settings.get("state"), entry.jurisdiction]
    if isinstance(defaults, dict):
        values.append(defaults.get("state"))
    if any(
        isinstance(value, str)
        and value.strip().upper() in {"DC", "WASHINGTON, DC", "DISTRICT OF COLUMBIA"}
        for value in values
    ):
        return "DC"
    raise ValueError(f"Catalog source {entry.key} has no valid US state or district")


def scope_rollout_wave(
    entries: Iterable[IngestionSourceCreate],
    wave: int | None,
) -> list[IngestionSourceCreate]:
    if wave is not None and wave not in ROLLOUT_WAVE_LABELS:
        raise ValueError("rollout wave must be between 1 and 4")
    return [
        entry for entry in entries
        if wave is None or source_rollout_wave(entry) == wave
    ]


def build_production_rollout_manifest(
    entries: Iterable[IngestionSourceCreate],
    *,
    candidates: Iterable[IngestionSourceCandidate] = (),
    shard_count: int = 4,
) -> ProductionRolloutManifest:
    if shard_count < 1 or shard_count > 128:
        raise ValueError("shard_count must be between 1 and 128")
    entry_list = sorted(entries, key=lambda entry: entry.key)
    proposal = audit_ingestion_hosts(entry_list, allowed_hosts="")
    if proposal.unsafe_sources:
        raise ValueError("Production rollout contains unsafe source URLs")
    policy = audit_ingestion_hosts(
        entry_list,
        allowed_hosts=proposal.required_hosts,
    )
    waves: list[RolloutWaveManifest] = []
    for wave, label in ROLLOUT_WAVE_LABELS.items():
        wave_entries = scope_rollout_wave(entry_list, wave)
        wave_policy = audit_ingestion_hosts(
            wave_entries,
            allowed_hosts=proposal.required_hosts,
        )
        waves.append(RolloutWaveManifest(
            wave=wave,
            label=label,
            states=sorted({
                _source_rollout_region(entry)
                for entry in wave_entries
            }),
            source_count=len(wave_entries),
            permit_source_count=sum(entry.record_type == "permit" for entry in wave_entries),
            parcel_source_count=sum(entry.record_type == "parcel" for entry in wave_entries),
            pre_approval_source_count=sum(
                (entry.settings or {}).get("signal_stage") == "pre_approval_and_approved"
                for entry in wave_entries
            ),
            approved_only_source_count=sum(
                (entry.settings or {}).get("signal_stage") == "approved_only"
                for entry in wave_entries
            ),
            manual_source_count=sum(
                (entry.settings or {}).get("schedule_mode") == "manual"
                for entry in wave_entries
            ),
            required_hosts=sorted({
                requirement.host for requirement in wave_policy.requirements
            }),
            source_keys=[entry.key for entry in wave_entries],
            shards=[
                RolloutShardManifest(
                    shard_index=shard_index,
                    source_count=len(shard_entries),
                    source_keys=[entry.key for entry in shard_entries],
                )
                for shard_index in range(shard_count)
                if (shard_entries := [
                    entry for entry in wave_entries
                    if source_shard(entry.key, shard_count) == shard_index
                ])
            ],
        ))
    fingerprint_payload = [entry.model_dump(mode="json") for entry in entry_list]
    catalog_fingerprint = sha256(json.dumps(
        fingerprint_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()
    candidate_list = sorted(candidates, key=lambda candidate: candidate.key)
    runnable_candidates = [
        candidate for candidate in candidate_list if candidate.can_run_canary
    ]
    candidate_entries = candidate_host_policy_entries(runnable_candidates)
    candidate_proposal = audit_ingestion_hosts(candidate_entries, allowed_hosts="")
    if candidate_proposal.unsafe_sources:
        raise ValueError("Candidate rollout contains unsafe source URLs")
    candidate_policy = audit_ingestion_hosts(
        candidate_entries,
        allowed_hosts=candidate_proposal.required_hosts,
    )
    candidate_fingerprint = sha256(json.dumps(
        [candidate.model_dump(mode="json") for candidate in candidate_list],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()
    candidate_manifest = CandidateRetryManifest(
        candidate_catalog_fingerprint=candidate_fingerprint,
        candidate_count=len(runnable_candidates),
        candidate_keys=[candidate.key for candidate in runnable_candidates],
        sample_size=10,
        required_hosts=candidate_proposal.required_hosts,
        allowed_hosts_value=",".join(candidate_proposal.required_hosts),
        policy_digest=candidate_policy.policy_digest,
    )
    payload = {
        "schema_version": 1,
        "catalog_fingerprint": catalog_fingerprint,
        "source_count": len(entry_list),
        "state_count": len({
            _source_rollout_region(entry)
            for entry in entry_list
        }),
        "required_hosts": proposal.required_hosts,
        "allowed_hosts_value": ",".join(proposal.required_hosts),
        "policy_digest": policy.policy_digest,
        "shard_count": shard_count,
        "waves": waves,
        "candidate_retries": candidate_manifest,
    }
    manifest_digest = sha256(json.dumps(
        asdict(_ManifestPayload(**payload)),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()
    return ProductionRolloutManifest(
        **payload,
        manifest_digest=manifest_digest,
    )


@dataclass(frozen=True)
class _ManifestPayload:
    schema_version: int
    catalog_fingerprint: str
    source_count: int
    state_count: int
    required_hosts: list[str]
    allowed_hosts_value: str
    policy_digest: str
    shard_count: int
    waves: list[RolloutWaveManifest]
    candidate_retries: CandidateRetryManifest


def rollout_manifest_json(manifest: ProductionRolloutManifest) -> str:
    return json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"


def require_current_rollout_manifest(
    entries: Iterable[IngestionSourceCreate],
    *,
    candidates: Iterable[IngestionSourceCandidate] = (),
    path: Path = DEFAULT_ROLLOUT_MANIFEST_PATH,
) -> ProductionRolloutManifest:
    manifest = build_production_rollout_manifest(
        entries,
        candidates=candidates,
        shard_count=4,
    )
    if not path.exists() or path.read_text(encoding="utf-8") != rollout_manifest_json(
        manifest
    ):
        raise ValueError("Production rollout manifest is stale or missing")
    return manifest
