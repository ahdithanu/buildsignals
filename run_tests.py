"""Self-contained test runner that doesn't need pytest CLI."""
from __future__ import annotations

import os
import sys
import uuid
import traceback

# Force test mode
os.environ["TESTING"] = "1"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User
from app.models.mixins import DEFAULT_ORG_ID


# ── Test data ──────────────────────────────────────────────────────────────

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"

SAMPLE_DEAL = {
    "name": "Test Deal", "address": "100 Main St", "city": "Austin", "state": "TX",
    "zip_code": "78701", "property_type": "office", "sq_ft": 50000,
    "year_built": 2015, "asking_price": 10000000,
}

SAMPLE_ASSUMPTIONS = {
    "purchase_price": 9500000, "closing_costs_pct": 0.02, "renovation_cost": 500000,
    "loan_amount": 6650000, "interest_rate": 0.06, "loan_term_years": 30,
    "gross_rental_income": 1200000, "vacancy_pct": 0.05, "opex_pct": 0.35,
    "cap_rate_market": 0.055, "exit_cap_rate": 0.06, "hold_period_years": 5,
    "rent_growth_pct": 0.03,
}

SAMPLE_CONTACT = {"name": "Jane Broker", "role": "Broker", "email": "j@test.com", "phone": "555-1234", "company": "TestCo"}


