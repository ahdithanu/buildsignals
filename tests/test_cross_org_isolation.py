"""Integration tests proving tenant isolation on deal-scoped routes.

Strategy: the default TestClient runs without a Bearer token, so every
request resolves to the default org ("default-org"). We insert one deal
belonging to "default-org" and one to "other-org" directly via the DB,
then hit the API and assert that:

- Deals in other-org look like 404, never like 200.
- Creating a Signal with a cross-org deal_id is rejected 404.
- Fetching/updating/deleting a cross-org Memo is rejected 404.

This protects against accidental un-scoped `db.query(...)` calls on
tenant tables (the vulnerability fixed in PR #3).
"""
from __future__ import annotations

from uuid import uuid4

from app.models.deal import Deal
from app.models.memo import Memo

OTHER_ORG = "other-org"


def _make_deal(db, org_id: str, name: str = "X") -> Deal:
    deal = Deal(
        id=str(uuid4()),
        name=name,
        organization_id=org_id,
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


def _make_memo(db, deal: Deal, org_id: str) -> Memo:
    memo = Memo(
        id=str(uuid4()),
        deal_id=deal.id,
        organization_id=org_id,
        title="t",
        content="c",
    )
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return memo


# ── Signals ────────────────────────────────────────────────────────────────


def test_list_deal_signals_cross_org_returns_404(client, db):
    other_deal = _make_deal(db, OTHER_ORG, "other-org deal")
    r = client.get(f"/deals/{other_deal.id}/signals")
    assert r.status_code == 404, r.text


def test_create_signal_cross_org_deal_returns_404(client, db):
    other_deal = _make_deal(db, OTHER_ORG, "other-org deal")
    r = client.post(
        "/signals",
        json={
            "deal_id": other_deal.id,
            "signal_type": "news",
            "description": "leak attempt",
        },
    )
    assert r.status_code == 404, r.text


# ── Memos ──────────────────────────────────────────────────────────────────


def test_get_memo_cross_org_returns_404(client, db):
    other_deal = _make_deal(db, OTHER_ORG, "other-org deal")
    _make_memo(db, other_deal, OTHER_ORG)
    r = client.get(f"/deals/{other_deal.id}/memo")
    assert r.status_code == 404, r.text


def test_update_memo_cross_org_returns_404(client, db):
    other_deal = _make_deal(db, OTHER_ORG, "other-org deal")
    _make_memo(db, other_deal, OTHER_ORG)
    r = client.put(
        f"/deals/{other_deal.id}/memo",
        json={"title": "pwned", "content": "pwned"},
    )
    assert r.status_code == 404, r.text


def test_delete_memo_cross_org_returns_404(client, db):
    other_deal = _make_deal(db, OTHER_ORG, "other-org deal")
    _make_memo(db, other_deal, OTHER_ORG)
    r = client.delete(f"/deals/{other_deal.id}/memo")
    assert r.status_code == 404, r.text


# ── Sanity: same-org still works ──────────────────────────────────────────


def test_same_org_deal_signals_ok(client, db):
    from app.utils.org_scope import DEFAULT_ORG_ID

    own_deal = _make_deal(db, DEFAULT_ORG_ID, "own deal")
    r = client.get(f"/deals/{own_deal.id}/signals")
    assert r.status_code == 200, r.text
    assert r.json() == []
