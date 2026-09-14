"""
Waterford Estate Sales Intelligence — FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.database import engine
from app.api.routes import health
from app.api.routes.clients    import router as clients_router
from app.api.routes.queue      import router as queue_router
from app.api.routes.reports    import router as reports_router
from app.api.routes.imports    import router as imports_router
from app.api.routes.commercial import router as commercial_router
from app.api.routes.crm       import router as crm_router
from app.api.routes.auth      import router as auth_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Waterford SI — env: {settings.app_env}")
    yield
    await engine.dispose()


import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_UPLOAD_MB = 50

app = FastAPI(
    title="Waterford Estate Sales Intelligence API",
    version="1.0.0",
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url="/api/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router,   prefix="/api")
app.include_router(clients_router)    # already prefixed /api/clients
app.include_router(queue_router)      # already prefixed /api/queue
app.include_router(reports_router)    # already prefixed /api/reports
app.include_router(imports_router)    # already prefixed /api/imports
app.include_router(commercial_router) # already prefixed /api/commercial
app.include_router(crm_router)        # already prefixed /api/crm
app.include_router(auth_router)       # already prefixed /api/auth


@app.get("/")
async def root():
    return {"message": "Waterford Estate Sales Intelligence API", "version": "1.0.0"}


@app.get("/api/routes")
async def list_routes():
    """Dev endpoint: list all registered routes."""
    return [
        {"path": r.path, "methods": list(r.methods)}
        for r in app.routes
        if hasattr(r, "methods")
    ]
