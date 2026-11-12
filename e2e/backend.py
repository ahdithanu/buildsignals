"""Migrate and serve disposable browser-test data; never accept a database target."""
import base64
import json
import os
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OPERATOR_USER_ID = "11111111-1111-4111-8111-111111111111"
OPERATOR_ORG_ID = "22222222-2222-4222-8222-222222222222"
OPERATOR_SOURCE_ID = "33333333-3333-4333-8333-333333333333"
SF_VIEWER_ID = "44444444-4444-4444-8444-444444444444"
SF_ORG_ID = "55555555-5555-4555-8555-555555555555"
SF_SOURCE_ID = "66666666-6666-4666-8666-666666666666"
SF_PERMIT_ID = "88888888-8888-4888-8888-888888888888"


def _deny_external_sockets():
    import ipaddress
    import socket

    def loopback(host):
        if host in ("localhost", b"localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def audit(event, args):
        if event == "socket.getaddrinfo" and not loopback(args[0]):
            raise RuntimeError("External DNS is disabled in SF map E2E")
        if event == "socket.connect" and args[0].family in (socket.AF_INET, socket.AF_INET6):
            if not loopback(args[1][0]):
                raise RuntimeError("External connections are disabled in SF map E2E")

    sys.addaudithook(audit)


def _seed_sf_map_fixture(db):
    import hashlib
    from datetime import datetime, timezone

    from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
    from app.models.organization import Organization
    from app.models.organization_membership import MemberRole, OrganizationMembership
    from app.models.user import User
    from app.services.security import hash_password
    from app.services.sf_geocoding import SOURCE_KEY, SOURCE_URL, request_url, save_match
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

    db.add_all([
        Organization(id=SF_ORG_ID, name="SYNTHETIC SF map workspace", slug="synthetic-sf-map"),
        User(id=SF_VIEWER_ID, email="synthetic-sf-viewer@example.com",
             full_name="E2E Synthetic SF Viewer", password_hash=hash_password("E2eSfViewerOnly42!"),
             is_active=True, is_superuser=False),
    ])
    db.flush()
    source = IngestionSource(
        id=SF_SOURCE_ID, organization_id=SF_ORG_ID, key=SOURCE_KEY, base_url=SOURCE_URL,
        name="SYNTHETIC SF map source - no acquisition", adapter="socrata", record_type="permit",
        jurisdiction="San Francisco, CA", is_active=True,
        settings={"synthetic_e2e_fixture": True, "schedule_mode": "manual",
                  "collection_interval_minutes": 1440, "retry_interval_minutes": 360,
                  "collection_sla_hours": 24,
                  "schedule": {"enabled": False}, "canary_enabled": False},
    )
    db.add(source)
    db.add(OrganizationMembership(organization_id=SF_ORG_ID, user_id=SF_VIEWER_ID,
                                  role=MemberRole.viewer, is_default=True))
    db.flush()
    now = datetime.now(timezone.utc)
    run = IngestionRun(organization_id=SF_ORG_ID, source_id=source.id, status="completed",
                       trigger="manual", completed_at=now, records_seen=1, records_inserted=1,
                       parameters={"synthetic_e2e_fixture": True, "no_acquisition": True})
    db.add(run)
    db.flush()
    payload = {"fixture": "synthetic-sf-map", "record_id": "SYNTHETIC-SF-MAP-001"}
    raw = RawSourceRecord(
        id="77777777-7777-4777-8777-777777777777", organization_id=SF_ORG_ID,
        source_id=source.id, run_id=run.id, external_record_id="SYNTHETIC-SF-MAP-001",
        record_type="permit", content_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        payload=payload, received_at=now,
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        id=SF_PERMIT_ID, organization_id=SF_ORG_ID, source_id=source.id,
        latest_raw_record_id=raw.id, external_record_id="SYNTHETIC-SF-MAP-001",
        normalization_hash="e" * 64, project_name="SYNTHETIC SF map filing - not a real project",
        address="100 MARKET ST", city="San Francisco", state="CA", postal_code="94103",
        approval_stage="pre_approval", is_active=True, source_url="https://data.sf.gov/d/i98e-djp9",
    )
    db.add(permit)
    db.flush()
    response = {"result": {"addressMatches": [{
        "matchedAddress": "100 MARKET ST, SAN FRANCISCO, CA, 94103",
        "addressComponents": {"city": "SAN FRANCISCO", "state": "CA", "zip": "94103"},
        "coordinates": {"x": -122.4, "y": 37.79},
    }]}}
    token = set_current_context(RequestContext(SF_ORG_ID, SF_VIEWER_ID))
    try:
        if not save_match(db, permit, response, request_url(permit, source)):
            raise RuntimeError("Synthetic SF map fixture validation failed")
        if permit.latitude is not None or permit.longitude is not None:
            raise RuntimeError("Synthetic SF source coordinates must remain unknown")
        db.commit()
    finally:
        reset_current_context(token)


def main():
    sf_map_enabled = os.environ.get("RUN_SF_MAP_E2E") == "1"
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
            "OPENROUTER_API_KEY": "",
            "REDIS_URL": "",
            "SF_DERIVED_LOCATIONS_ENABLED": "true" if sf_map_enabled else "false",
            "DEMO_ENABLED": "true",
            "INTERNAL_OPERATIONS_USER_IDS": OPERATOR_USER_ID,
        })
        if sf_map_enabled:
            _deny_external_sockets()
        import uvicorn
        from alembic.config import Config

        from alembic import command

        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(config, "head")
        from app.db import SessionLocal, engine
        from app.main import app
        from app.models.ingestion import IngestionSource
        from app.models.organization import Organization
        from app.models.organization_membership import MemberRole, OrganizationMembership
        from app.models.user import User
        from app.services.demo_seed import seed_demo
        from app.services.security import hash_password
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
            db.add_all([
                Organization(id=OPERATOR_ORG_ID, name="SYNTHETIC E2E operator workspace",
                             slug="synthetic-e2e-operator"),
                User(id=OPERATOR_USER_ID, email="synthetic-operator@example.com",
                     full_name="E2E Synthetic Operator", password_hash=hash_password("E2eOperatorOnly42!"),
                     is_active=True, is_superuser=False),
            ])
            db.flush()
            db.add_all([
                OrganizationMembership(organization_id=OPERATOR_ORG_ID, user_id=OPERATOR_USER_ID,
                                       role=MemberRole.admin, is_default=True),
                IngestionSource(id=OPERATOR_SOURCE_ID, organization_id=OPERATOR_ORG_ID,
                                key="e2e_operator_synthetic_fixture",
                                name="SYNTHETIC E2E source fixture - no ingestion",
                                adapter="json_api", record_type="permit", is_active=False,
                                jurisdiction="Synthetic fixture only",
                                base_url="https://synthetic-e2e.invalid/never-fetch",
                                settings={"synthetic_e2e_fixture": True, "schedule": {"enabled": False}}),
            ])
            db.commit()
            if sf_map_enabled:
                _seed_sf_map_fixture(db)

        try:
            uvicorn.run(app, host="127.0.0.1", port=api_port, log_level="warning")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
