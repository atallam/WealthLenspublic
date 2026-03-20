"""
WealthLens OSS — Main Application
FastAPI server with encrypted multi-tenant family wealth management.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.database import init_db


# Import all models so tables are created
import app.models  # noqa: F401
import app.budget_models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables if they don't exist."""
    init_db()
    print(f"🔐 WealthLens OSS started — {settings.ENVIRONMENT} mode")
    print(f"   Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    yield
    print("WealthLens OSS shutting down")


app = FastAPI(
    title="WealthLens OSS",
    description="Zero-knowledge family wealth management — your data stays yours.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routes ---
from app.routes.auth import router as auth_router
from app.routes.holdings import router as holdings_router
from app.routes.transactions import router as transactions_router
from app.routes.portfolio import router as portfolio_router
from app.routes.market import router as market_router
from app.routes.ai import router as ai_router
from app.routes.artifacts import router as artifacts_router
from app.routes.budget import router as budget_router

app.include_router(auth_router)
app.include_router(holdings_router)
app.include_router(transactions_router)
app.include_router(portfolio_router)
app.include_router(market_router)
app.include_router(ai_router)
app.include_router(artifacts_router)
app.include_router(budget_router)


# --- Health Check ---
@app.get("/api/health")
def health():
    from app.database import get_pool_status
    from app.config import settings
    return {
        "status": "ok",
        "version": "2.0.0",
        "encryption": "AES-256-GCM",
        "key_derivation": "PBKDF2-SHA256-600K",
        "db_pool": get_pool_status(),
        "redis": bool(settings.REDIS_URL),
        "twelve_data": bool(settings.TWELVE_DATA_API_KEY),
        "ai_advisor": bool(settings.ANTHROPIC_API_KEY),
        "google_oauth": bool(settings.GOOGLE_CLIENT_ID),
    }


# --- Serve React SPA (production) ---
DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(DIST_DIR):
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    # SPA catch-all: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't catch API routes
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        index = os.path.join(DIST_DIR, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return {"error": "Frontend not built. Run: cd frontend && npm run build"}
