"""Dump the FastAPI OpenAPI schema to disk.

Run locally with `python scripts/export_openapi.py`. CI runs this on
every push to main and commits the resulting openapi.json so the
frontend can codegen types without booting the backend.

The env vars below are placeholder values used only during import.
app.config's fail-fast guards reject the dev SECRET_KEY / SQLite DB
in production, so we tag ENVIRONMENT=ci to skip those guards.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make `app.*` importable when the script is run from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("SECRET_KEY", "openapi-export-not-a-real-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./openapi-export.db")
os.environ.setdefault("ENVIRONMENT", "ci")

from app.main import app  # noqa: E402  (import after env setup)


def main() -> int:
    schema = app.openapi()
    out = Path(__file__).resolve().parent.parent / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
