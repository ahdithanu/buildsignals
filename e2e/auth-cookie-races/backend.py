"""Loopback-only auth fixture. Never accepts a database URL or external target."""

import json
import os
import secrets
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    with TemporaryDirectory(prefix="buildsignals-auth-cookie-races-") as directory:
        # Override inherited production settings before importing any app module.
        os.environ.update({
            "DATABASE_URL": f"sqlite:///{directory}/auth.db",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENVIRONMENT": "development",
            "ALLOW_ANONYMOUS": "false",
            "REFRESH_COOKIE_NAME": "bs_local_auth_race",
            "REFRESH_COOKIE_SECURE": "false",
            "REFRESH_COOKIE_SAMESITE": "lax",
            "REGISTER_RATE_LIMIT": "10000",
            "LOGIN_RATE_LIMIT": "10000",
            "REFRESH_RATE_LIMIT": "10000",
            "SENTRY_DSN": "",
            "REDIS_URL": "",
            "RESEND_API_KEY": "",
        })

        import uvicorn
        from fastapi import Depends, FastAPI, HTTPException

        from app.db import engine, get_db, init_db
        from app.models.organization import Organization
        from app.models.organization_membership import MemberRole, OrganizationMembership
        from app.routes.auth import router
        from app.routes.organizations import switch_router
        from app.utils.auth_deps import get_current_user

        init_db()
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.include_router(switch_router, prefix="/v1")

        @app.post("/v1/probe-workspace")
        def workspace(principal: dict = Depends(get_current_user), db=Depends(get_db)):
            # Synthetic membership setup only; switch itself uses the real route.
            org = Organization(name="Synthetic second workspace", slug=secrets.token_hex(16))
            db.add(org)
            db.flush()
            db.add(OrganizationMembership(user_id=principal["user_id"], organization_id=org.id, role=MemberRole.editor))
            db.commit()
            return {"organization_id": org.id}

        @app.get("/v1/probe-expired-access")
        def expired_access():
            raise HTTPException(status_code=401, detail="Synthetic expired access response")

        @app.post("/v1/probe-expired-write")
        def expired_write():
            raise HTTPException(status_code=401, detail="Synthetic expired mutation response")

        @app.post("/v1/probe-write")
        def probe_write(principal: dict = Depends(get_current_user)):
            return {"email": principal["user"].email}

        @app.get("/v1/probe-identity")
        def probe_identity(principal: dict = Depends(get_current_user)):
            return {
                "email": principal["user"].email,
                "organization_id": principal["org_id"],
            }

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            print(json.dumps({"port": sock.getsockname()[1]}), flush=True)
            server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
            try:
                server.run(sockets=[sock])
            finally:
                engine.dispose()


if __name__ == "__main__":
    main()
