"""
config.py — Central configuration
All environment variables and app settings live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
NEWS_API_KEY     = os.getenv("NEWS_API_KEY", "")
FRED_API_KEY     = os.getenv("FRED_API_KEY", "")

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(BASE_DIR, "data")
NSE_STOCKS_FILE  = os.path.join(DATA_DIR, "nse_stocks.json")

# ── App settings ──────────────────────────────────────────────
APP_TITLE        = "StockSense India"
APP_VERSION      = "1.0.0"
CORS_ORIGINS     = ["*"]              # tighten in production

# ── Live price refresh ────────────────────────────────────────
PRICE_REFRESH_SECONDS = 60            # WebSocket push interval

# ── Prediction settings ───────────────────────────────────────
PREDICTION_HORIZON_DAYS = 7          # predict 7 days ahead
LSTM_LOOKBACK_DAYS      = 60         # 60 days of history as input

# ── AI model names ────────────────────────────────────────────
GROQ_MODEL   = "llama3-8b-8192"      # fast, free
GEMINI_MODEL = "gemini-2.5-flash"    # fallback, free

# ── NSE index symbols (yfinance format) ───────────────────────
SENSEX_SYMBOL    = "^BSESN"
NIFTY50_SYMBOL   = "^NSEI"
BANKNIFTY_SYMBOL = "^NSEBANK"

# ── Trending commodities tracked ──────────────────────────────
COMMODITY_SYMBOLS = {
    "Gold":        "GC=F",
    "Silver":      "SI=F",
    "Crude Oil":   "CL=F",
    "Natural Gas": "NG=F",
}

# ── Validation helpers ────────────────────────────────────────
def has_groq()    -> bool: return bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_key_here")
def has_gemini()  -> bool: return bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_google_api_key_here")
def has_news()    -> bool: return bool(NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here")
def has_fred()    -> bool: return bool(FRED_API_KEY and FRED_API_KEY != "your_fred_key_here")