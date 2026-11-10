"""Migrate and serve disposable browser-test data; never accept a database target."""
import base64
import json
import os
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    api_port = int(os.environ.get("E2E_API_PORT") or "8000")
    web_port = int(os.environ.get("E2E_WEB_PORT") or "8080")
    if not all(1 <= port <= 65535 for port in (api_port, web_port)):
        raise ValueError("E2E_API_PORT and E2E_WEB_PORT must be valid TCP ports")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with TemporaryDirectory(prefix="buildsignals-browser-workflows-") as directory:
        # Override inherited service credentials before importing the application.
        os.environ.update({
            "DATABASE_URL": f"sqlite:///{directory}/workflows.db",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENVIRONMENT": "development",
            "ALLOW_ANONYMOUS": "false",
            "REFRESH_COOKIE_SECURE": "false",
            "REFRESH_COOKIE_SAMESITE": "lax",
            "REFRESH_COOKIE_NAME": "bs_local_workflow",
            "CORS_ALLOWED_ORIGINS": f"http://localhost:{web_port}",
            "REGISTER_RATE_LIMIT": "100000",
            "LOGIN_RATE_LIMIT": "100000",
            "REFRESH_RATE_LIMIT": "100000",
            "GLOBAL_RATE_LIMIT": "1000000",
            "MFA_ACTIVE_KEY_ID": "local-browser-test",
            "MFA_ENCRYPTION_KEYS": json.dumps({
                "local-browser-test": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            }),
            "MFA_ALLOW_LEGACY_PLAINTEXT": "false",
            "SENTRY_DSN": "",
            "RESEND_API_KEY": "",
            "REDIS_URL": "",
            "DEMO_ENABLED": "true",
        })
        import uvicorn
        from alembic.config import Config

        from alembic import command

        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(config, "head")
        from app.db import SessionLocal, engine
        from app.main import app
        from app.services.demo_seed import seed_demo
        from tests.demo_fixtures import create_snapshot

        snapshot_dir = os.environ.get("DEMO_TEST_SNAPSHOT_DIR")
        if snapshot_dir:
            snapshots = [Path(snapshot_dir) / f"columbus-{kind}-20240{month}-live.db"
                         for kind in ("commercial", "site") for month in (1, 2, 3)]
        else:
            snapshot = Path(directory) / "demo-snapshot.db"
            create_snapshot(snapshot)
            snapshots = [snapshot]
        with SessionLocal() as db:
            seed_demo(db, snapshots)

        try:
            uvicorn.run(app, host="127.0.0.1", port=api_port, log_level="warning")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
