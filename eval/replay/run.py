"""CLI entry for the cutoff-safe replay harness (mirrors ``eval/bench.py``).

Offline and deterministic: it builds an isolated in-memory SQLite snapshot from
a checked-in fixture, freezes a manifest, replays the reference method twice, and
writes JSON-only outputs (manifest / signals / metrics / reproducibility). It
never reaches a network, a real database, or production data.

    python -m eval.replay.run --fixture eval/replay/fixtures/devvelocity_v0_known_then.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.db import Base  # noqa: E402
from eval.replay.driver import (  # noqa: E402
    REFERENCE_METHOD_ID,
    REFERENCE_METHOD_VERSION,
    BaselineRun,
    replay,
)
from eval.replay.manifest import (  # noqa: E402
    FIXTURES,
    SeriesSpec,
    freeze,
    load_fixture,
    load_thresholds,
)
from eval.replay.metrics import evaluate, reproducibility_check  # noqa: E402

DEFAULT_FIXTURE = FIXTURES / "devvelocity_v0_known_then.jsonl"
DEFAULT_THRESHOLDS = FIXTURES / "thresholds.devvelocity-v0.json"


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _default_cutoffs(fixture_rows_recorded: list[datetime]) -> list[datetime]:
    # One cutoff per distinct recorded_at, so every eligible interpretation is
    # exercised; the driver sorts and de-duplicates.
    return sorted(set(fixture_rows_recorded))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cutoff-safe replay harness")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--method-id", default=REFERENCE_METHOD_ID)
    parser.add_argument("--method-version", default=REFERENCE_METHOD_VERSION)
    parser.add_argument("--data-scope", default="local_fixture")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "replay_results")
    parser.add_argument(
        "--cutoff", action="append", default=[],
        help="ISO-8601 tz-aware cutoff; repeatable. Defaults to each fixture recorded_at.",
    )
    args = parser.parse_args(argv)

    db = _session()
    try:
        loaded = load_fixture(db, args.fixture)
        thresholds, _ = load_thresholds(args.thresholds)

        if args.cutoff:
            cutoffs = [datetime.fromisoformat(value) for value in args.cutoff]
        else:
            with args.fixture.open() as handle:
                recorded = [
                    datetime.fromisoformat(json.loads(line)["recorded_at"])
                    for line in handle
                    if line.strip()
                ]
            cutoffs = _default_cutoffs(recorded)

        series = SeriesSpec(
            series_keys=loaded.series_keys, methodology_version=loaded.methodology_version,
        )
        manifest = freeze(
            db, method_id=args.method_id, method_version=args.method_version,
            series=series, cutoffs=cutoffs, thresholds=thresholds,
            data_scope=args.data_scope,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        run = replay(
            db, method_id=args.method_id, method_version=args.method_version,
            cutoffs=cutoffs, series=series, manifest=manifest,
        )
        repro = replay(
            db, method_id=args.method_id, method_version=args.method_version,
            cutoffs=cutoffs, series=series, manifest=manifest,
        )
        baseline = BaselineRun(crossings=(), move=float(_baseline_move(thresholds)))
        metrics = evaluate(run, baseline=baseline, thresholds=thresholds, repro_run=repro)

        out_dir = args.out / manifest.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text(json.dumps(manifest.to_json(), sort_keys=True, indent=2))
        with (out_dir / "signals.jsonl").open("w") as handle:
            for signal in run.signals:
                handle.write(json.dumps(signal.canonical(), sort_keys=True) + "\n")
        (out_dir / "metrics.json").write_text(json.dumps(metrics, sort_keys=True, indent=2))
        (out_dir / "reproducibility.json").write_text(
            json.dumps(reproducibility_check(run, repro), sort_keys=True, indent=2),
        )
        print(f"run_id={manifest.run_id} run_fingerprint={run.run_fingerprint}")
        print(f"Wrote {out_dir}/manifest.json, signals.jsonl, metrics.json, reproducibility.json")
        return 0
    finally:
        db.close()


def _baseline_move(thresholds: dict) -> float:
    entry = thresholds.get("baseline_move")
    value = entry.get("value") if isinstance(entry, dict) else entry
    return value if isinstance(value, (int, float)) else 1.5


if __name__ == "__main__":
    raise SystemExit(main())
