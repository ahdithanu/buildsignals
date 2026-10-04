"""Process due webhook deliveries for one organization."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.services.webhook_service import process_due_webhook_deliveries
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def _bounded_int(name: str, *, minimum: int, maximum: int):
    def _parse(value: str) -> int:
        parsed = int(value)
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    return _parse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, help="Organization UUID to process")
    parser.add_argument("--limit", type=_bounded_int("limit", minimum=1, maximum=250), default=25)
    parser.add_argument("--max-attempts", type=_bounded_int("max attempts", minimum=1, maximum=25), default=8)
    parser.add_argument("--timeout-seconds", type=_bounded_int("timeout seconds", minimum=1, maximum=60), default=10)
    args = parser.parse_args(argv)

    token = set_current_context(RequestContext(org_id=args.organization_id, user_id="webhook-worker"))
    db = SessionLocal()
    try:
        result = process_due_webhook_deliveries(
            db,
            organization_id=args.organization_id,
            limit=args.limit,
            max_attempts=args.max_attempts,
            timeout_seconds=args.timeout_seconds,
        )
    finally:
        db.close()
        reset_current_context(token)

    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
