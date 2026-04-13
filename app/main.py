from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
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

app = FastAPI(
    title="DealSignal — Real Estate Acquisition Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.on_event("startup")
def on_startup():
    init_db()
