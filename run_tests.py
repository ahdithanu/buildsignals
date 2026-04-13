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


# ── Test data ──────────────────────────────────────────────────────────────

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
