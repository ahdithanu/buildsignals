"""Check a temporary SQLite recovery without modifying the source database."""
import argparse
import json
import sqlite3
import tempfile
from pathlib import Path


def verify_recovery(source: Path) -> dict:
    source = source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="buildsignals-recovery-") as directory:
        recovered = Path(directory) / "recovered.db"
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(recovered) as backup:
                original.backup(backup)
        with sqlite3.connect(recovered.as_uri() + "?mode=ro", uri=True) as restored:
            integrity = [row[0] for row in restored.execute("PRAGMA integrity_check")]
            errors = len(list(restored.execute("PRAGMA foreign_key_check")))
            names = {row[0] for row in restored.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "organizations", "audit_logs", "parcel_records",
                        "buildsignal_revisions", "buildsignal_reviews", "buildsignal_publications"}
            missing = sorted(required - names)
            counts = {name: restored.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                      for name in sorted(required & names)}
        return {"scope": "Local SQLite only; not production recovery verification",
                "passed": integrity == ["ok"] and not errors and not missing,
                "integrity": integrity, "foreign_key_errors": errors,
                "missing_tables": missing, "restored_counts": counts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    report = verify_recovery(parser.parse_args().source)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
