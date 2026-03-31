"""
Service: Market Overview
Fetches live index data for Sensex, Nifty 50, Bank Nifty.

Data source : yfinance (free, no API key needed)
Symbols     : ^BSESN (Sensex), ^NSEI (Nifty50), ^NSEBANK (BankNifty)
Called by   : GET /market/overview
"""

import yfinance as yf
from datetime import datetime, timezone
from typing import Optional


# ── Index definitions ─────────────────────────────────────────

INDICES = {
    "sensex": {
        "symbol":      "^BSESN",
        "name":        "BSE Sensex",
        "description": "Bombay Stock Exchange top 30 companies",
    },
    "nifty50": {
        "symbol":      "^NSEI",
        "name":        "Nifty 50",
        "description": "NSE top 50 companies",
    },
    "banknifty": {
        "symbol":      "^NSEBANK",
        "name":        "Bank Nifty",
        "description": "NSE banking sector index",
    },
}


# ── Core fetcher ──────────────────────────────────────────────

def fetch_index(symbol: str, name: str) -> dict:
    """
    Fetch current index value, change, and % change.

    Returns:
        {
          name, symbol, current, previous_close,
          change, change_pct, direction,
          day_high, day_low, last_updated
        }
    """
    ticker = yf.Ticker(symbol)

    # fast_info is lightweight — no full download needed
    info = ticker.fast_info

    current        = round(float(info.last_price), 2)
    previous_close = round(float(info.previous_close), 2)
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
        "day_high":       round(float(info.day_high), 2),
        "day_low":        round(float(info.day_low), 2),
        "last_updated":   datetime.now(timezone.utc).isoformat(),
    }


def fetch_index_history(symbol: str, period: str = "1mo") -> list[dict]:
    """
    Fetch OHLCV history for mini sparkline chart on home page.

    period options: "1d", "5d", "1mo", "3mo"
    Returns list of { date, close } for a simple line chart.
    """
    ticker = yf.Ticker(symbol)
    hist   = ticker.history(period=period, interval="1d")

    if hist.empty:
        return []

    return [
        {
            "date":  str(row.Index.date()),
            "close": round(float(row.Close), 2),
            "open":  round(float(row.Open), 2),
            "high":  round(float(row.High), 2),
            "low":   round(float(row.Low), 2),
        }
        for row in hist.itertuples()
    ]


# ── Main function called by router ────────────────────────────

def get_market_overview() -> dict:
    """
    Fetches all three indices and returns combined overview.
    Called by GET /market/overview
    """
    results = {}
    errors  = []

    for key, meta in INDICES.items():
        try:
            results[key] = fetch_index(meta["symbol"], meta["name"])
        except Exception as e:
            errors.append(f"{key}: {str(e)}")
            results[key] = _fallback_index(meta["name"], meta["symbol"])

    results["last_updated"] = datetime.now(timezone.utc).isoformat()
    results["errors"]       = errors   # empty list if all OK
    return results


def get_index_history(index_key: str, period: str = "1mo") -> list[dict]:
    """
    Returns price history for a given index key.
    index_key: "sensex" | "nifty50" | "banknifty"
    """
    meta = INDICES.get(index_key)
    if not meta:
        return []
    return fetch_index_history(meta["symbol"], period)


# ── Fallback (used when yfinance call fails) ──────────────────

def _fallback_index(name: str, symbol: str) -> dict:
    """Returns a safe empty response when API fails."""
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
        "error":          "Data unavailable",
    }