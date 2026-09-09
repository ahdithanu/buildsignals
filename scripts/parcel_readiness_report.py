"""Generate an offline parcel backlog report without changing source admission."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ingestion.catalog import load_candidate_catalog, load_catalog  # noqa: E402
from app.services.ingestion.parcel_readiness import build_parcel_readiness  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_parcel_readiness(
        load_catalog(), load_candidate_catalog(),
        (ROOT / "docs/parcel_source_onboarding_decisions.md").read_text(),
    )
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