def make_client():
    """Create a fresh TestClient with isolated in-memory DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    # Seed required FK targets: default Organization and system User
    session.add(Organization(
        id=DEFAULT_ORG_ID, name="Default Organization",
        slug="default-org", is_active=True,
    ))
    session.add(User(
        id=SYSTEM_USER_ID, email="system@dealsignal.local",
        full_name="System", password_hash="!nologin",
        is_active=True, is_superuser=False,
    ))
    session.commit()

    def _override():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    return client, session


# ── Test functions ─────────────────────────────────────────────────────────

passed = 0
failed = 0
errors = []


def test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        global passed, failed
        client, db = make_client()
        try:
            fn(client, db)
            passed += 1
            print(f"  \033[32m✓\033[0m {name}")
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  \033[31m✗\033[0m {name} — {e}")
        except Exception as e:
            failed += 1
            errors.append((name, traceback.format_exc()))
            print(f"  \033[31m✗\033[0m {name} — {type(e).__name__}: {e}")
        finally:
            app.dependency_overrides.clear()
        return fn
    return decorator


# ──────────────────── DEAL TESTS ──────────────────────

print("\n=== DEALS ===")

@test("Create deal")
def _(c, db):
    r = c.post("/deals", json=SAMPLE_DEAL)
    assert r.status_code == 201, f"got {r.status_code}: {r.text[:200]}"
    assert r.json()["property_type"] == "Office"
    assert r.json()["status"] == "new"

@test("List deals")
def _(c, db):
    c.post("/deals", json=SAMPLE_DEAL)
    r = c.get("/deals")
    assert r.status_code == 200
    assert len(r.json()) >= 1

@test("Get deal detail")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.get(f"/deals/{did}")
    assert r.status_code == 200
    assert "assumptions" in r.json()
    assert "outputs" in r.json()
    assert "contacts_count" in r.json()

@test("Update deal")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.patch(f"/deals/{did}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"

@test("Get nonexistent deal → 404")
def _(c, db):
    assert c.get("/deals/fake-id").status_code == 404

@test("Soft-delete deal")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    assert c.delete(f"/deals/{did}").status_code == 204
    assert c.get(f"/deals/{did}").status_code == 404
    # Should not appear in list
    assert not any(d["id"] == did for d in c.get("/deals").json())

@test("Bulk import")
def _(c, db):
    r = c.post("/deals/import", json=[{**SAMPLE_DEAL, "name": "A"}, {**SAMPLE_DEAL, "name": "B"}])
    assert r.status_code == 201
    assert len(r.json()) == 2

# ──────────────────── NORMALIZATION ──────────────────────

print("\n=== NORMALIZATION ===")

@test("Property type: multi-family → Multifamily")
def _(c, db):
    r = c.post("/deals", json={**SAMPLE_DEAL, "property_type": "multi-family"})
    assert r.json()["property_type"] == "Multifamily"

@test("Property type: warehouse → Industrial")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.patch(f"/deals/{did}", json={"property_type": "warehouse"})
    assert r.json()["property_type"] == "Industrial"

@test("Signal type: price_reduction → Price Reduction")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post("/signals", json={"deal_id": did, "signal_type": "price_reduction", "source": "X", "description": "Y", "severity": 5.0})
    assert r.json()["signal_type"] == "Price Reduction"

@test("Signal type: tenant_risk → Tenant Risk")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post("/signals", json={"deal_id": did, "signal_type": "tenant_risk", "source": "X", "description": "Y", "severity": 5.0})
    assert r.json()["signal_type"] == "Tenant Risk"

# ──────────────────── ENRICHMENT + SCORING ──────────────────────

print("\n=== ENRICHMENT & SCORING ===")

@test("Enrich deal")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/enrich")
    assert r.status_code == 200

@test("Score deal (0-100)")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/enrich")
    r = c.post(f"/deals/{did}/score")
    assert r.status_code == 200
    assert 0 <= r.json()["score"] <= 100

# ──────────────────── UNDERWRITING ──────────────────────

print("\n=== UNDERWRITING ===")

@test("PUT assumptions")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.put(f"/deals/{did}/assumptions", json=SAMPLE_ASSUMPTIONS)
    assert r.status_code == 200
    assert r.json()["purchase_price"] == 9500000

@test("Recalculate outputs")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.put(f"/deals/{did}/assumptions", json=SAMPLE_ASSUMPTIONS)
    r = c.post(f"/deals/{did}/recalculate")
    assert r.status_code == 200

@test("NOI calculation correct")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.put(f"/deals/{did}/assumptions", json=SAMPLE_ASSUMPTIONS)
    c.post(f"/deals/{did}/recalculate")
    data = c.get(f"/deals/{did}/outputs").json()
    expected_noi = 1200000 * (1 - 0.05) * (1 - 0.35)
    assert abs(data["noi"] - expected_noi) < 1, f"NOI {data['noi']} != {expected_noi}"

# ──────────────────── CONTACTS ──────────────────────

print("\n=== CONTACTS ===")

@test("Create contact")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT)
    assert r.status_code == 201
    assert r.json()["name"] == "Jane Broker"

@test("List contacts")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT)
    r = c.get(f"/deals/{did}/contacts")
    assert r.status_code == 200
    assert len(r.json()) >= 1

@test("Update contact status")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    r = c.patch(f"/contacts/{cid}", json={"status": "contacted"})
    assert r.json()["status"] == "contacted"

@test("Soft-delete contact")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    assert c.delete(f"/contacts/{cid}").status_code == 204

@test("Business rule: contact qualified → deal auto-advances")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    assert c.get(f"/deals/{did}").json()["status"] == "new"
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    c.patch(f"/contacts/{cid}", json={"status": "qualified"})
    assert c.get(f"/deals/{did}").json()["status"] == "qualified"

@test("Qualified contact doesn't regress advanced deal")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/move-stage", json={"stage": "qualified"})
    c.post(f"/deals/{did}/move-stage", json={"stage": "underwriting"})
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    c.patch(f"/contacts/{cid}", json={"status": "qualified"})
    assert c.get(f"/deals/{did}").json()["status"] == "underwriting"

# ──────────────────── PIPELINE ──────────────────────

print("\n=== PIPELINE ===")

@test("Move stage forward")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/move-stage", json={"stage": "qualified"})
    assert r.status_code == 200
    assert c.get(f"/deals/{did}").json()["status"] == "qualified"

@test("Move through all stages")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    for s in ["qualified", "underwriting", "ic_review", "loi_sent", "closed"]:
        assert c.post(f"/deals/{did}/move-stage", json={"stage": s}).status_code == 200
    assert c.get(f"/deals/{did}").json()["status"] == "closed"

@test("Cannot move backward → 400")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/move-stage", json={"stage": "underwriting"})
    r = c.post(f"/deals/{did}/move-stage", json={"stage": "new"})
    assert r.status_code == 400, f"expected 400, got {r.status_code}"

@test("Can move to dead from any stage")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    assert c.post(f"/deals/{did}/move-stage", json={"stage": "dead"}).status_code == 200

@test("Invalid stage → 422")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    assert c.post(f"/deals/{did}/move-stage", json={"stage": "bogus"}).status_code == 422

# ──────────────────── ACTIVITIES ──────────────────────

print("\n=== ACTIVITIES ===")

@test("Create activity")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    r = c.post(f"/deals/{did}/activities", json={"contact_id": cid, "activity_type": "email", "subject": "Hi"})
    assert r.status_code == 201

@test("List activities")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    cid = c.post(f"/deals/{did}/contacts", json=SAMPLE_CONTACT).json()["id"]
    c.post(f"/deals/{did}/activities", json={"contact_id": cid, "activity_type": "call", "subject": "Call"})
    assert len(c.get(f"/deals/{did}/activities").json()) >= 1

@test("Follow-ups endpoint")
def _(c, db):
    assert c.get("/outreach/follow-ups").status_code == 200

# ──────────────────── SIGNALS ──────────────────────

print("\n=== SIGNALS ===")

@test("Create signal")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post("/signals", json={"deal_id": did, "signal_type": "market", "source": "X", "description": "Y", "severity": 5.0})
    assert r.status_code == 201

@test("List signals")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post("/signals", json={"deal_id": did, "signal_type": "market", "source": "X", "description": "Y", "severity": 5.0})
    assert len(c.get("/signals").json()) >= 1

@test("Deal signals")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post("/signals", json={"deal_id": did, "signal_type": "market", "source": "X", "description": "Y", "severity": 5.0})
    assert len(c.get(f"/deals/{did}/signals").json()) >= 1

# ──────────────────── DOCUMENTS ──────────────────────

print("\n=== DOCUMENTS ===")

@test("Create document")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/documents", json={"filename": "test.pdf", "file_type": "pdf", "file_size": 1024})
    assert r.status_code == 201

@test("List documents")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/documents", json={"filename": "t.pdf", "file_type": "pdf", "file_size": 512})
    assert len(c.get(f"/deals/{did}/documents").json()) >= 1

@test("Soft-delete document")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    doc_id = c.post(f"/deals/{did}/documents", json={"filename": "del.pdf", "file_type": "pdf", "file_size": 256}).json()["id"]
    assert c.delete(f"/documents/{doc_id}").status_code == 204

# ──────────────────── MEMOS ──────────────────────

print("\n=== MEMOS ===")

@test("Generate memo")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/generate-memo")
    assert r.status_code == 201
    assert len(r.json()["content"]) > 0

@test("Get memo")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/generate-memo")
    assert c.get(f"/deals/{did}/memo").status_code == 200

@test("Update memo")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/generate-memo")
    r = c.put(f"/deals/{did}/memo", json={"title": "Custom", "content": "# Custom"})
    assert r.json()["title"] == "Custom"

@test("Get memo 404 when none")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    assert c.get(f"/deals/{did}/memo").status_code == 404

@test("Soft-delete memo")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/generate-memo")
    assert c.delete(f"/deals/{did}/memo").status_code == 204
    assert c.get(f"/deals/{did}/memo").status_code == 404

# ──────────────────── DASHBOARD ──────────────────────

print("\n=== DASHBOARD ===")

@test("GET /dashboard/kpis")
def _(c, db):
    c.post("/deals", json=SAMPLE_DEAL)
    r = c.get("/dashboard/kpis")
    assert r.status_code == 200
    assert r.json()["total_deals"] >= 1

@test("GET /dashboard/top-opportunities")
def _(c, db):
    assert c.get("/dashboard/top-opportunities").status_code == 200

@test("GET /dashboard/pipeline-snapshot")
def _(c, db):
    c.post("/deals", json=SAMPLE_DEAL)
    r = c.get("/dashboard/pipeline-snapshot")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@test("GET /dashboard/recent-signals")
def _(c, db):
    assert c.get("/dashboard/recent-signals").status_code == 200

@test("GET /dashboard/ai-insights")
def _(c, db):
    assert c.get("/dashboard/ai-insights").status_code == 200

# ──────────────────── AUDIT LOGGING ──────────────────────

print("\n=== AUDIT LOGGING ===")

@test("Deal create logged")
def _(c, db):
    c.post("/deals", json=SAMPLE_DEAL)
    logs = db.query(AuditLog).filter(AuditLog.action == "create").all()
    assert len(logs) >= 1

@test("Deal update logged")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.patch(f"/deals/{did}", json={"name": "Renamed"})
    logs = db.query(AuditLog).filter(AuditLog.action == "update").all()
    assert len(logs) >= 1

@test("Stage change logged")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/move-stage", json={"stage": "qualified"})
    logs = db.query(AuditLog).filter(AuditLog.action == "stage_change").all()
    assert len(logs) >= 1

@test("Soft delete logged")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.delete(f"/deals/{did}")
    logs = db.query(AuditLog).filter(AuditLog.action == "soft_delete").all()
    assert len(logs) >= 1

# ──────────────────── BUY BOX ──────────────────────

print("\n=== BUY BOX ===")

@test("Create buy box")
def _(c, db):
    r = c.post("/buy-box", json={"asset_type": "Office", "locations": "Austin TX, Dallas TX", "min_price": 5000000, "max_price": 50000000, "min_irr": 0.12})
    assert r.status_code == 201
    assert r.json()["asset_type"] == "Office"
    assert r.json()["locations"] == "Austin TX, Dallas TX"

@test("List buy boxes")
def _(c, db):
    c.post("/buy-box", json={"asset_type": "Office"})
    c.post("/buy-box", json={"asset_type": "Industrial"})
    r = c.get("/buy-box")
    assert r.status_code == 200
    assert len(r.json()) == 2

@test("Match deal to buy boxes")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post("/buy-box", json={"asset_type": "Office", "locations": "Austin TX", "min_price": 1000000, "max_price": 20000000})
    c.post("/buy-box", json={"asset_type": "Industrial", "locations": "Chicago IL"})
    r = c.get(f"/deals/{did}/match-buy-boxes")
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert len(matches) == 2
    # Office + Austin should rank higher
    assert matches[0]["match_score"] >= matches[1]["match_score"]

@test("Match returns 404 for bad deal")
def _(c, db):
    assert c.get("/deals/fake-id/match-buy-boxes").status_code == 404

# ──────────────────── DISTRIBUTIONS ──────────────────────

print("\n=== DISTRIBUTIONS ===")

@test("Send deal (log distribution)")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.post(f"/deals/{did}/send", json={"recipient_name": "John Doe", "recipient_email": "john@example.com", "notes": "Initial send"})
    assert r.status_code == 201
    assert r.json()["recipient_email"] == "john@example.com"
    assert r.json()["status"] == "logged"

@test("List distributions")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    c.post(f"/deals/{did}/send", json={"recipient_name": "A", "recipient_email": "a@x.com"})
    c.post(f"/deals/{did}/send", json={"recipient_name": "B", "recipient_email": "b@x.com"})
    r = c.get(f"/deals/{did}/distributions")
    assert r.status_code == 200
    assert len(r.json()) == 2

@test("Send to nonexistent deal → 404")
def _(c, db):
    r = c.post("/deals/fake-id/send", json={"recipient_name": "X", "recipient_email": "x@x.com"})
    assert r.status_code == 404

# ──────────────────── DEAL SUMMARY ──────────────────────

print("\n=== DEAL SUMMARY ===")

@test("Get deal summary")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.get(f"/deals/{did}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test Deal"
    assert "metrics" in body
    assert "risks" in body
    assert "upside" in body
    assert "overview" in body

@test("Summary includes asking price metric")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    body = c.get(f"/deals/{did}/summary").json()
    assert "Asking Price" in body["metrics"]

@test("Summary 404 for bad deal")
def _(c, db):
    assert c.get("/deals/fake-id/summary").status_code == 404

# ──────────────────── AUTH ──────────────────────

print("\n=== AUTH ===")

REG_USER = {
    "email": "alice@example.com",
    "password": "supersecret123",
    "full_name": "Alice Example",
    "organization_name": "Alice Capital",
}

@test("Register new user + org")
def _(c, db):
    r = c.post("/auth/register", json=REG_USER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"  # creator becomes admin
    assert body["access_token"]

@test("Register without org joins default-org as editor")
def _(c, db):
    r = c.post("/auth/register", json={
        "email": "bob@example.com", "password": "supersecret123", "full_name": "Bob",
    })
    assert r.status_code == 201
    assert r.json()["role"] == "editor"
    assert r.json()["organization_id"] == "default-org"

@test("Duplicate email → 409")
def _(c, db):
    c.post("/auth/register", json=REG_USER)
    r = c.post("/auth/register", json=REG_USER)
    assert r.status_code == 409

@test("Login with valid credentials")
def _(c, db):
    c.post("/auth/register", json=REG_USER)
    r = c.post("/auth/login", json={"email": REG_USER["email"], "password": REG_USER["password"]})
    assert r.status_code == 200
    assert r.json()["access_token"]

@test("Login with wrong password → 401")
def _(c, db):
    c.post("/auth/register", json=REG_USER)
    r = c.post("/auth/login", json={"email": REG_USER["email"], "password": "wrongpass99"})
    assert r.status_code == 401

@test("Login with unknown email → 401")
def _(c, db):
    r = c.post("/auth/login", json={"email": "nobody@x.com", "password": "whatever123"})
    assert r.status_code == 401

@test("/auth/me with valid token")
def _(c, db):
    token = c.post("/auth/register", json=REG_USER).json()["access_token"]
    r = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == REG_USER["email"]
    assert body["role"] == "admin"

@test("/auth/me without token → 401")
def _(c, db):
    r = c.get("/auth/me")
    assert r.status_code == 401

@test("/auth/me with malformed header → 401")
def _(c, db):
    r = c.get("/auth/me", headers={"Authorization": "NotBearer xyz"})
    assert r.status_code == 401

@test("/auth/me with invalid token → 401")
def _(c, db):
    r = c.get("/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
    assert r.status_code == 401

@test("Password is hashed, not stored plaintext")
def _(c, db):
    c.post("/auth/register", json=REG_USER)
    from app.models.user import User
    u = db.query(User).filter(User.email == REG_USER["email"]).first()
    assert u is not None
    assert u.password_hash != REG_USER["password"]
    assert u.password_hash.startswith("$2")  # bcrypt prefix

# ──────────────────── ORG ISOLATION (authed requests) ──────────────────────

print("\n=== ORG ISOLATION ===")

def _register_and_auth(c, email, org_name):
    body = c.post("/auth/register", json={
        "email": email, "password": "supersecret123",
        "full_name": "Test User", "organization_name": org_name,
    }).json()
    return body["access_token"], body["organization_id"]

@test("Authed request scopes deals to token's org")
def _(c, db):
    tok_a, org_a = _register_and_auth(c, "a@x.com", "Org A")
    tok_b, org_b = _register_and_auth(c, "b@x.com", "Org B")
    assert org_a != org_b
    hdr_a = {"Authorization": f"Bearer {tok_a}"}
    hdr_b = {"Authorization": f"Bearer {tok_b}"}
    # A creates a deal
    did_a = c.post("/deals", json={**SAMPLE_DEAL, "name": "A's Deal"}, headers=hdr_a).json()["id"]
    # B creates a deal
    did_b = c.post("/deals", json={**SAMPLE_DEAL, "name": "B's Deal"}, headers=hdr_b).json()["id"]
    # A sees only A's deals
    a_list = c.get("/deals", headers=hdr_a).json()
    a_names = {d["name"] for d in a_list}
    assert "A's Deal" in a_names
    assert "B's Deal" not in a_names
    # B sees only B's deals
    b_list = c.get("/deals", headers=hdr_b).json()
    b_names = {d["name"] for d in b_list}
    assert "B's Deal" in b_names
    assert "A's Deal" not in b_names

@test("Cross-org deal access returns 404")
def _(c, db):
    tok_a, _ = _register_and_auth(c, "a2@x.com", "Org A2")
    tok_b, _ = _register_and_auth(c, "b2@x.com", "Org B2")
    did_a = c.post("/deals", json=SAMPLE_DEAL, headers={"Authorization": f"Bearer {tok_a}"}).json()["id"]
    # B tries to read A's deal → should 404 (filtered out by org scope)
    r = c.get(f"/deals/{did_a}", headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404

@test("Unauthed requests still hit default-org (backward compat)")
def _(c, db):
    r = c.post("/deals", json=SAMPLE_DEAL)
    assert r.status_code == 201
    # And the deal is scoped to default-org
    from app.models.deal import Deal
    d = db.query(Deal).filter(Deal.id == r.json()["id"]).first()
    assert d.organization_id == "default-org"

# ──────────────────── RBAC ──────────────────────

print("\n=== RBAC ===")

def _register_admin(c, email, org_name):
    body = c.post("/auth/register", json={
        "email": email, "password": "supersecret123",
        "full_name": "Admin User", "organization_name": org_name,
    }).json()
    return body["access_token"], body["organization_id"]

@test("Admin can delete deal (authed)")
def _(c, db):
    tok, _ = _register_admin(c, "admin1@x.com", "RBAC Org 1")
    hdr = {"Authorization": f"Bearer {tok}"}
    did = c.post("/deals", json=SAMPLE_DEAL, headers=hdr).json()["id"]
    r = c.delete(f"/deals/{did}", headers=hdr)
    assert r.status_code == 204, r.text

@test("Viewer cannot delete deal → 403")
def _(c, db):
    # Admin creates org + deal
    admin_tok, org_id = _register_admin(c, "admin2@x.com", "RBAC Org 2")
    admin_hdr = {"Authorization": f"Bearer {admin_tok}"}
    did = c.post("/deals", json=SAMPLE_DEAL, headers=admin_hdr).json()["id"]
    # Register a viewer user (joins default-org), then admin invites + demotes to viewer
    c.post("/auth/register", json={
        "email": "viewer@x.com", "password": "supersecret123", "full_name": "Viewer",
    })
    invite_r = c.post(
        f"/organizations/{org_id}/members",
        json={"email": "viewer@x.com", "role": "viewer"},
        headers=admin_hdr,
    )
    assert invite_r.status_code == 201, invite_r.text
    # Viewer logs in, switches to the new org
    viewer_login = c.post("/auth/login", json={"email": "viewer@x.com", "password": "supersecret123"}).json()
    switch_r = c.post(
        "/auth/switch-org",
        json={"organization_id": org_id},
        headers={"Authorization": f"Bearer {viewer_login['access_token']}"},
    )
    assert switch_r.status_code == 200
    viewer_tok = switch_r.json()["access_token"]
    # Viewer attempts delete
    r = c.delete(f"/deals/{did}", headers={"Authorization": f"Bearer {viewer_tok}"})
    assert r.status_code == 403

@test("Unauthed delete still works (demo mode)")
def _(c, db):
    did = c.post("/deals", json=SAMPLE_DEAL).json()["id"]
    r = c.delete(f"/deals/{did}")
    assert r.status_code == 204

# ──────────────────── ORG & MEMBERSHIP API ──────────────────────

print("\n=== ORG & MEMBERSHIP API ===")

@test("GET /organizations/me lists my orgs")
def _(c, db):
    tok, org_id = _register_admin(c, "u1@x.com", "User1 Org")
    r = c.get("/organizations/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["organization"]["id"] == org_id
    assert body[0]["role"] == "admin"

@test("List members of org")
def _(c, db):
    tok, org_id = _register_admin(c, "u2@x.com", "User2 Org")
    r = c.get(f"/organizations/{org_id}/members", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    members = r.json()
    assert len(members) == 1
    assert members[0]["email"] == "u2@x.com"
    assert members[0]["role"] == "admin"

@test("Invite existing user as editor")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner3@x.com", "Owner3 Org")
    c.post("/auth/register", json={"email": "newbie@x.com", "password": "supersecret123", "full_name": "New"})
    r = c.post(
        f"/organizations/{org_id}/members",
        json={"email": "newbie@x.com", "role": "editor"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "editor"

@test("Invite unknown email → 404")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner4@x.com", "Owner4 Org")
    r = c.post(
        f"/organizations/{org_id}/members",
        json={"email": "ghost@x.com", "role": "editor"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 404

@test("Duplicate invite → 409")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner5@x.com", "Owner5 Org")
    c.post("/auth/register", json={"email": "twice@x.com", "password": "supersecret123", "full_name": "T"})
    headers = {"Authorization": f"Bearer {admin_tok}"}
    c.post(f"/organizations/{org_id}/members", json={"email": "twice@x.com", "role": "editor"}, headers=headers)
    r = c.post(f"/organizations/{org_id}/members", json={"email": "twice@x.com", "role": "viewer"}, headers=headers)
    assert r.status_code == 409

@test("Non-admin cannot invite → 403")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner6@x.com", "Owner6 Org")
    c.post("/auth/register", json={"email": "ed@x.com", "password": "supersecret123", "full_name": "Ed"})
    c.post(
        f"/organizations/{org_id}/members",
        json={"email": "ed@x.com", "role": "editor"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    # Editor tries to invite
    ed_login = c.post("/auth/login", json={"email": "ed@x.com", "password": "supersecret123"}).json()
    switched = c.post(
        "/auth/switch-org", json={"organization_id": org_id},
        headers={"Authorization": f"Bearer {ed_login['access_token']}"},
    ).json()
    c.post("/auth/register", json={"email": "victim@x.com", "password": "supersecret123", "full_name": "V"})
    r = c.post(
        f"/organizations/{org_id}/members",
        json={"email": "victim@x.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {switched['access_token']}"},
    )
    assert r.status_code == 403

@test("Update member role")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner7@x.com", "Owner7 Org")
    reg = c.post("/auth/register", json={"email": "mem7@x.com", "password": "supersecret123", "full_name": "M"}).json()
    headers = {"Authorization": f"Bearer {admin_tok}"}
    c.post(f"/organizations/{org_id}/members", json={"email": "mem7@x.com", "role": "editor"}, headers=headers)
    r = c.patch(
        f"/organizations/{org_id}/members/{reg['user_id']}",
        json={"role": "viewer"}, headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"

@test("Cannot demote last admin")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "lone@x.com", "Lone Org")
    reg = c.post("/auth/login", json={"email": "lone@x.com", "password": "supersecret123"}).json()
    r = c.patch(
        f"/organizations/{org_id}/members/{reg['user_id']}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 400

@test("Remove member")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "owner8@x.com", "Owner8 Org")
    reg = c.post("/auth/register", json={"email": "kick@x.com", "password": "supersecret123", "full_name": "K"}).json()
    headers = {"Authorization": f"Bearer {admin_tok}"}
    c.post(f"/organizations/{org_id}/members", json={"email": "kick@x.com", "role": "editor"}, headers=headers)
    r = c.delete(f"/organizations/{org_id}/members/{reg['user_id']}", headers=headers)
    assert r.status_code == 204

@test("Cannot remove last admin")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "solo@x.com", "Solo Org")
    reg = c.post("/auth/login", json={"email": "solo@x.com", "password": "supersecret123"}).json()
    r = c.delete(
        f"/organizations/{org_id}/members/{reg['user_id']}",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 400

@test("Switch org issues new token for that org")
def _(c, db):
    admin_tok, org_id = _register_admin(c, "multi@x.com", "First Org")
    # Register again with a second org name for same user? Can't — email is unique.
    # Instead: invite multi@x.com into a second org
    second = c.post("/auth/register", json={
        "email": "second-admin@x.com", "password": "supersecret123",
        "full_name": "S", "organization_name": "Second Org",
    }).json()
    second_admin_hdr = {"Authorization": f"Bearer {second['access_token']}"}
    c.post(
        f"/organizations/{second['organization_id']}/members",
        json={"email": "multi@x.com", "role": "editor"},
        headers=second_admin_hdr,
    )
    # multi switches
    r = c.post(
        "/auth/switch-org",
        json={"organization_id": second["organization_id"]},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 200
    assert r.json()["organization_id"] == second["organization_id"]
    assert r.json()["role"] == "editor"

@test("Switch to org you don't belong to → 403")
def _(c, db):
    tok_a, _ = _register_admin(c, "alone-a@x.com", "Alone A")
    tok_b, org_b = _register_admin(c, "alone-b@x.com", "Alone B")
    r = c.post(
        "/auth/switch-org",
        json={"organization_id": org_b},
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert r.status_code == 403

@test("Buy boxes are org-scoped under auth")
def _(c, db):
    tok_a, _ = _register_and_auth(c, "bb-a@x.com", "BB Org A")
    tok_b, _ = _register_and_auth(c, "bb-b@x.com", "BB Org B")
    c.post("/buy-box", json={"asset_type": "Office"}, headers={"Authorization": f"Bearer {tok_a}"})
    c.post("/buy-box", json={"asset_type": "Industrial"}, headers={"Authorization": f"Bearer {tok_b}"})
    a_boxes = c.get("/buy-box", headers={"Authorization": f"Bearer {tok_a}"}).json()
    b_boxes = c.get("/buy-box", headers={"Authorization": f"Bearer {tok_b}"}).json()
    assert len(a_boxes) == 1 and a_boxes[0]["asset_type"] == "Office"
    assert len(b_boxes) == 1 and b_boxes[0]["asset_type"] == "Industrial"

# ──────────────────── HEALTH ──────────────────────

print("\n=== HEALTH ===")

@test("GET /health")
def _(c, db):
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ──────────────────── RESULTS ──────────────────────

print(f"\n{'='*50}")
print(f"\033[{'32' if failed == 0 else '31'}m{passed} passed, {failed} failed\033[0m")

if errors:
    print("\nFailed tests:")
    for name, err in errors:
        print(f"  {name}:")
        for line in err.split('\n')[:3]:
            print(f"    {line}")

sys.exit(0 if failed == 0 else 1)
