import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, event
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.audit_log import AuditLog
from app.models.buy_box import BuyBox
from app.models.organization_membership import MemberRole, OrganizationMembership
from tests.test_acquisition_criteria import CRITERIA
from tests.test_acquisition_screen_export import register


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Retirement tests must not call external sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)


@pytest.fixture
def owned_box(client):
    headers = register(client, "criteria-retire@example.com")
    response = client.post("/buy-box", headers=headers, json={
        "asset_type": "legacy office", "locations": "Austin TX",
        "min_price": 100, "max_price": 900, "min_irr": 0.12,
        "deal_type": "acquisition", "notes": "Preserve legacy notes",
        "acquisition_criteria": CRITERIA,
    })
    assert response.status_code == 201, response.text
    return headers, response.json()


def retire_url(box):
    return f"/buy-box/{box['id']}/retire"


def body(box):
    return {"expected_criteria": box["acquisition_criteria"]}


def audits(db, box):
    return db.query(AuditLog).filter_by(entity_type="buy_box", entity_id=box["id"]).all()


def assert_unchanged(db, box):
    db.expire_all()
    row = db.get(BuyBox, box["id"])
    assert row.acquisition_criteria == box["acquisition_criteria"]
    assert row.retired_at is None
    assert audits(db, box) == []


def test_retirement_preserves_every_other_field_and_audits_once(client, db, owned_box):
    headers, box = owned_box
    assert box["retired_at"] is None
    row = db.get(BuyBox, box["id"])
    before = {col.key: getattr(row, col.key) for col in BuyBox.__table__.columns}
    response = client.post(retire_url(box), headers=headers, json=body(box))
    assert response.status_code == 200, response.text
    retired = response.json()
    assert retired["retired_at"] is not None
    assert retired == box | {"retired_at": retired["retired_at"]}
    first_timestamp = datetime.fromisoformat(retired["retired_at"].replace("Z", "+00:00"))
    for _ in range(2):
        retry = client.post(retire_url(box), headers=headers, json=body(box))
        assert retry.status_code == 200, retry.text
        assert retry.json() == retired
    db.refresh(row)
    after = {col.key: getattr(row, col.key) for col in BuyBox.__table__.columns}
    assert after == before | {"retired_at": row.retired_at}
    audit, = audits(db, box)
    assert audit.action == "retire_acquisition_criteria"
    assert audit.organization_id == box["organization_id"]
    assert audit.actor_id == box["user_id"]
    assert json.loads(audit.old_values) == {"retired_at": None}
    logged = json.loads(audit.new_values)
    assert set(logged) == {"retired_at"}
    # SQLite drops timezone metadata; all retirement timestamps are written in UTC.
    assert datetime.fromisoformat(logged["retired_at"]) == first_timestamp.replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("role,status", [
    (MemberRole.admin, 200), (MemberRole.editor, 200), (MemberRole.viewer, 403),
])
def test_current_membership_controls_retirement(client, db, owned_box, role, status):
    headers, box = owned_box
    member = db.query(OrganizationMembership).filter_by(organization_id=box["organization_id"]).one()
    member.role = role
    db.commit()
    response = client.post(retire_url(box), headers=headers, json=body(box))
    assert response.status_code == status, response.text
    if status == 403:
        assert_unchanged(db, box)


def test_foreign_missing_and_unauthenticated_retirement(client, db, owned_box):
    headers, box = owned_box
    foreign = register(client, "retire-foreign@example.com")
    assert client.post(retire_url(box), headers=foreign, json=body(box)).status_code == 404
    assert client.post("/buy-box/missing/retire", headers=headers, json=body(box)).status_code == 404
    assert client.post(retire_url(box), json=body(box)).status_code == 401
    assert_unchanged(db, box)


def test_demo_retirement_is_read_only(client, db, owned_box, monkeypatch):
    from app import config
    from app.services.demo_access import DEMO_ORG_ID, DEMO_USER_ID
    from app.services.security import create_access_token

    _, box = owned_box
    monkeypatch.setattr(config, "DEMO_ENABLED", True)
    token = create_access_token(user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID, demo=True)
    response = client.post(retire_url(box), headers={"Authorization": f"Bearer {token}"}, json=body(box))
    assert response.status_code == 403, response.text
    assert "read-only" in response.json()["detail"]
    assert_unchanged(db, box)


