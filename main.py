"""
StockSense India — FastAPI Backend
Entry point: uvicorn main:app --reload

All endpoints:
  GET  /search?q=           → stock search
  GET  /search/all          → full stock list
  GET  /search/sector/{s}   → stocks by sector
  GET  /market/overview     → Sensex, Nifty50, BankNifty
  GET  /market/movers       → top gainers + losers
  GET  /market/trending     → trending stocks + commodities
  GET  /stock/{symbol}      → stock detail + chart
  WS   /stock/{symbol}/live → live price stream
  GET  /stock/{symbol}/factors  → 6 factor scores
  GET  /stock/{symbol}/predict  → predicted price + % delta
  GET  /stock/{symbol}/news     → news + sentiment
  GET  /health              → server status check
"""

import sys
import os

# Make project root importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import APP_TITLE, APP_VERSION, CORS_ORIGINS, has_groq, has_gemini, has_news, has_fred
from backend.routers.search import router as search_router
from backend.routers.market import router as market_router
from backend.routers.stock  import router as stock_router


# ── App init ──────────────────────────────────────────────────

app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="AI-powered NSE/BSE stock price predictor",
    docs_url="/docs",       # Swagger UI at http://localhost:8000/docs
    redoc_url="/redoc",
)

# ── CORS — allow frontend to call API ─────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────

app.include_router(search_router)
app.include_router(market_router)
app.include_router(stock_router)


# ── Health check ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """
    Returns server status and which API keys are configured.
    Useful for debugging before starting development.
    """
    return JSONResponse({
        "status": "ok",
        "version": APP_VERSION,
        "apis_configured": {
            "groq":    has_groq(),
            "gemini":  has_gemini(),
            "news":    has_news(),
            "fred":    has_fred(),
            "yfinance": True,     # no key needed
            "nse":     True,      # no key needed
        }
    })


@app.get("/", tags=["System"])
def root():
    return {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }