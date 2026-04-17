"""
config.py — Central configuration
Reads ALL values from .env file — no hardcoded secrets here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys (all from .env) ──────────────────────────────────
GROQ_API_KEY        = os.getenv("GROQ_API_KEY",        "")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY",       "")
NEWS_API_KEY        = os.getenv("NEWS_API_KEY",         "")
FRED_API_KEY        = os.getenv("FRED_API_KEY",         "")
UPSTOX_API_KEY      = os.getenv("UPSTOX_API_KEY",      "")
UPSTOX_API_SECRET   = os.getenv("UPSTOX_API_SECRET",   "")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/upstox/callback")

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "data")
NSE_STOCKS_FILE = os.path.join(DATA_DIR, "nse_stocks.json")

# ── App settings ──────────────────────────────────────────────
APP_TITLE   = "StockSense India"
APP_VERSION = "1.0.0"

# ── Live price refresh ────────────────────────────────────────
PRICE_REFRESH_SECONDS = 60

# ── Prediction ────────────────────────────────────────────────
PREDICTION_HORIZON_DAYS = 7
LSTM_LOOKBACK_DAYS      = 60

# ── AI model names ────────────────────────────────────────────
GROQ_MODEL   = "llama3-8b-8192"
GEMINI_MODEL = "gemini-2.5-flash"

# ── NSE index symbols ─────────────────────────────────────────
NIFTY50_SYMBOL   = "^NSEI"
SENSEX_SYMBOL    = "^BSESN"
BANKNIFTY_SYMBOL = "^NSEBANK"

# ── Commodity symbols ─────────────────────────────────────────
COMMODITY_SYMBOLS = {
    "Gold":        "GC=F",
    "Silver":      "SI=F",
    "Crude Oil":   "CL=F",
    "Natural Gas": "NG=F",
}

# ── Key presence checks ───────────────────────────────────────
def has_groq()    -> bool: return bool(GROQ_API_KEY)
def has_gemini()  -> bool: return bool(GEMINI_API_KEY)
def has_news()    -> bool: return bool(NEWS_API_KEY)
def has_fred()    -> bool: return bool(FRED_API_KEY)
def has_upstox()  -> bool: return bool(UPSTOX_API_KEY and UPSTOX_API_SECRET)