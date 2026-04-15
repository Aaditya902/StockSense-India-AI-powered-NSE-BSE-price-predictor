"""
Service: Market Overview — FIXED
Handles: yfinance None values, closed markets, API changes across versions.

Root cause of zeros: fast_info.last_price returns None when market is closed
or yfinance can't get a live quote. float(None) = TypeError caught silently,
returning 0.0 without triggering the fallback.

Fix: 3-strategy cascade
  Strategy 1 — fast_info (live quote, best when market is open)
  Strategy 2 — ticker.history(period='5d') last close (works even when closed)
  Strategy 3 — ticker.info['regularMarketPrice'] (slower but reliable)
"""

import yfinance as yf
from datetime import datetime, timezone
from typing import Optional
from backend.services.yf_session import get_ticker


INDICES = {
    "sensex":    {"symbol": "^BSESN",   "name": "BSE Sensex"},
    "nifty50":   {"symbol": "^NSEI",    "name": "Nifty 50"},
    "banknifty": {"symbol": "^NSEBANK", "name": "Bank Nifty"},
}


def _safe_float(val) -> Optional[float]:
    """Return float or None — never raises."""
    try:
        f = float(val)
        return f if f != 0.0 else None   # treat 0 as missing
    except (TypeError, ValueError):
        return None


#  Core fetcher with 3-strategy cascade 

def fetch_index(symbol: str, name: str) -> dict:
    """
    Fetch index data using a 3-strategy cascade.
    Always returns a valid dict — never raises.
    """
    ticker = get_ticker(symbol)

    current        = None
    previous_close = None
    day_high       = None
    day_low        = None

    #  Strategy 1: fast_info (live, works during market hours) 
    try:
        fi             = ticker.fast_info
        current        = _safe_float(fi.last_price)
        previous_close = _safe_float(fi.previous_close)
        day_high       = _safe_float(fi.day_high)
        day_low        = _safe_float(fi.day_low)
    except Exception:
        pass

    #  Strategy 2: history (works after hours + holidays) 
    if current is None or previous_close is None:
        try:
            hist = ticker.history(period="5d", interval="1d")
            if not hist.empty:
                closes = hist["Close"].dropna().tolist()
                highs  = hist["High"].dropna().tolist()
                lows   = hist["Low"].dropna().tolist()

                if closes:
                    current        = current        or _safe_float(closes[-1])
                    previous_close = previous_close or _safe_float(closes[-2] if len(closes) >= 2 else closes[-1])
                    day_high       = day_high       or _safe_float(highs[-1]  if highs  else None)
                    day_low        = day_low        or _safe_float(lows[-1]   if lows   else None)
        except Exception:
            pass

    #  Strategy 3: ticker.info (slowest, most reliable fallback) 
    if current is None:
        try:
            info           = ticker.info
            current        = current        or _safe_float(info.get("regularMarketPrice") or info.get("previousClose"))
            previous_close = previous_close or _safe_float(info.get("previousClose")      or info.get("regularMarketPreviousClose"))
            day_high       = day_high       or _safe_float(info.get("dayHigh")             or info.get("regularMarketDayHigh"))
            day_low        = day_low        or _safe_float(info.get("dayLow")              or info.get("regularMarketDayLow"))
        except Exception:
            pass

    if current is None:
        return _fallback_index(name, symbol, "No data from yfinance — market may be closed")

    current        = round(current,        2)
    previous_close = round(previous_close or current, 2)
    day_high       = round(day_high       or current, 2)
    day_low        = round(day_low        or current, 2)
    change         = round(current - previous_close, 2)
    change_pct     = round((change / previous_close) * 100, 2) if previous_close else 0.0

    return {
        "name":           name,
        "symbol":         symbol,
        "current":        current,
        "previous_close": previous_close,
        "change":         change,
        "change_pct":     change_pct,
        "direction":      "up" if change > 0 else "down" if change < 0 else "flat",
        "day_high":       day_high,
        "day_low":        day_low,
        "last_updated":   datetime.now(timezone.utc).isoformat(),
    }


def fetch_index_history(symbol: str, period: str = "1mo") -> list[dict]:
    """Fetch OHLCV history for sparkline charts."""
    try:
        hist = get_ticker(symbol).history(period=period, interval="1d")
        if hist.empty:
            return []
        return [
            {
                "date":  str(row.Index.date()),
                "close": round(float(row.Close), 2),
                "open":  round(float(row.Open),  2),
                "high":  round(float(row.High),  2),
                "low":   round(float(row.Low),   2),
            }
            for row in hist.itertuples()
            if row.Close and float(row.Close) > 0
        ]
    except Exception:
        return []


def get_market_overview() -> dict:
    results = {}
    for key, meta in INDICES.items():
        results[key] = fetch_index(meta["symbol"], meta["name"])
    results["last_updated"] = datetime.now(timezone.utc).isoformat()
    return results


def get_index_history(index_key: str, period: str = "1mo") -> list[dict]:
    meta = INDICES.get(index_key)
    if not meta:
        return []
    return fetch_index_history(meta["symbol"], period)


def _fallback_index(name: str, symbol: str, reason: str = "") -> dict:
    return {
        "name":           name,
        "symbol":         symbol,
        "current":        0.0,
        "previous_close": 0.0,
        "change":         0.0,
        "change_pct":     0.0,
        "direction":      "flat",
        "day_high":       0.0,
        "day_low":        0.0,
        "last_updated":   datetime.now(timezone.utc).isoformat(),
        "error":          reason or "Data unavailable",
    }