"""Verify isolation only on an explicitly acknowledged restored database copy."""
import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.recovery_verification import verify_restored_postgres  # noqa: E402


def _database_identity(value):
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or not url.host or not url.database:
        raise ValueError("An explicit PostgreSQL host and database are required")
    # libpq routing overrides make the authority insufficient to identify a target.
    if {key.lower() for key in url.query} & {"host", "hostaddr", "port", "dbname", "service"}:
        raise ValueError("Connection routing overrides are not supported")
    return (url.host.lower(), url.port or 5432, url.database)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-restored-copy", action="store_true", required=True)
    args = parser.parse_args()
    url = os.environ.get("RESTORE_DATABASE_URL")
    if not args.isolated_restored_copy or not url or url == os.environ.get("DATABASE_URL"):
        parser.error("Set RESTORE_DATABASE_URL to a separate restored copy; never the production database")
    try:
        target = _database_identity(url)
        source = os.environ.get("DATABASE_URL")
        if source and target == _database_identity(source):
            raise ValueError("Same database")
    except (ArgumentError, ValueError, TypeError):
        parser.error("Use an explicit PostgreSQL host/database distinct from DATABASE_URL; no routing overrides")
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
    return 0 if isinstance(report, dict) and report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
