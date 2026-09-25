"""Persisted browser-family protocol, using real signed tokens and cookie values."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.config import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from app.models.browser_session import BrowserSession
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services.browser_sessions import validate_browser_claims
from app.services.rate_limiter import limiter
from app.services.security import create_access_token, decode_access_token

PASSWORD = "BrowserFamilyRegression42!"


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


class Browser:
    def __init__(self, client):
        self.client = client
        self.id, self.epoch = str(uuid4()), 0
        self.cookie, self.access = None, None

    def post(self, action, body=None, *, advance=True, headers=None):
        if advance:
            self.epoch += 1
        self.client.cookies.clear()
        if self.cookie:
            self.client.cookies.set(REFRESH_COOKIE_NAME, self.cookie, domain="testserver.local", path=REFRESH_COOKIE_PATH)
        protocol = {"X-Browser-Protocol": "1", "X-Browser-Id": self.id, "X-Browser-Epoch": str(self.epoch)}
        if self.access:
            protocol["Authorization"] = f"Bearer {self.access}"
        response = self.client.post(f"/v1/auth/{action}", json=body, headers={**protocol, **(headers or {})})
        self.cookie = self.client.cookies.get(REFRESH_COOKIE_NAME)
        if response.status_code in (200, 201) and action in ("register", "login", "refresh", "switch-org"):
            self.access = response.json()["access_token"]
        return response

    def register(self, name):
        self.email = f"{name}-{uuid4().hex}@example.com"
        result = self.post("register", {"email": self.email, "password": PASSWORD, "full_name": name})
        assert result.status_code == 201, result.text
        return result.json()

    def login(self, email=None):
        return self.post("login", {"email": email or self.email, "password": PASSWORD})

    def me(self, token=None):
        return self.client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token or self.access}"})


def test_tokens_are_bound_and_refresh_never_mutates_cookie(client, db):
    browser = Browser(client)
    account = browser.register("bound")
    claims = decode_access_token(browser.access)
    row = db.get(BrowserSession, claims["sid"])
    assert row.user_id == account["user_id"]
    assert row.organization_id == account["organization_id"]
    assert claims["bid"] == browser.id
    assert claims["sg"] == row.generation == 1
    cookie, token = browser.cookie, browser.access
    result = browser.post("refresh", advance=False)
    assert result.status_code == 200
    assert "set-cookie" not in result.headers
    assert browser.cookie == cookie and browser.access != token


def test_new_login_invalidates_old_access_and_late_refresh_cookie(client):
    browser = Browser(client)
    browser.register("superseded")
    old_cookie, old_access = browser.cookie, browser.access
    assert browser.login().status_code == 200
    assert browser.me(old_access).status_code == 401
    assert browser.me().status_code == 200
    browser.cookie = old_cookie  # Simulate an obsolete Set-Cookie arriving late.
    result = browser.post("refresh", advance=False)
    assert result.status_code == 401
    assert "set-cookie" not in result.headers


def test_logout_revokes_only_its_device_and_never_restores_from_cookie(client):
    first, second = Browser(client), Browser(client)
    first.register("devices")
    assert second.login(first.email).status_code == 200
    old_cookie, old_access = first.cookie, first.access
    result = first.post("logout")
    assert result.status_code == 204
    assert "set-cookie" not in result.headers
    assert first.me(old_access).status_code == 401
    assert second.me().status_code == 200
    first.cookie = old_cookie
    assert first.post("refresh", advance=False).status_code == 401
    assert second.post("refresh", advance=False).status_code == 200


def test_old_logout_cannot_revoke_new_login_even_with_new_cookie(client):
    browser = Browser(client)
    browser.register("queued-logout")
    old_access = browser.access
    assert browser.login().status_code == 200
    newer = browser.access
    result = browser.post("logout", headers={"Authorization": f"Bearer {old_access}"})
    assert result.status_code == 409
    assert "set-cookie" not in result.headers
    assert browser.me(newer).status_code == 200


def test_logout_with_missing_cookie_revokes_family_before_a_late_cookie_arrives(client):
    browser = Browser(client)
    browser.register("lost-cookie-logout")
    cookie, access = browser.cookie, browser.access
    browser.cookie = None
    result = browser.post("logout")
    assert result.status_code == 204
    assert "set-cookie" not in result.headers
    assert browser.me(access).status_code == 401
    browser.cookie = cookie
    # Even replaying its old public epoch cannot revive the logged-out family.
    result = browser.post("refresh", advance=False, headers={"X-Browser-Epoch": "1"})
    assert result.status_code == 401


def test_browser_metadata_without_signed_identity_cannot_revoke_family(client):
    browser = Browser(client)
    browser.register("unsigned-logout")
    browser.cookie = None
    result = browser.post("logout", headers={"Authorization": ""})
    assert result.status_code == 409
    assert "set-cookie" not in result.headers
    assert browser.me().status_code == 200


def test_stale_login_epoch_is_rejected_without_cookie_overwrite(client):
    browser = Browser(client)
    browser.register("old-login")
    assert browser.login().status_code == 200
    cookie = browser.cookie
    result = browser.post("login", {"email": browser.email, "password": PASSWORD},
                          headers={"X-Browser-Epoch": "1"})
    assert result.status_code == 409
    assert "set-cookie" not in result.headers
    assert browser.cookie == cookie


def test_missing_cookie_same_account_recovery_requires_password(client):
    browser = Browser(client)
    browser.register("recovery")
    old = browser.access
    browser.cookie = None
    assert browser.login().status_code == 200
    assert browser.me(old).status_code == 401


def test_forged_known_browser_id_cannot_replace_other_account_without_cookie(client):
    victim, attacker = Browser(client), Browser(client)
    victim.register("victim")
    attacker.register("attacker")
    attacker.id, attacker.epoch = victim.id, victim.epoch + 10
    attacker.cookie = None
    result = attacker.login()
    assert result.status_code == 409
    assert "set-cookie" not in result.headers
    assert victim.me().status_code == 200
    assert client.get("/v1/auth/me", headers={"X-Browser-Id": victim.id}).status_code == 401


def test_cookie_from_other_origin_family_is_not_accepted(client):
    origin_a, origin_b = Browser(client), Browser(client)
    origin_a.register("origin-a")
    origin_b.register("origin-b")
    origin_a.cookie = origin_b.cookie
    result = origin_a.post("refresh", advance=False)
    assert result.status_code == 401
    assert "set-cookie" not in result.headers
    assert origin_a.me().status_code == 200  # Its existing bearer still means A.


def test_logout_all_revokes_every_device_without_clearing_cookie(client):
    first, second = Browser(client), Browser(client)
    first.register("all-devices")
    assert second.login(first.email).status_code == 200
    result = first.post("logout-all")
    assert result.status_code == 204 and "set-cookie" not in result.headers
    assert first.me().status_code == second.me().status_code == 401
    assert second.post("refresh", advance=False).status_code == 401


@pytest.mark.parametrize("header,value", [("X-Browser-Protocol", ""), ("X-Browser-Id", "bad"),
                                           ("X-Browser-Epoch", "-1"), ("X-Browser-Epoch", "9007199254740992")])
def test_old_or_malformed_protocol_is_rejected(client, header, value):
    result = Browser(client).post("login", {"email": "unknown@example.com", "password": PASSWORD},
                                  headers={header: value})
    assert result.status_code == 426
    assert "set-cookie" not in result.headers


def test_family_claims_cannot_be_spliced_between_users_or_workspaces(client):
    first, second = Browser(client), Browser(client)
    a, b = first.register("splice-a"), second.register("splice-b")
    binding = {k: decode_access_token(first.access)[k] for k in ("sid", "sg", "bid", "be")}
    forged = create_access_token(user_id=b["user_id"], org_id=b["organization_id"], browser_session=binding)
    assert first.me(forged).status_code == 401
    assert a["organization_id"] != b["organization_id"]


def test_aware_database_expiry_preserves_timezone():
    claims = {"sid": "family", "sg": 1, "bid": "browser", "be": 1, "sub": "user", "org_id": "org"}
    row = SimpleNamespace(id="family", generation=1, browser_id="browser", client_epoch=1,
                          user_id="user", organization_id="org", revoked=False,
                          expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).astimezone(timezone(timedelta(hours=-8))))
    db = MagicMock()
    db.query.return_value.filter_by.return_value.populate_existing.return_value.first.return_value = row
    assert validate_browser_claims(db, claims) is row


def test_switch_workspace_rotates_family_and_rejects_stale_workspace(client, db):
    browser = Browser(client)
    account = browser.register("workspace")
    target = Organization(name="Synthetic second workspace", slug=f"workspace-{uuid4().hex}")
    db.add(target)
    db.flush()
    db.add(OrganizationMembership(user_id=account["user_id"], organization_id=target.id, role=MemberRole.viewer))
    db.commit()
    old_access, old_cookie = browser.access, browser.cookie
    before = decode_access_token(old_access)
    result = browser.post("switch-org", {"organization_id": target.id})
    assert result.status_code == 200, result.text
    after = decode_access_token(browser.access)
    assert after["sid"] == before["sid"]
    assert after["sg"] == before["sg"] + 1
    assert after["org_id"] == target.id
    assert result.json()["role"] == "viewer"
    assert "set-cookie" in result.headers
    assert browser.me(old_access).status_code == 401
    assert browser.me().json()["organization_id"] == target.id
    assert browser.post("refresh", advance=False).status_code == 200
    result = browser.post("switch-org", {"organization_id": account["organization_id"]},
                          headers={"Authorization": f"Bearer {old_access}"})
    assert result.status_code == 401
    assert "set-cookie" not in result.headers
    browser.cookie = old_cookie
    assert browser.post("refresh", advance=False).status_code == 401


def test_delete_account_never_clears_cookie_and_revokes_deleted_identity(client, db):
    browser, other = Browser(client), Browser(client)
    account = browser.register("deletable")
    second = other.register("remaining-admin")
    db.add(OrganizationMembership(user_id=second["user_id"], organization_id=account["organization_id"], role=MemberRole.admin))
    db.commit()
    result = client.post("/v1/auth/delete-account", json={"password": PASSWORD},
                            headers={"Authorization": f"Bearer {browser.access}"})
    assert result.status_code == 204, result.text
    assert "set-cookie" not in result.headers
    assert browser.me().status_code == 401
    assert browser.post("refresh", advance=False).status_code == 401
    assert other.me().status_code == 200


def test_cors_allows_browser_protocol_headers(client):
    from app.config import CORS_ALLOWED_ORIGINS

    response = client.options("/v1/auth/login", headers={
        "Origin": CORS_ALLOWED_ORIGINS[0], "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,x-browser-protocol,x-browser-id,x-browser-epoch",
    })
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-credentials"] == "true"
