import os

if os.environ.get("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.environ.get("ENVIRONMENT", "development"),
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration()],
        send_default_pii=False,
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ALLOWED_ORIGINS
from app.logging_config import configure_logging
from app.middleware.auth_context import AuthContextMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

configure_logging()
from app.routes.health import router as health_router
from app.routes.deals import router as deals_router
from app.routes.deal_intelligence import router as intelligence_router
from app.routes.assumptions import router as assumptions_router
from app.routes.contacts import router as contacts_router
from app.routes.activities import router as activities_router
from app.routes.pipeline import router as pipeline_router
from app.routes.signals import router as signals_router
from app.routes.documents import router as documents_router
from app.routes.memos import router as memos_router
from app.routes.dashboard import router as dashboard_router
from app.routes.buy_box import router as buy_box_router
from app.routes.distributions import router as distributions_router
from app.routes.deal_summary import router as deal_summary_router
from app.routes.auth import router as auth_router
from app.routes.twofa import router as twofa_router
from app.routes.audit import router as audit_router
from app.routes.organizations import router as organizations_router, switch_router as auth_switch_router
from app.routes.data_portability import router as data_portability_router

app = FastAPI(
    title="DealSignal — Real Estate Acquisition Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Organization-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

# Resolves JWT (if any) into a per-request org/user ContextVar. Unauthenticated
# requests fall through to the default-org for backward compatibility.
app.add_middleware(AuthContextMiddleware)

# Outermost: tags every request with an X-Request-ID and logs method/path/
# status/duration when it completes. Wrapping auth means even 401s get a
# request_id in the logs and the response header.
app.add_middleware(RequestContextMiddleware)

# Outermost on the response path: stamp baseline security headers on every
# response (including 404s/500s produced before any route runs). Uses
# `setdefault` so route handlers can still override individual headers.
app.add_middleware(SecurityHeadersMiddleware)

# ── Register routers ────────────────────────────────────────────────────────

app.include_router(health_router)
app.include_router(deals_router)
app.include_router(intelligence_router)
app.include_router(assumptions_router)
app.include_router(contacts_router)
app.include_router(activities_router)
app.include_router(pipeline_router)
app.include_router(signals_router)
app.include_router(documents_router)
app.include_router(memos_router)
app.include_router(dashboard_router)
app.include_router(buy_box_router)
app.include_router(distributions_router)
app.include_router(deal_summary_router)
app.include_router(auth_router)
app.include_router(twofa_router)
app.include_router(audit_router)
app.include_router(organizations_router)
app.include_router(auth_switch_router)
app.include_router(data_portability_router)

# NOTE: Schema is managed exclusively by Alembic. Production runs
# `alembic upgrade head` in the Render preDeploy step (see render.yaml).
# For local dev against SQLite, run `alembic upgrade head` once after clone.
# The historical `init_db()` / `Base.metadata.create_all()` path is kept
# available in app.db for test fixtures but is no longer invoked at startup:
# creating schema from models at boot masks migration drift (a model change
# that lacks a migration would "just work" in dev and then fail in prod).
