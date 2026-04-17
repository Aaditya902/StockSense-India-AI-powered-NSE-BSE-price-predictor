"""
StockSense India — FastAPI application entry point

Run locally:  uvicorn main:app --reload
Run on Render: uvicorn main:app --host 0.0.0.0 --port $PORT

Frontend:
  http://localhost:8000/           → Page 1 (Market home)
  http://localhost:8000/stock      → Page 2 (Stock detail)

API prefix /api:
  /api/search, /api/market/*, /api/stock/*

Upstox live data:
  http://localhost:8000/upstox/login    → one-time daily login
  http://localhost:8000/upstox/status   → check connection
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import APP_TITLE, APP_VERSION, has_groq, has_gemini, has_news, has_fred, has_upstox
from backend.routers.search  import router as search_router
from backend.routers.market  import router as market_router
from backend.routers.stock   import router as stock_router
from backend.routers.upstox  import router as upstox_router

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ───────────────────────────────────────────────

app.include_router(search_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(stock_router,  prefix="/api")
app.include_router(upstox_router)

# ── Frontend pages ────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/stock", include_in_schema=False)
def serve_stock():
    return FileResponse(os.path.join(FRONTEND_DIR, "stock.html"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# ── Health check ──────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    """Load all NSE/BSE instruments at startup (runs in background)."""
    import asyncio
    async def _load():
        try:
            from backend.services.instruments import load_instruments
            await asyncio.get_event_loop().run_in_executor(None, load_instruments)
        except Exception as e:
            print(f"[Startup] Instruments load failed: {e}")
    asyncio.create_task(_load())


@app.get("/health", tags=["System"])
def health_check():
    from backend.services.upstox_service import has_valid_token
    return JSONResponse({
        "status":  "ok",
        "version": APP_VERSION,
        "apis": {
            "groq":              has_groq(),
            "gemini":            has_gemini(),
            "news":              has_news(),
            "fred":              has_fred(),
            "upstox_configured": has_upstox(),
            "upstox_connected":  has_valid_token(),
        }
    })