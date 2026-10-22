"""Freeze and pin the inputs of a cutoff-safe replay into a verifiable manifest.

Everything that can change a replay result - the source snapshot, the frozen
cohort, the entity-id snapshots, the feature/normalization version, the
method/code versions, the predeclared thresholds, and the approved data scope -
is hashed here. ``verify()`` re-hashes the snapshot before a run and refuses to
proceed on any drift, so a mutated snapshot can never silently change results.

This module also contains the offline fixture loader. Replay only ever runs
against an isolated local snapshot that was built from checked-in fixtures (or
an explicitly approved local snapshot); there is no path to production data.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.temporal import TemporalEvent, TemporalObservation
from app.services.temporal_service import fingerprint, observation_series_key, utc

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Only these two scopes may ever run. Anything else is refused by ``freeze``.
APPROVED_DATA_SCOPES = ("local_fixture", "approved_local_snapshot")

# Relevant implementation bytes are verified before replay. They remain outside
# the signal reproducibility fingerprint, but any code drift requires a new
# freeze before the saved manifest may run again.
_PINNED_MODULES = ("driver.py", "manifest.py", "metrics.py", "run.py", "evaluate.py",
                   "dv_signal.py", "corpus_binding.py")
_PINNED_SERVICES = ("corpus_qualification.py", "temporal_service.py",
                    "activity_baseline.py", "development_velocity.py")


def _iso(value: datetime) -> str:
    return utc(value).isoformat()


@dataclass(frozen=True)
class SeriesSpec:
    """A frozen cohort under replay.

    ``series_keys`` names exactly which temporal series are in scope; the cohort
    is fixed in the manifest before the run, so it cannot drift between runs and
    cannot be re-selected from survivors at ``T`` (no survivorship leakage).
    """

    series_keys: tuple[str, ...]
    methodology_version: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict:
        return {
            "series_keys": sorted(self.series_keys),
            "methodology_version": self.methodology_version,
            "params": dict(self.params),
        }


def series_key_for(
    *, entity_id: str, source_id: str, external_record_id: str, attribute: str,
    methodology_version: str,
) -> str:
    """Resolve the temporal series key exactly as ``temporal_service`` does."""
    return observation_series_key(
        entity_id, source_id, external_record_id, attribute, methodology_version,
    )


# ── Offline fixture loader ──────────────────────────────────────────────────

@dataclass(frozen=True)
class LoadedFixture:
    series_keys: tuple[str, ...]
    methodology_version: str
    entity_id: str
    source_id: str
    attribute: str
    observation_ids: tuple[str, ...]


def _ensure_org(db: Session, org_id: str) -> None:
    if db.get(Organization, org_id) is None:
        db.add(Organization(id=org_id, name=org_id, slug=org_id))
        db.flush()


def load_rows(
    db: Session, rows: Sequence[Mapping[str, Any]], *, org_id: str = "default-org",
) -> LoadedFixture:
    """Insert fixture observation rows with deterministic, content-derived ids.

    Rows are inserted directly (not through ``record_observation``) so that
    ``recorded_at``/``first_observed_at`` and the row ids are fully controlled
    and a rebuilt snapshot is byte-identical. The append-only/immutability
    guarantees of the live store are unaffected: these are brand-new inserts.
    """
    if not rows:
        raise ValueError("Fixture is empty")
    _ensure_org(db, org_id)
    seen_sources: set[str] = set()
    seen_keys: set[str] = set()
    series_keys: list[str] = []
    observation_ids: list[str] = []
    methodology_version = ""
    entity_id = ""
    source_id = ""
    attribute = ""
    for row in rows:
        key = str(row["key"])
        if key in seen_keys:
            raise ValueError(f"Duplicate fixture row key: {key}")
        seen_keys.add(key)
        entity_id = str(row["entity_id"])
        source_key = str(row["source_key"])
        source_id = source_key
        external_record_id = str(row["external_record_id"])
        attribute = str(row["attribute"])
        methodology_version = str(row["methodology_version"])
        record_type = str(row.get("record_type", "filing"))
        source_type = str(row.get("source_type", record_type))
        received_at = utc(datetime.fromisoformat(row["first_observed_at"]))
        recorded_at = utc(datetime.fromisoformat(row["recorded_at"]))
        effective_at = (
            utc(datetime.fromisoformat(row["effective_at"]))
            if row.get("effective_at") is not None
            else None
        )
        value = row["value"]
        content_hash = fingerprint([key, value, external_record_id])

        if source_key not in seen_sources:
            seen_sources.add(source_key)
            if db.get(IngestionSource, source_id) is None:
                db.add(IngestionSource(
                    id=source_id, organization_id=org_id, key=source_key,
                    name=source_key, adapter="fixture", record_type=record_type,
                ))
                db.add(IngestionRun(
                    id=f"run-{source_key}"[:36], organization_id=org_id,
                    source_id=source_id, status="completed",
                ))
                db.flush()

        raw_id = f"raw-{key}"[:36]
        db.add(RawSourceRecord(
            id=raw_id, organization_id=org_id, source_id=source_id,
            run_id=f"run-{source_key}"[:36], external_record_id=external_record_id,
            record_type=record_type, content_hash=content_hash,
            payload={"value": value}, received_at=received_at,
        ))
        db.flush()

        sk = series_key_for(
            entity_id=entity_id, source_id=source_id,
            external_record_id=external_record_id, attribute=attribute,
            methodology_version=methodology_version,
        )
        if sk not in series_keys:
            series_keys.append(sk)
        obs_id = f"obs-{key}"[:36]
        observation_ids.append(obs_id)
        db.add(TemporalObservation(
            id=obs_id, organization_id=org_id, entity_id=entity_id,
            raw_source_record_id=raw_id, source_id=source_id,
            observation_key=fingerprint(key), series_key=sk, attribute=attribute,
            value=value, unit=row.get("unit"), effective_at=effective_at,
            first_observed_at=received_at, recorded_at=recorded_at,
            source_system=source_key, source_type=source_type,
            confidence=float(row.get("confidence", 1.0)),
            geography=row.get("geography"),
            methodology_version=methodology_version, content_hash=content_hash,
        ))
    db.flush()
    db.commit()
    return LoadedFixture(
        series_keys=tuple(series_keys), methodology_version=methodology_version,
        entity_id=entity_id, source_id=source_id, attribute=attribute,
        observation_ids=tuple(observation_ids),
    )


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_fixture(db: Session, path: str | Path, *, org_id: str = "default-org") -> LoadedFixture:
    """Load a checked-in ``.jsonl`` fixture into an isolated local snapshot."""
    return load_rows(db, _read_jsonl(Path(path)), org_id=org_id)


# ── Predeclared thresholds ──────────────────────────────────────────────────

def load_thresholds(path: str | Path) -> tuple[dict, str]:
    """Load the predeclared thresholds file and its content hash.

    The hash is pinned into the manifest, so any post-hoc edit changes the run
    identity and is detectable: thresholds cannot be chosen after seeing results.
    """
    data = json.loads(Path(path).read_text())
    return data, fingerprint(data)


# ── Snapshot / entity-mapping hashing ───────────────────────────────────────

def _cohort_observations(
    db: Session, series_keys: Sequence[str], *, org_id: str,
) -> list[TemporalObservation]:
    if not series_keys:
        return []
    return (
        db.query(TemporalObservation)
        .populate_existing()
        .filter(
            TemporalObservation.organization_id == org_id,
            TemporalObservation.series_key.in_(list(series_keys)),
        )
        .order_by(TemporalObservation.id.asc())
        .all()
    )


def _snapshot_payload(db: Session, series_keys: Sequence[str], *, org_id: str) -> dict:
    observations = _cohort_observations(db, series_keys, org_id=org_id)
    raw_ids = sorted({obs.raw_source_record_id for obs in observations})
    raws = (
        db.query(RawSourceRecord)
        .populate_existing()
        .filter(
            RawSourceRecord.organization_id == org_id,
            RawSourceRecord.id.in_(raw_ids),
        )
        .order_by(RawSourceRecord.id.asc())
        .all()
        if raw_ids else []
    )
    obs_ids = sorted(obs.id for obs in observations)
    events = (
        db.query(TemporalEvent)
        .populate_existing()
        .filter(
            TemporalEvent.organization_id == org_id,
            TemporalEvent.observation_id.in_(obs_ids),
        )
        .order_by(TemporalEvent.id.asc())
        .all()
        if obs_ids else []
    )
    return {
        "observations": sorted(
            [
                [
                    obs.id, obs.organization_id, obs.entity_id, obs.source_id,
                    obs.raw_source_record_id, obs.observation_key, obs.series_key, obs.attribute,
                    obs.source_type, obs.source_system, obs.source_url, obs.confidence,
                    obs.geography, _iso(obs.source_updated_at) if obs.source_updated_at else None,
                    obs.value, obs.unit,
                    _iso(obs.effective_at) if obs.effective_at else None,
                    _iso(obs.first_observed_at), _iso(obs.recorded_at),
                    obs.methodology_version, obs.content_hash,
                ]
                for obs in observations
            ],
            key=lambda item: item[0],
        ),
        "raw_records": sorted(
            [
                [raw.id, raw.organization_id, raw.source_id, raw.run_id,
                 raw.external_record_id, raw.record_type, raw.content_hash,
                 raw.payload, _iso(raw.received_at),
                 _iso(raw.source_updated_at) if raw.source_updated_at else None]
                for raw in raws
            ],
            key=lambda item: item[0],
        ),
        "events": sorted(
            [
                [
                    ev.id, ev.organization_id, ev.observation_id, ev.event_type,
                    _iso(ev.occurred_at) if ev.occurred_at else None,
                    _iso(ev.recorded_at),
                ]
                for ev in events
            ],
            key=lambda item: item[0],
        ),
    }


def _snapshot_id(db: Session, series_keys: Sequence[str], *, org_id: str) -> str:
    return fingerprint(_snapshot_payload(db, series_keys, org_id=org_id))


def _entity_mapping_id(db: Session, series_keys: Sequence[str], *, org_id: str) -> str:
    observations = _cohort_observations(db, series_keys, org_id=org_id)
    return fingerprint(sorted({obs.entity_id for obs in observations}))


def _module_hashes() -> dict[str, str]:
    here = Path(__file__).resolve().parent
    hashes: dict[str, str] = {}
    for name in _PINNED_MODULES:
        target = here / name
        if target.exists():
            hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    for name in _PINNED_SERVICES:
        target = ROOT / "app" / "services" / name
        hashes[f"app/services/{name}"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def _code_version() -> str:
    """Best-effort git rev read from .git files (never shells out)."""
    git_dir = ROOT / ".git"
    head = git_dir / "HEAD"
    try:
        content = head.read_text().strip()
    except OSError:
        return "unknown"
    if content.startswith("ref:"):
        ref = content.split(" ", 1)[1].strip()
        ref_path = git_dir / ref
        try:
            return ref_path.read_text().strip()
        except OSError:
            packed = git_dir / "packed-refs"
            try:
                for line in packed.read_text().splitlines():
                    if line.endswith(ref):
                        return line.split(" ", 1)[0].strip()
            except OSError:
                return "unknown"
            return "unknown"
    return content


# ── The manifest ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReplayManifest:
    run_id: str
    created_at: datetime
    method_id: str
    method_version: str
    code_version: str
    module_hashes: dict[str, str]
    snapshot_id: str
    series: SeriesSpec
    entity_mapping_id: str
    feature_version: str
    cutoffs: tuple[datetime, ...]
    thresholds_id: str
    data_scope: str
    reconstruction_guard: timedelta
    org_id: str = "default-org"

    def canonical(self) -> dict:
        """Result-determining pins only (provenance fields are excluded).

        ``created_at``/``code_version``/``module_hashes`` are deliberately left
        out so the reproducibility fingerprint tracks the *inputs that decide the
        result*, not the commit or the clock.
        """
        return {
            "method_id": self.method_id,
            "method_version": self.method_version,
            "snapshot_id": self.snapshot_id,
            "entity_mapping_id": self.entity_mapping_id,
            "feature_version": self.feature_version,
            "series": self.series.canonical(),
            "cutoffs": [_iso(cutoff) for cutoff in self.cutoffs],
            "data_scope": self.data_scope,
            "reconstruction_guard_seconds": self.reconstruction_guard.total_seconds(),
        }

    def to_json(self) -> dict:
        data = self.canonical()
        data.update(
            run_id=self.run_id,
            created_at=_iso(self.created_at),
            code_version=self.code_version,
            module_hashes=dict(self.module_hashes),
            thresholds_id=self.thresholds_id,
            org_id=self.org_id,
        )
        return data


def freeze(
    db: Session, *, method_id: str, method_version: str, series: SeriesSpec,
    cutoffs: Sequence[datetime], thresholds: Mapping[str, Any], data_scope: str,
    created_at: datetime | None = None,
    reconstruction_guard: timedelta = timedelta(days=1),
    org_id: str = "default-org",
) -> ReplayManifest:
    """Pin every result-determining input into an immutable manifest."""
    if data_scope not in APPROVED_DATA_SCOPES:
        raise ValueError(
            f"Refusing run: data_scope {data_scope!r} is not one of {APPROVED_DATA_SCOPES}",
        )
    ordered_cutoffs = _normalize_cutoffs(cutoffs)
    snapshot_id = _snapshot_id(db, series.series_keys, org_id=org_id)
    created = utc(created_at) if created_at is not None else datetime.now(timezone.utc)
    thresholds_id = fingerprint(dict(thresholds))
    return ReplayManifest(
        run_id=fingerprint([
            method_id, method_version, snapshot_id, thresholds_id,
            [_iso(cutoff) for cutoff in ordered_cutoffs], series.canonical(),
        ])[:16],
        created_at=created,
        method_id=method_id,
        method_version=method_version,
        code_version=_code_version(),
        module_hashes=_module_hashes(),
        snapshot_id=snapshot_id,
        series=series,
        entity_mapping_id=_entity_mapping_id(db, series.series_keys, org_id=org_id),
        feature_version=f"canonical-observation-v1:{series.methodology_version}",
        cutoffs=ordered_cutoffs,
        thresholds_id=thresholds_id,
        data_scope=data_scope,
        reconstruction_guard=reconstruction_guard,
        org_id=org_id,
    )


def verify(db: Session, manifest: ReplayManifest) -> None:
    """Re-hash the in-scope snapshot and raise on any drift."""
    if manifest.data_scope not in APPROVED_DATA_SCOPES:
        raise ValueError(f"Refusing run: data_scope {manifest.data_scope!r} is not approved")
    if manifest.module_hashes != _module_hashes():
        raise ValueError("Replay implementation drift detected since the manifest was frozen")
    current = _snapshot_id(db, manifest.series.series_keys, org_id=manifest.org_id)
    if current != manifest.snapshot_id:
        raise ValueError(
            "Snapshot drift detected: in-scope data changed since the manifest was frozen",
        )
    current_mapping = _entity_mapping_id(db, manifest.series.series_keys, org_id=manifest.org_id)
    if current_mapping != manifest.entity_mapping_id:
        raise ValueError("Entity-mapping drift detected since the manifest was frozen")


def _normalize_cutoffs(cutoffs: Sequence[datetime]) -> tuple[datetime, ...]:
    if not cutoffs:
        raise ValueError("At least one cutoff is required")
    normalized = []
    for cutoff in cutoffs:
        if cutoff.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        normalized.append(utc(cutoff))
    return tuple(sorted(set(normalized)))