@pytest.mark.parametrize("stored", [None, {}, {"profile": "invalid"}, CRITERIA | {"min_size": True}])
def test_legacy_and_invalid_stored_criteria_are_refused(client, db, owned_box, stored):
    headers, box = owned_box
    row = db.get(BuyBox, box["id"])
    row.acquisition_criteria = stored
    db.commit()
    response = client.post(retire_url(box), headers=headers, json=body(box))
    assert response.status_code == 422, response.text
    db.refresh(row)
    assert row.acquisition_criteria == stored
    assert row.retired_at is None
    assert audits(db, box) == []


@pytest.mark.parametrize("invalid", [
    None, {}, {"min_size": 15}, CRITERIA | {"min_size": True},
    CRITERIA | {"max_size": 1}, CRITERIA | {"min_price": 4000000},
    CRITERIA | {"max_price": "NaN"}, CRITERIA | {"market_city": "  "},
    CRITERIA | {"market_state": "oh"}, CRITERIA | {"version": 2},
    CRITERIA | {"min_year_built": "1980"}, CRITERIA | {"organization_id": "injected"},
])
def test_expected_criteria_are_fully_validated(client, db, owned_box, invalid):
    headers, box = owned_box
    response = client.post(retire_url(box), headers=headers, json={"expected_criteria": invalid})
    assert response.status_code == 422, response.text
    assert_unchanged(db, box)


@pytest.mark.parametrize("payload", [None, {}, [], {"acquisition_criteria": CRITERIA}])
def test_expected_criteria_body_is_required(client, db, owned_box, payload):
    headers, box = owned_box
    response = client.post(retire_url(box), headers=headers, json=payload)
    assert response.status_code == 422, response.text
    assert_unchanged(db, box)


@pytest.mark.parametrize("field,value", [
    ("id", "injected"), ("organization_id", "foreign"), ("user_id", "foreign"),
    ("created_at", "2000-01-01T00:00:00Z"), ("notes", "changed"),
    ("asset_type", "retail"), ("locations", "Cincinnati OH"), ("min_price", 1),
    ("max_price", 2), ("min_irr", 0.5), ("deal_type", "changed"),
    ("retired_at", "2000-01-01T00:00:00Z"), ("acquisition_criteria", CRITERIA),
])
def test_extra_retirement_fields_are_forbidden(client, db, owned_box, field, value):
    headers, box = owned_box
    response = client.post(retire_url(box), headers=headers, json=body(box) | {field: value})
    assert response.status_code == 422, response.text
    assert_unchanged(db, box)


@pytest.mark.parametrize("already_retired", [False, True])
def test_stale_criteria_conflict_even_on_retry(client, db, owned_box, already_retired):
    headers, box = owned_box
    if already_retired:
        assert client.post(retire_url(box), headers=headers, json=body(box)).status_code == 200
    response = client.post(retire_url(box), headers=headers, json={
        "expected_criteria": box["acquisition_criteria"] | {"max_size": 30},
    })
    assert response.status_code == 409, response.text
    db.expire_all()
    assert db.get(BuyBox, box["id"]).acquisition_criteria == box["acquisition_criteria"]
    assert len(audits(db, box)) == int(already_retired)


def test_expected_criteria_compare_validated_values(client, owned_box):
    headers, box = owned_box
    response = client.post(retire_url(box), headers=headers, json={
        "expected_criteria": CRITERIA | {"market_city": " Columbus "},
    })
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("change", ["criteria", "retirement"])
def test_cached_row_is_refreshed_under_requested_lock(client, db, owned_box, change):
    headers, box = owned_box
    cached = db.get(BuyBox, box["id"])
    with Session(db.get_bind()) as writer:
        row = writer.get(BuyBox, box["id"])
        if change == "criteria":
            row.acquisition_criteria = box["acquisition_criteria"] | {"max_size": 30}
        else:
            row.retired_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        writer.commit()
    observed = []

    def inspect_query(state):
        if state.is_select and any(mapper.class_ is BuyBox for mapper in state.all_mappers):
            observed.append(state.statement._for_update_arg is not None)

    def shared_db():
        yield db

    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = shared_db
    event.listen(db, "do_orm_execute", inspect_query)
    try:
        response = client.post(retire_url(box), headers=headers, json=body(box))
        assert response.status_code == (409 if change == "criteria" else 200), response.text
        assert observed[0] is True
        if change == "criteria":
            assert cached.acquisition_criteria["max_size"] == 30
            assert cached.retired_at is None
        else:
            assert response.json()["retired_at"].startswith("2026-01-01T00:00:00")
        assert audits(db, box) == []
    finally:
        event.remove(db, "do_orm_execute", inspect_query)
        app.dependency_overrides[get_db] = original


