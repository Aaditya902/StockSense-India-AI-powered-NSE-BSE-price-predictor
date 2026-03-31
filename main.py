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


@app.get("/debug/yfinance/{symbol}", tags=["System"])
def debug_yfinance(symbol: str):
    """
    Debug endpoint — shows exactly what yfinance returns for a symbol.
    Use this to diagnose zero-value issues.
    e.g. GET /debug/yfinance/^BSESN
    """
    import yfinance as yf
    result = {}
    ticker = yf.Ticker(symbol)

    # fast_info
    try:
        fi = ticker.fast_info
        result["fast_info"] = {
            "last_price":     str(fi.last_price),
            "previous_close": str(fi.previous_close),
            "day_high":       str(fi.day_high),
            "day_low":        str(fi.day_low),
        }
    except Exception as e:
        result["fast_info_error"] = str(e)

    # history
    try:
        hist = ticker.history(period="5d", interval="1d")
        result["history_rows"] = len(hist)
        if not hist.empty:
            result["history_last_close"] = float(hist["Close"].iloc[-1])
            result["history_dates"] = [str(d.date()) for d in hist.index[-3:]]
    except Exception as e:
        result["history_error"] = str(e)

    # info
    try:
        info = ticker.info
        result["info_keys_with_price"] = {
            k: v for k, v in info.items()
            if "price" in k.lower() or "close" in k.lower()
        }
    except Exception as e:
        result["info_error"] = str(e)

    return result


@app.get("/", tags=["System"])
def root():
    return {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }