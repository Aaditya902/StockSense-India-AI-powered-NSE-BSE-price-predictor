"""
StockSense India — FastAPI Backend
Entry point: uvicorn main:app --reload

All endpoints:
  GET  /search?q=           → stock search
  GET  /market/overview     → Sensex, Nifty50, BankNifty
  GET  /market/movers       → top gainers + losers
  GET  /market/trending     → trending stocks + commodities
  GET  /stock/{symbol}      → stock detail + chart
  WS   /stock/{symbol}/live → live price stream
  GET  /stock/{symbol}/factors  → 6 factor scores
  GET  /stock/{symbol}/predict  → predicted price + % delta
  GET  /stock/{symbol}/news     → news + sentiment
  GET  /health              → server status check

Frontend served at:
  http://127.0.0.1:8000/app         → Page 1 (Market home)
  http://127.0.0.1:8000/app/stock   → Page 2 (Stock detail)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import APP_TITLE, APP_VERSION, has_groq, has_gemini, has_news, has_fred
from backend.routers.search import router as search_router
from backend.routers.market import router as market_router
from backend.routers.stock  import router as stock_router


# ── App init ──────────────────────────────────────────────────

app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="AI-powered NSE/BSE stock price predictor",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow all origins (file://, localhost, any port) ───

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,      # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────

app.include_router(search_router)
app.include_router(market_router)
app.include_router(stock_router)

# ── Serve frontend files ──────────────────────────────────────
# Serves the frontend at /app so you can open:
#   http://127.0.0.1:8000/app          → index.html (Market home)
#   http://127.0.0.1:8000/app/stock    → stock.html (Stock detail)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

if os.path.exists(FRONTEND_DIR):
    @app.get("/app", include_in_schema=False)
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/app/stock", include_in_schema=False)
    def serve_stock():
        return FileResponse(os.path.join(FRONTEND_DIR, "stock.html"))

    # Serve all static assets (CSS, JS if any)
    app.mount("/app/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")


# ── Health check ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    return JSONResponse({
        "status": "ok",
        "version": APP_VERSION,
        "frontend": "http://127.0.0.1:8000/app",
        "apis_configured": {
            "groq":    has_groq(),
            "gemini":  has_gemini(),
            "news":    has_news(),
            "fred":    has_fred(),
            "yfinance": True,
            "nse":     True,
        }
    })


@app.get("/debug/yfinance/{symbol}", tags=["System"])
def debug_yfinance(symbol: str):
    """Debug endpoint — shows what yfinance returns for a symbol."""
    import yfinance as yf
    result = {}
    ticker = yf.Ticker(symbol)
    try:
        fi = ticker.fast_info
        result["fast_info"] = {
            "last_price":     str(fi.last_price),
            "previous_close": str(fi.previous_close),
        }
    except Exception as e:
        result["fast_info_error"] = str(e)
    try:
        hist = ticker.history(period="5d", interval="1d")
        result["history_rows"] = len(hist)
        if not hist.empty:
            result["history_last_close"] = float(hist["Close"].iloc[-1])
    except Exception as e:
        result["history_error"] = str(e)
    return result


@app.get("/", tags=["System"])
def root():
    return {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "frontend": "http://127.0.0.1:8000/app",
        "docs":     "http://127.0.0.1:8000/docs",
        "health":   "http://127.0.0.1:8000/health",
    }