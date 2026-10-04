"""Restricted-role demo API, RLS and read-only transaction integration."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import _set_rls_org, get_db
from app.main import app
from app.models.graph import GraphEntity, GraphEntityType
from app.models.organization import Organization
from app.services.demo_access import DEMO_ORG_ID, DEMO_USER_ID, demo_read_only
from app.services.demo_seed import seed_demo
from app.services.rate_limiter import limiter
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.demo_fixtures import create_snapshot

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires migrated, restricted-role local PostgreSQL")


def test_demo_postgres_api_rls_and_readonly(tmp_path, monkeypatch):
    engine = create_engine(URL)
    factory = sessionmaker(bind=engine)
    event.listen(factory, "after_begin", _set_rls_org)
    with engine.connect() as connection:
        role = connection.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert not role.rolsuper and not role.rolbypassrls
    snapshot = tmp_path / "snapshot.db"
    create_snapshot(snapshot)
    with factory() as db:
        seed_demo(db, [snapshot])
    other_org, other_entity = str(uuid4()), str(uuid4())
    context = set_current_context(RequestContext(other_org, "other-user"))
    try:
        with factory() as db:
            db.add(Organization(id=other_org, name="Other tenant", slug=other_org))
            db.flush()
            db.add(GraphEntity(id=other_entity, organization_id=other_org,
                               display_name="Secret", normalized_name="secret", entity_type=GraphEntityType.company))
            db.commit()
    finally:
        reset_current_context(context)

    def override():
        with factory() as db:
            yield db

    monkeypatch.setattr(config, "DEMO_ENABLED", True)
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.reset("demo:testclient")
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            response = client.post("/auth/demo")
            assert response.status_code == 200, response.text
            auth = {"Authorization": f"Bearer {response.json()['access_token']}"}
            assert client.get("/auth/me", headers=auth).status_code == 200
            permits = client.get("/ingestion/permits?limit=25", headers=auth)
            assert permits.status_code == 200 and len(permits.json()) == 1
            detail = client.get(f"/ingestion/permits/{permits.json()[0]['id']}", headers=auth)
            assert detail.status_code == 200 and detail.json()["graph_related"]
            assert client.get(f"/graph/entities/{other_entity}", headers=auth).status_code == 404
            assert client.post("/deals", headers=auth, json={}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)

    context = set_current_context(RequestContext(DEMO_ORG_ID, DEMO_USER_ID))
    read_only = demo_read_only.set(True)
    try:
        with factory() as db:
            # No application tenant filter: the real RLS policy must exclude it.
            assert db.execute(text("SELECT id FROM graph_entities WHERE id=:id"), {"id": other_entity}).first() is None
            assert db.execute(text("SHOW transaction_read_only")).scalar() == "on"
            with pytest.raises(DBAPIError) as error:
                db.execute(text("UPDATE organizations SET name=name WHERE id=:id"), {"id": DEMO_ORG_ID})
            assert error.value.orig.pgcode == "25006"
            db.rollback()
            assert db.execute(text("SHOW transaction_read_only")).scalar() == "on"
    finally:
        demo_read_only.reset(read_only)
        reset_current_context(context)
        engine.dispose()
