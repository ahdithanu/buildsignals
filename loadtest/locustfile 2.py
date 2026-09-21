"""Load test for the DealSignal API.

Not a runtime dependency — install locust separately:

    pip install locust

Run against a local server:

    # terminal 1 — boot the API
    uvicorn app.main:app --port 8000

    # terminal 2 — headless load, 50 users, spawn 5/s, 2 minutes
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 5 -t 2m

Or drop --headless for the web UI at http://localhost:8089.

Point --host at staging (never production) to find bottlenecks before a
customer does. Each simulated user registers its own org on start, so a
run leaves a pile of throwaway orgs/users behind — run against a database
you can wipe, not a shared one.

The journey is intentionally read-heavy (that's the real traffic shape
for a deal-browsing app): listing and dashboard views dominate, with
occasional writes.
"""
from __future__ import annotations

import uuid

from locust import HttpUser, between, task

# All API routes are versioned. See app/middleware/versioning.py.
V = "/v1"


class DealSignalUser(HttpUser):
    # Think-time between actions — a human clicking around, not a hammer.
    wait_time = between(1, 4)

    def on_start(self) -> None:
        """Register a fresh user + org, then log in and keep the token."""
        self.token: str | None = None
        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        password = "LoadTestPassw0rd!"

        # credentials:'include' equivalent isn't needed — we read the access
        # token from the login body and send it as a Bearer header.
        reg = self.client.post(
            f"{V}/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Load Test",
                "organization_name": f"Load Org {uuid.uuid4().hex[:6]}",
            },
            name="POST /auth/register",
        )
        if reg.status_code not in (200, 201):
            # Can't proceed without an account; the failure is already
            # recorded by locust. Stop this user's journey.
            return

        login = self.client.post(
            f"{V}/auth/login",
            json={"email": email, "password": password},
            name="POST /auth/login",
        )
        if login.status_code == 200:
            self.token = login.json().get("access_token")

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ── Read paths (dominant) ────────────────────────────────────────────

    @task(10)
    def list_deals(self) -> None:
        self.client.get(f"{V}/deals", headers=self._auth(), name="GET /deals")

    @task(6)
    def dashboard_kpis(self) -> None:
        self.client.get(
            f"{V}/dashboard/kpis", headers=self._auth(), name="GET /dashboard/kpis"
        )

    @task(4)
    def dashboard_top_opportunities(self) -> None:
        self.client.get(
            f"{V}/dashboard/top-opportunities",
            headers=self._auth(),
            name="GET /dashboard/top-opportunities",
        )

    @task(3)
    def list_signals(self) -> None:
        self.client.get(f"{V}/signals", headers=self._auth(), name="GET /signals")

    # ── Write paths (occasional) ─────────────────────────────────────────

    @task(2)
    def create_deal(self) -> None:
        self.client.post(
            f"{V}/deals",
            headers=self._auth(),
            json={
                "name": f"Deal {uuid.uuid4().hex[:8]}",
                "property_type": "multifamily",
                "units": 24,
                "asking_price": 3_500_000,
            },
            name="POST /deals",
        )
