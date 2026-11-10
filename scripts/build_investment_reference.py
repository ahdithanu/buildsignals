"""Explicit one-shot six-file public capture for the annual-2025 release reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import investment_inputs, investment_reference
from app.services.investment_model import rank_metros


def build_reference(*, http_client=None, now=None) -> dict:
    """One get_snapshot capture, no retries, DB, models, overwrite, or timestamp rewrite."""
    target, manifest_path = investment_reference.REFERENCE_PATH, investment_reference.MANIFEST_PATH
    if target.exists() or manifest_path.exists():
        raise FileExistsError("Reference already exists; preserve the original capture")
    snapshot = (investment_inputs.get_snapshot() if http_client is None and now is None else
                investment_inputs.get_snapshot(http_client=http_client, now=now))
    payload = {"schema_version": investment_reference.SCHEMA_VERSION,
               "code_version": investment_reference.code_version(),
               "year": investment_reference.YEAR, "min_cohort": investment_reference.MIN_COHORT,
               "snapshot": snapshot}
    artifact = (json.dumps(payload, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()
    manifest = (json.dumps({"schema_version": investment_reference.SCHEMA_VERSION,
                           "artifact_filename": target.name,
                           "artifact_sha256": hashlib.sha256(artifact).hexdigest()},
                          sort_keys=True, indent=2) + "\n").encode()
    loaded = investment_reference.validate_reference_artifact(artifact, manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive writes preserve prior captures; an incomplete pair fails closed in the loader.
    with target.open("xb") as stream:
        stream.write(artifact)
    with manifest_path.open("xb") as stream:
        stream.write(manifest)
    return {"artifact_path": str(target), "manifest_path": str(manifest_path),
            "artifact_sha256": loaded["artifact_sha256"], "snapshot_id": loaded["snapshot_id"],
            "captured_at": loaded["captured_at"], "input_mode": loaded["input_mode"],
            "cohort_size": len(rank_metros(loaded)), "source_count": len(loaded["provenance"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-official", action="store_true", required=True,
                        help="Authorize one bounded capture of the six fixed official files")
    parser.parse_args()
    print(json.dumps(build_reference(), sort_keys=True))


if __name__ == "__main__":
    main()