@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_retirement_and_audit_rollback_together(client, db, owned_box, monkeypatch, failure):
    from app.routes import buy_box as routes

    headers, box = owned_box
    original = routes.log_change

    def fail_after_audit(*args, **kwargs):
        original(*args, **kwargs)
        args[0].flush()
        raise RuntimeError("synthetic retirement failure")

    def fail_commit(session):
        if any(isinstance(row, AuditLog) and row.action == "retire_acquisition_criteria"
               for row in session.new):
            session.flush()
            raise RuntimeError("synthetic retirement failure")

    if failure == "audit":
        monkeypatch.setattr(routes, "log_change", fail_after_audit)
    else:
        event.listen(Session, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="synthetic retirement failure"):
            client.post(retire_url(box), headers=headers, json=body(box))
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail_commit)
    assert_unchanged(db, box)


def test_active_list_filters_before_pagination_and_history_is_scoped(client, db, owned_box):
    headers, box = owned_box
    others = []
    for index in range(3):
        payload = {} if index == 1 else {"acquisition_criteria": CRITERIA}
        response = client.post("/buy-box", headers=headers, json=payload)
        assert response.status_code == 201, response.text
        others.append(response.json())
    # Explicit distinct times avoid relying on SQLite timestamp precision.
    ordered = [box, *others]
    for index, item in enumerate(ordered):
        db.get(BuyBox, item["id"]).created_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    db.commit()
    for item in (ordered[1], ordered[3]):
        assert client.post(retire_url(item), headers=headers, json=body(item)).status_code == 200
    active = client.get("/buy-box", headers=headers)
    assert [item["id"] for item in active.json()] == [ordered[2]["id"], box["id"]]
    page = client.get("/buy-box", headers=headers, params={"skip": 1, "limit": 1})
    assert [item["id"] for item in page.json()] == [box["id"]]
    historical = client.get("/buy-box", headers=headers, params={"include_retired": True, "skip": 1, "limit": 2})
    assert [item["id"] for item in historical.json()] == [ordered[2]["id"], ordered[1]["id"]]
    assert historical.json()[1]["retired_at"] is not None
    member = db.query(OrganizationMembership).filter_by(organization_id=box["organization_id"]).one()
    member.role = MemberRole.viewer
    db.commit()
    assert len(client.get("/buy-box", headers=headers, params={"include_retired": True}).json()) == 4
    foreign = register(client, "retired-list-foreign@example.com")
    assert client.get("/buy-box", headers=foreign, params={"include_retired": True}).json() == []


