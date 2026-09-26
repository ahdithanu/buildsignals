"""Verify isolation only on an explicitly acknowledged restored database copy."""
import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.recovery_verification import verify_restored_postgres  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-restored-copy", action="store_true", required=True)
    args = parser.parse_args()
    url = os.environ.get("RESTORE_DATABASE_URL")
    if not args.isolated_restored_copy or not url or url == os.environ.get("DATABASE_URL"):
        parser.error("Set RESTORE_DATABASE_URL to a separate restored copy; never the production database")
    engine = None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        report = verify_restored_postgres(engine)
    except Exception:
        print("Recovery isolation probe failed. Check the restored copy, role, migration and database logs. No connection details printed.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
