"""Shared fixtures for all tests.

Each test gets a unique file-based SQLite DB to avoid locking issues.
"""
from __future__ import annotations

import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient with isolated DB per test."""
    db_path = str(tmp_path / f"test_{uuid.uuid4().hex[:8]}.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def _override():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def db(client, tmp_path):
    """Direct DB session for query-based assertions (shares the same DB as client)."""
    # Re-use the override that client set up
    gen = app.dependency_overrides[get_db]()
    session = next(gen)
    yield session
    session.close()


# ── Sample data ────────────────────────────────────────────────────────────

SAMPLE_DEAL = {
    "name": "Test Deal",
    "address": "100 Main St",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78701",
    "property_type": "office",
    "sq_ft": 50000,
    "year_built": 2015,
    "asking_price": 10000000,
}

SAMPLE_ASSUMPTIONS = {
    "purchase_price": 9500000,
    "closing_costs_pct": 0.02,
    "renovation_cost": 500000,
    "loan_amount": 6650000,
    "interest_rate": 0.06,
    "loan_term_years": 30,
    "gross_rental_income": 1200000,
    "vacancy_pct": 0.05,
    "opex_pct": 0.35,
    "cap_rate_market": 0.055,
    "exit_cap_rate": 0.06,
    "hold_period_years": 5,
    "rent_growth_pct": 0.03,
}