def test_retirement_blocks_edit_screen_export_but_preserves_historical_bytes(client, db, owned_box, monkeypatch):
    from app.routes import buy_box as routes

    headers, box = owned_box
    created = client.post("/deals", headers=headers, json={
        "name": "Synthetic retirement", "city": "Columbus", "state": "OH",
        "units": 12, "asking_price": 2000000, "year_built": 1990,
    })
    assert created.status_code == 201, created.text
    base = f"/deals/{created.json()['id']}/acquisition-screen"
    params = {"buy_box_id": box["id"]}
    exported = client.post(base + "/export", headers=headers, params=params)
    assert exported.status_code == 200, exported.text
    snapshot_id = exported.headers["x-acquisition-snapshot-id"]
    history_before = client.get(base + "/history", headers=headers)
    audit_count = db.query(AuditLog).filter_by(action="acquisition_screen_export").count()
    assert client.post(retire_url(box), headers=headers, json=body(box)).status_code == 200
    screen = Mock(side_effect=AssertionError("Retired criteria must not be screened"))
    monkeypatch.setattr(routes, "screen_acquisition", screen)
    for response in (
        client.get(base, headers=headers, params=params),
        client.post(base + "/export", headers=headers, params=params),
        client.put(f"/buy-box/{box['id']}/acquisition-criteria", headers=headers, json={
            "expected_criteria": box["acquisition_criteria"],
            "acquisition_criteria": box["acquisition_criteria"] | {"max_size": 30},
        }),
    ):
        assert response.status_code == 409, response.text
    screen.assert_not_called()
    assert client.get(base + "/history", headers=headers).content == history_before.content
    downloaded = client.get(base + "/history/" + snapshot_id, headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == exported.content
    digest = hashlib.sha256(exported.content).hexdigest()
    db.expire_all()
    saved = db.get(AcquisitionScreenSnapshot, snapshot_id)
    assert saved.content.encode() == exported.content
    assert saved.content_sha256 == digest
    assert db.query(AcquisitionScreenSnapshot).count() == 1
    assert db.query(AuditLog).filter_by(action="acquisition_screen_export").count() == audit_count
    assert len(audits(db, box)) == 1
    assert db.get(BuyBox, box["id"]).acquisition_criteria == box["acquisition_criteria"]
    portable = client.get(f"/organizations/{box['organization_id']}/export", headers=headers)
    assert portable.status_code == 200, portable.text
    archived, = portable.json()["buy_boxes"]
    assert archived["id"] == box["id"]
    assert archived["retired_at"] is not None
    assert archived["acquisition_criteria"] == box["acquisition_criteria"]
    historical, = portable.json()["acquisition_screen_snapshots"]
    assert historical["content"].encode() == exported.content
    assert historical["content_sha256"] == digest


def test_list_keeps_existing_positional_parameters(client, owned_box):
    from app.routes.buy_box import list_buy_boxes
    from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

    _, box = owned_box
    session_gen = app.dependency_overrides[get_db]()
    session = next(session_gen)
    token = set_current_context(RequestContext(box["organization_id"], box["user_id"]))
    try:
        assert [item.id for item in list_buy_boxes(0, 50, session)] == [box["id"]]
    finally:
        reset_current_context(token)
        session_gen.close()


@pytest.mark.parametrize("export", [False, True])
def test_only_export_locks_and_both_refresh_cached_retirement(client, db, owned_box, export):
    headers, box = owned_box
    created = client.post("/deals", headers=headers, json={"name": "Synthetic serialization"})
    assert created.status_code == 201, created.text
    base = f"/deals/{created.json()['id']}/acquisition-screen"
    cached = db.get(BuyBox, box["id"])
    observed = []

    def inspect_query(state):
        if state.is_select and any(mapper.class_ is BuyBox for mapper in state.all_mappers):
            observed.append(state.statement._for_update_arg is not None)

    def shared_db():
        yield db

    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = shared_db
    event.listen(db, "do_orm_execute", inspect_query)
    request = client.post if export else client.get
    url = base + "/export" if export else base
    try:
        response = request(url, headers=headers, params={"buy_box_id": box["id"]})
        assert response.status_code == 200, response.text
        assert observed[0] is export
        if not export:
            assert observed == [False]
        db.rollback()
        # Keep a genuinely stale identity-map row while a separate transaction retires it.
        assert cached.retired_at is None
        with Session(db.get_bind()) as writer:
            row = writer.get(BuyBox, box["id"])
            row.retired_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            writer.commit()
        assert cached.retired_at is None
        rejected = request(url, headers=headers, params={"buy_box_id": box["id"]})
        assert rejected.status_code == 409, rejected.text
        assert cached.retired_at is not None
    finally:
        event.remove(db, "do_orm_execute", inspect_query)
        app.dependency_overrides[get_db] = original


def test_retirement_migration_is_nullable_additive_and_single_head(monkeypatch):
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["20261115_0001"]
    migration = scripts.get_revision("20261115_0001")
    assert migration.down_revision == "20260928_0008"
    add_column = Mock()
    drop_column = Mock()
    monkeypatch.setattr(migration.module.op, "add_column", add_column)
    monkeypatch.setattr(migration.module.op, "drop_column", drop_column)
    # Inspect operations only; no migration is applied to any database target.
    migration.module.upgrade()
    add_column.assert_called_once()
    table, column = add_column.call_args.args
    assert table == "buy_boxes"
    assert column.name == "retired_at"
    assert column.nullable is True
    assert isinstance(column.type, DateTime) and column.type.timezone is True
    assert column.default is None and column.server_default is None
    migration.module.downgrade()
    drop_column.assert_called_once_with("buy_boxes", "retired_at")
