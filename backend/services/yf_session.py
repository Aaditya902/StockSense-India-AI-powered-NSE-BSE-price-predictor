"""
yfinance Session Manager — compatible with yfinance >= 0.2.61

WHAT CHANGED FROM 0.2.54
-------------------------
Yahoo Finance deprecated the old /v8/finance/chart cookie-based endpoint in
late 2024. yfinance >= 0.2.55 switched to a new auth flow. The old version
silently returns empty DataFrames or raises JSONDecodeError on individual stock
calls (fast_info, history) even though index calls (/v8/finance/spark) still
worked — which is why Sensex/Nifty showed real values but movers/commodities
showed $0 and "No data".

Solutions in this version:
  1. Drop fast_info entirely — unreliable across versions; use history() only
  2. Use yfinance's built-in session with proper headers (don't override it)
  3. Per-symbol result cache (not ticker cache) — cache actual price data
  4. Minimum 1.2s between calls to avoid 429
  5. Clear error messages so fallbacks trigger correctly
"""

import time
import threading
import yfinance as yf
from datetime import datetime, timezone


# ── Rate limiter ──────────────────────────────────────────────

_lock           = threading.Lock()
_last_call_time = 0.0
MIN_INTERVAL    = 1.2   # seconds between yfinance calls


def _throttle():
    global _last_call_time
    with _lock:
        now     = time.time()
        elapsed = now - _last_call_time
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        _last_call_time = time.time()


# ── Price data cache (caches actual OHLCV, not Ticker objects) ─

_price_cache: dict = {}   # symbol → { price, prev_close, change_pct, expires_at }
PRICE_TTL = 300           # 5 minutes


def get_price(symbol: str) -> dict:
    """
    Returns { price, prev_close, change_pct, direction } for a symbol.
    Uses history(period='5d') which is reliable across yfinance versions.
    Raises RuntimeError on failure so callers can handle fallback.
    """
    now = time.time()
    cached = _price_cache.get(symbol)
    if cached and now < cached["expires_at"]:
        return cached

    _throttle()

    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="5d", interval="1d", auto_adjust=True)

        if hist is None or hist.empty:
            raise RuntimeError(f"yfinance returned empty history for {symbol}")

        closes = hist["Close"].dropna().tolist()
        if not closes:
            raise RuntimeError(f"No close prices in yfinance history for {symbol}")

        price      = round(float(closes[-1]), 2)
        prev_close = round(float(closes[-2]), 2) if len(closes) >= 2 else price
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

        result = {
            "price":      price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            "expires_at": now + PRICE_TTL,
        }
        _price_cache[symbol] = result
        return result

    except Exception as e:
        # Re-raise with the symbol name for easier debugging
        raise RuntimeError(f"yfinance failed for {symbol}: {e}") from e


def get_ticker(symbol: str) -> yf.Ticker:
    """
    Returns a plain yf.Ticker. Kept for backward compatibility with callers
    that use ticker.history() directly.
    No custom session — yfinance >= 0.2.55 manages its own auth internally.
    Throttled to avoid 429.
    """
    _throttle()
    return yf.Ticker(symbol)


def clear_cache(symbol: str = None):
    """Clear price cache for one symbol or all."""
    if symbol:
        _price_cache.pop(symbol, None)
    else:
        _price_cache.clear()