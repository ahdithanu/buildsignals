import os

if os.environ.get("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.environ.get("ENVIRONMENT", "development"),
        release=os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ALLOWED_ORIGINS
from app.logging_config import configure_logging
from app.middleware.auth_context import AuthContextMiddleware
from app.middleware.rate_limit import GlobalRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.versioning import CURRENT_API_PREFIX, ApiVersioningMiddleware

configure_logging()
from app.routes.activities import router as activities_router
from app.routes.assumptions import router as assumptions_router
from app.routes.audit import router as audit_router
from app.routes.auth import router as auth_router
from app.routes.buy_box import router as buy_box_router
from app.routes.contacts import router as contacts_router
from app.routes.dashboard import router as dashboard_router
from app.routes.data_portability import router as data_portability_router
from app.routes.deal_intelligence import router as intelligence_router
from app.routes.deal_summary import router as deal_summary_router
from app.routes.deals import router as deals_router
from app.routes.distributions import router as distributions_router
from app.routes.documents import router as documents_router
from app.routes.health import router as health_router
from app.routes.memos import router as memos_router
from app.routes.organizations import router as organizations_router
from app.routes.organizations import switch_router as auth_switch_router
from app.routes.password_reset import router as password_reset_router
from app.routes.pipeline import router as pipeline_router
from app.routes.signals import router as signals_router
from app.routes.twofa import router as twofa_router
from app.routes.graph import router as graph_router, opportunity_router as graph_opportunity_router
from app.routes.ingestion import router as ingestion_router
from app.routes.brands import router as brands_router
from app.routes.parcels import router as parcels_router

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

# Per-IP DoS backstop. Sits outside AuthContext so a hammering client gets
# rejected before we touch the DB, but inside RequestContext so the 429 still
# carries an X-Request-ID for tracing. Auth routes have their own tighter
# limits at the route layer; those still apply on top of this.
app.add_middleware(GlobalRateLimitMiddleware)

# API versioning: rewrite unversioned inbound paths to /v1/* and stamp
# Deprecation + Sunset headers on the response. Sits outside AuthContext
# so JWT decoding and rate limiting see the rewritten path, ensuring
# per-path counters and audit rows key off the canonical /v1 path.
app.add_middleware(ApiVersioningMiddleware)

# Outermost: tags every request with an X-Request-ID and logs method/path/
# status/duration when it completes. Wrapping auth means even 401s get a
# request_id in the logs and the response header.
app.add_middleware(RequestContextMiddleware)

# Outermost on the response path: stamp baseline security headers on every
# response (including 404s/500s produced before any route runs). Uses
# `setdefault` so route handlers can still override individual headers.
app.add_middleware(SecurityHeadersMiddleware)

# ── Register routers ────────────────────────────────────────────────────────

# Infrastructure — stays unversioned. Restart probes, uptime monitors,
# and OpenAPI codegen tools should not need to know about API versions.
app.include_router(health_router)

# Versioned public API. Every other router mounts under /v1. The
# versioning middleware transparently rewrites unversioned callers
# so existing clients keep working during the deprecation window.
app.include_router(deals_router, prefix=CURRENT_API_PREFIX)
app.include_router(intelligence_router, prefix=CURRENT_API_PREFIX)
app.include_router(assumptions_router, prefix=CURRENT_API_PREFIX)
app.include_router(contacts_router, prefix=CURRENT_API_PREFIX)
app.include_router(activities_router, prefix=CURRENT_API_PREFIX)
app.include_router(pipeline_router, prefix=CURRENT_API_PREFIX)
app.include_router(signals_router, prefix=CURRENT_API_PREFIX)
app.include_router(documents_router, prefix=CURRENT_API_PREFIX)
app.include_router(memos_router, prefix=CURRENT_API_PREFIX)
app.include_router(dashboard_router, prefix=CURRENT_API_PREFIX)
app.include_router(buy_box_router, prefix=CURRENT_API_PREFIX)
app.include_router(distributions_router, prefix=CURRENT_API_PREFIX)
app.include_router(deal_summary_router, prefix=CURRENT_API_PREFIX)
app.include_router(auth_router, prefix=CURRENT_API_PREFIX)
app.include_router(password_reset_router, prefix=CURRENT_API_PREFIX)
app.include_router(twofa_router, prefix=CURRENT_API_PREFIX)
app.include_router(audit_router, prefix=CURRENT_API_PREFIX)
app.include_router(organizations_router, prefix=CURRENT_API_PREFIX)
app.include_router(auth_switch_router, prefix=CURRENT_API_PREFIX)
app.include_router(data_portability_router, prefix=CURRENT_API_PREFIX)
app.include_router(graph_router, prefix=CURRENT_API_PREFIX)
app.include_router(graph_opportunity_router, prefix=CURRENT_API_PREFIX)
app.include_router(ingestion_router, prefix=CURRENT_API_PREFIX)
app.include_router(brands_router, prefix=CURRENT_API_PREFIX)
app.include_router(parcels_router, prefix=CURRENT_API_PREFIX)

# NOTE: Schema is managed exclusively by Alembic. Production runs
# `alembic upgrade head` in the Render preDeploy step (see render.yaml).
# For local dev against SQLite, run `alembic upgrade head` once after clone.
# The historical `init_db()` / `Base.metadata.create_all()` path is kept
# available in app.db for test fixtures but is no longer invoked at startup:
# creating schema from models at boot masks migration drift (a model change
# that lacks a migration would "just work" in dev and then fail in prod).
