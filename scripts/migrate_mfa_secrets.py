"""Validate or atomically backfill/rotate MFA ciphertext; never print secrets."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402, F401
from app.db import SessionLocal  # noqa: E402
from app.services.mfa_secrets import reencrypt_secrets  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the validated encrypted rewrite")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            report = reencrypt_secrets(db, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            print("MFA validation/rewrite failed; transaction rolled back. Check schema, key ring and legacy data.", file=sys.stderr)
            return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
