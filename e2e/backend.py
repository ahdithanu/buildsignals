"""Migrate and serve disposable browser-test data; never accept a database target."""
import base64
import json
import os
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
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
            "CORS_ALLOWED_ORIGINS": "http://localhost:8080",
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
        })
        import uvicorn
        from alembic.config import Config

        from alembic import command

        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(config, "head")
        from app.db import engine
        from app.main import app

        try:
            uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
