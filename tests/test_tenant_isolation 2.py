"""Cross-tenant isolation audit — the hard guarantee.

The earlier `test_cross_org_isolation.py` covered signals + memos via the
default-org fallback. This file is stricter: it spins up two real
authenticated orgs (admin tokens), seeds an entity tree under org A, then
hammers every cross-tenant route with org B's token and asserts 404.

If any of these tests ever go red, we have a row-level data leak — every
new route that touches a tenant table should pass these tests before merge.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.buy_box import BuyBox
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_distribution import DealDistribution
from app.models.document import Document
from app.models.memo import Memo
from app.models.outreach_activity import OutreachActivity
from app.models.signal import Signal
from app.services.rate_limiter import limiter

STRONG_PW = "CorrectHorseBattery42"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def _register(client, *, email, org_name):
    r = client.post("/auth/register", json={
        "email": email, "password": STRONG_PW,
        "full_name": email.split("@")[0].title(),
        "organization_name": org_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Seed helpers (write straight to the DB so we don't depend on the
# routes we're testing for setup) ─────────────────────────────────────────

def _seed_deal(db, org_id, name="Deal A") -> Deal:
    d = Deal(id=str(uuid4()), name=name, organization_id=org_id)
    db.add(d); db.commit(); db.refresh(d)
    return d


def _seed_contact(db, deal: Deal) -> Contact:
    c = Contact(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        name="A Contact",
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _seed_memo(db, deal: Deal) -> Memo:
    m = Memo(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        title="t", content="c",
    )
    db.add(m); db.commit(); db.refresh(m)
    return m


def _seed_document(db, deal: Deal) -> Document:
    d = Document(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        filename="ot.pdf",
        file_path="/tmp/ot.pdf",
        doc_type="pdf",
    )
    db.add(d); db.commit(); db.refresh(d)
    return d


def _seed_signal(db, deal: Deal) -> Signal:
    s = Signal(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        signal_type="news",
        description="leak",
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


def _seed_buybox(db, org_id) -> BuyBox:
    b = BuyBox(
        id=str(uuid4()),
        organization_id=org_id,
        asset_type="multifamily",
    )
    db.add(b); db.commit(); db.refresh(b)
    return b


def _seed_activity(db, deal: Deal) -> OutreachActivity:
    a = OutreachActivity(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        activity_type="email",
        subject="hi",
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _seed_distribution(db, deal: Deal) -> DealDistribution:
    d = DealDistribution(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
        recipient_name="X",
        recipient_email="x@y.com",
    )
    db.add(d); db.commit(); db.refresh(d)
    return d


def _seed_assumptions(db, deal: Deal) -> DealAssumptions:
    a = DealAssumptions(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=deal.organization_id,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


# ── Fixture: two registered orgs + a fully populated tree under A ─────────

@pytest.fixture
def two_orgs(client, db):
    a = _register(client, email="admin@acme.com", org_name="Acme")
    b = _register(client, email="admin@globex.com", org_name="Globex")
    deal_a = _seed_deal(db, a["organization_id"], name="A's Deal")
    contact_a = _seed_contact(db, deal_a)
    memo_a = _seed_memo(db, deal_a)
    document_a = _seed_document(db, deal_a)
    signal_a = _seed_signal(db, deal_a)
    buybox_a = _seed_buybox(db, a["organization_id"])
    activity_a = _seed_activity(db, deal_a)
    distribution_a = _seed_distribution(db, deal_a)
    _seed_assumptions(db, deal_a)
    return {
        "a": a, "b": b,
        "deal_a": deal_a,
        "contact_a": contact_a,
        "memo_a": memo_a,
        "document_a": document_a,
        "signal_a": signal_a,
        "buybox_a": buybox_a,
        "activity_a": activity_a,
        "distribution_a": distribution_a,
    }


# ──────────────────────────────────────────────────────────────────────────
# /deals — the most critical route. Direct CRUD must not leak.
# ──────────────────────────────────────────────────────────────────────────

class TestDealCrossOrg:
    def test_get_deal_returns_404(self, client, two_orgs):
        r = client.get(
            f"/deals/{two_orgs['deal_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 404

    def test_patch_deal_returns_404(self, client, two_orgs):
        r = client.patch(
            f"/deals/{two_orgs['deal_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
            json={"name": "PWNED"},
        )
        assert r.status_code == 404

    def test_delete_deal_returns_404(self, client, two_orgs):
        r = client.delete(
            f"/deals/{two_orgs['deal_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 404

    def test_list_deals_excludes_other_org(self, client, two_orgs):
        r = client.get(
            "/deals",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert two_orgs["deal_a"].id not in ids


# ──────────────────────────────────────────────────────────────────────────
# Deal-nested routes — every child resource path. These all 404 if the
# parent deal can't be resolved in the caller's org.
# ──────────────────────────────────────────────────────────────────────────

class TestNestedRoutesCrossOrg:
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("GET", "/deals/{id}/assumptions", None),
            ("PUT", "/deals/{id}/assumptions", {"purchase_price": 1}),
            ("GET", "/deals/{id}/outputs", None),
            ("POST", "/deals/{id}/recalculate", None),
            ("GET", "/deals/{id}/contacts", None),
            ("POST", "/deals/{id}/contacts", {"name": "X"}),
            ("GET", "/deals/{id}/activities", None),
            # ActivityCreate requires deal_id in body — pass org A's deal_id
            # so a cross-org caller can't sneak through path-vs-body confusion.
            ("POST", "/deals/{id}/activities", {"deal_id": "{id}", "activity_type": "email", "subject": "x"}),
            ("POST", "/deals/{id}/move-stage", {"stage": "sourced"}),
            ("GET", "/deals/{id}/documents", None),
            ("GET", "/deals/{id}/memo", None),
            ("POST", "/deals/{id}/generate-memo", None),
            ("PUT", "/deals/{id}/memo", {"title": "x", "content": "x"}),
            ("DELETE", "/deals/{id}/memo", None),
            ("POST", "/deals/{id}/send", {"recipient_name": "X", "recipient_email": "x@y.com"}),
            ("GET", "/deals/{id}/distributions", None),
            ("POST", "/deals/{id}/enrich", None),
            ("POST", "/deals/{id}/score", None),
            ("GET", "/deals/{id}/summary", None),
            ("GET", "/deals/{id}/signals", None),
            ("GET", "/deals/{id}/match-buy-boxes", None),
        ],
    )
    def test_cross_org_nested_route_returns_404(
        self, client, two_orgs, method, path, body,
    ):
        deal_id = two_orgs["deal_a"].id
        url = path.format(id=deal_id)
        kwargs = {"headers": _auth(two_orgs["b"]["access_token"])}
        if body is not None:
            # Substitute {id} placeholders in body values too (for routes
            # that take deal_id in both path and body, e.g. /activities).
            kwargs["json"] = {
                k: (v.format(id=deal_id) if isinstance(v, str) and "{id}" in v else v)
                for k, v in body.items()
            }
        r = client.request(method, url, **kwargs)
        # Anything other than 404 indicates the route resolved the cross-org
        # deal. 401/403 would be a different bug (auth/role) — surface those.
        assert r.status_code == 404, (
            f"{method} {url} returned {r.status_code} for cross-org caller: {r.text[:200]}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Routes that take a child entity ID directly (no deal in the path).
# ──────────────────────────────────────────────────────────────────────────

class TestChildEntityRoutesCrossOrg:
    def test_patch_contact_cross_org_404(self, client, two_orgs):
        r = client.patch(
            f"/contacts/{two_orgs['contact_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
            json={"name": "PWNED"},
        )
        assert r.status_code == 404

    def test_delete_contact_cross_org_404(self, client, two_orgs):
        r = client.delete(
            f"/contacts/{two_orgs['contact_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 404

    def test_delete_document_cross_org_404(self, client, two_orgs):
        r = client.delete(
            f"/documents/{two_orgs['document_a'].id}",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 404

    def test_create_signal_cross_org_deal_404(self, client, two_orgs):
        r = client.post(
            "/signals",
            headers=_auth(two_orgs["b"]["access_token"]),
            json={
                "deal_id": two_orgs["deal_a"].id,
                "signal_type": "news",
                "description": "leak",
            },
        )
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# Collection-style routes — they don't 404, but their results must
# exclude the other org's data.
# ──────────────────────────────────────────────────────────────────────────

class TestCollectionRoutesCrossOrg:
    def test_signals_list_excludes_other_org(self, client, two_orgs):
        r = client.get(
            "/signals",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert two_orgs["signal_a"].id not in ids

    def test_buy_box_list_excludes_other_org(self, client, two_orgs):
        r = client.get(
            "/buy-box",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert two_orgs["buybox_a"].id not in ids

    def test_follow_ups_excludes_other_org(self, client, two_orgs):
        r = client.get(
            "/outreach/follow-ups",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert two_orgs["activity_a"].id not in ids

    def test_dashboard_kpis_counts_only_own_org(self, client, two_orgs):
        r = client.get(
            "/dashboard/kpis",
            headers=_auth(two_orgs["b"]["access_token"]),
        )
        assert r.status_code == 200
        assert r.json()["total_deals"] == 0


# ──────────────────────────────────────────────────────────────────────────
# Sanity: same-org access still works for the deal we seeded.
# ──────────────────────────────────────────────────────────────────────────

class TestSameOrgStillWorks:
    def test_admin_a_can_read_own_deal(self, client, two_orgs):
        r = client.get(
            f"/deals/{two_orgs['deal_a'].id}",
            headers=_auth(two_orgs["a"]["access_token"]),
        )
        assert r.status_code == 200
        assert r.json()["id"] == two_orgs["deal_a"].id
