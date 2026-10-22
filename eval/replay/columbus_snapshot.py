"""Read-only, offline replay/qualification receipt for a unified local archive.

This diagnostic does not extract outcomes or certify source coverage. Historical
cutoffs remain unavailable when their evidence was first captured later.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource
from app.models.temporal import TemporalObservation
from app.services.corpus_qualification import CorpusQualificationRequest
from app.services.temporal_service import utc
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)
from eval.replay import DV_METHOD_ID, DV_METHOD_VERSION, SeriesSpec, freeze, replay
from eval.replay.corpus_binding import produce_corpus_binding, verify_corpus_binding
from eval.replay.dv_signal import firing_threshold_value
from eval.replay.evaluate import evaluate_outcomes, load_protocol
from eval.replay.manifest import FIXTURES, load_thresholds
from scripts.columbus_corpus_capture import _file_hash


def _cutoffs(start: str, end: str, as_of: datetime) -> list[datetime]:
    cursor = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    finish = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    values = []
    while cursor < finish:
        cursor = cursor.replace(year=cursor.year + (cursor.month == 12), month=cursor.month % 12 + 1)
        values.append(cursor)
    return sorted({value for value in values if value <= as_of} | {as_of})


def run_snapshot(database: Path, output: Path, *, protocol_path: Path | None = None) -> dict:
    """Validate local artifact, freeze inputs, replay twice, and persist HOLD evidence."""
    database, output = Path(database).absolute(), Path(output).absolute()
    if database.is_symlink() or not database.is_file():
        raise ValueError("An existing local snapshot file is required")
    sidecar_path = database.with_suffix(".snapshot.json")
    if sidecar_path.is_symlink():
        raise ValueError("Symlink snapshot sidecar refused")
    sidecar = json.loads(sidecar_path.read_text())
    if (sidecar.get("method") != "columbus-local-evidence-snapshot-v0"
            or sidecar.get("database_sha256") != _file_hash(database)):
        raise ValueError("Snapshot database hash changed or sidecar method is unsupported")
    if len(sidecar.get("methodology_versions", [])) != 1:
        raise ValueError("Pin exactly one source observation methodology")
    if output.exists():
        raise FileExistsError("Choose a new diagnostic output directory")
    protocol = load_protocol(protocol_path or FIXTURES / "dv_v0_evaluation_protocol.json")
    thresholds, _ = load_thresholds(FIXTURES / "thresholds.devvelocity-v0.json")
    org_id, source_id = sidecar["organization_id"], sidecar["source_id"]
    method = sidecar["methodology_versions"][0]
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(
        database.resolve().as_uri() + "?mode=ro", uri=True))
    context = set_current_context(RequestContext(org_id, SYSTEM_USER_ID))
    try:
        with Session(engine) as db:
            source = db.get(IngestionSource, source_id)
            if (source is None or source.organization_id != org_id or source.is_active
                    or source.key != sidecar["source_key"]
                    or not source.settings.get("local_snapshot_import", {}).get("timestamp_preservation")):
                raise ValueError("Expected inactive local evidence-import source")
            observations = db.scalars(select(TemporalObservation).where(
                TemporalObservation.organization_id == org_id,
                TemporalObservation.source_id == source_id,
                TemporalObservation.methodology_version == method,
                TemporalObservation.attribute.in_(["permit.filed_at", "permit.approval_stage"]),
            )).all()
            if not observations:
                raise ValueError("Snapshot has no pinned observation cohort")
            as_of = max(utc(row.recorded_at) for row in observations)
            scope = source.settings["historical_qualification"]
            cutoffs = _cutoffs(scope["start_inclusive"], scope["end_exclusive"], as_of)
            baseline = {
                "sources": [{"source_id": source_id, "methodology_version": method}],
                "city": "Columbus", "state": "OH", "attribute": "permit.filed_at",
                "period_days": 30, "baseline_periods": 6, "reporting_lag_days": 7,
                "minimum_baseline_records": 20,
            }
            series = SeriesSpec(
                series_keys=tuple(sorted({row.series_key for row in observations})),
                methodology_version=method,
                params={"baseline": baseline, "minimum_populated_baseline_windows": 3,
                        "seasonal_adjustment": "off", "firing_threshold": firing_threshold_value(thresholds)},
            )
            manifest = freeze(
                db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION, series=series,
                cutoffs=cutoffs, thresholds={"signal_thresholds": thresholds, "evaluation_protocol": protocol},
                data_scope="approved_local_snapshot", created_at=as_of, org_id=org_id,
            )
            request = CorpusQualificationRequest(
                as_of=as_of, sources=baseline["sources"], city="Columbus", state="OH")
            binding = produce_corpus_binding(db, manifest=manifest, request=request, protocol=protocol)
            verification = verify_corpus_binding(db, manifest=manifest, protocol=protocol, receipt=binding)
            run = replay(db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION,
                         cutoffs=cutoffs, series=series, manifest=manifest)
            again = replay(db, method_id=DV_METHOD_ID, method_version=DV_METHOD_VERSION,
                           cutoffs=cutoffs, series=series, manifest=manifest)
            if run.run_fingerprint != again.run_fingerprint:
                raise ValueError("Repeated replay did not reproduce")
            metrics = evaluate_outcomes(run, outcomes={}, protocol=protocol,
                                        db=db, corpus_binding=binding)
            report = {
                "method": "columbus-snapshot-diagnostic-v1", "decision": "HOLD",
                "score_is_validated": False, "source_coverage_verified": False,
                "snapshot_id": manifest.snapshot_id, "run_fingerprint": run.run_fingerprint,
                "qualification_verdict": binding["qualification"]["verdict"],
                "binding_verified": verification["verified"],
                "binding_qualified": verification["qualified"], "binding_reason": verification["reason"],
                "observations": db.scalar(select(func.count()).select_from(TemporalObservation)),
                "cutoffs": len(cutoffs), "statuses": dict(Counter(s.status for s in run.signals)),
                "eligible_signal_cutoffs": sum(s.status in ("fired", "no_signal") for s in run.signals),
                "reproducible": True, "evaluation_verdict": metrics["verdict"]["verdict"],
                "limitations": ["Retrospective archive; original capture times preserved.",
                                "No independently accepted coverage attestation was supplied.",
                                "No outcomes extracted; v0 outcome timing and holdout contract remain unresolved.",
                                "This diagnostic can only HOLD; it does not certify validation."],
            }
            if _file_hash(database) != sidecar["database_sha256"]:
                raise ValueError("Snapshot database changed during the diagnostic")
            # Complete computation before publishing any result directory.
            output.mkdir(parents=True, exist_ok=False)
            artifacts = {"manifest.json": manifest.to_json(), "corpus-binding.json": binding,
                         "metrics.json": metrics}
            for name, value in artifacts.items():
                with (output / name).open("x") as stream:
                    json.dump(value, stream, indent=2)
                    stream.write("\n")
            with (output / "signals.jsonl").open("x") as stream:
                for signal in run.signals:
                    stream.write(json.dumps(signal.canonical()) + "\n")
            # A summary is the completion marker; never publish one before signals.
            with (output / "summary.json").open("x") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
            return report
    finally:
        reset_current_context(context)
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_snapshot(args.database, args.output), indent=2))


if __name__ == "__main__":
    main()
