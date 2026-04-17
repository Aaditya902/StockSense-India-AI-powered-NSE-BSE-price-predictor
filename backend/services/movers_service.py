"""
Service: Market Movers
Fetches top gainers and top losers from NSE India.

Primary  : NSE India public API via nse_direct (shared session, handles empty-body blocks)
Fallback : yfinance via get_price() — uses history(), compatible with yfinance >= 0.2.61
Cache    : 5-minute in-memory cache

Called by: GET /market/movers
"""

import time
from datetime import datetime, timezone

_cache: dict = {"data": None, "expires_at": 0}
CACHE_TTL = 300   # 5 minutes

NIFTY50_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "HCLTECH.NS", "WIPRO.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATAMOTORS.NS",
    "ULTRACEMCO.NS", "NESTLEIND.NS", "POWERGRID.NS", "NTPC.NS", "TECHM.NS",
    "BAJAJFINSV.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "HINDALCO.NS", "DRREDDY.NS",
]


def get_market_movers() -> dict:
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    try:
        result = _fetch_from_nse()
        _cache["data"]       = result
        _cache["expires_at"] = now + CACHE_TTL
        return result
    except Exception as e:
        print(f"[MoversService] NSE API failed: {e} — trying yfinance fallback")

    try:
        result = _fetch_from_yfinance()
        _cache["data"]       = result
        _cache["expires_at"] = now + CACHE_TTL
        return result
    except Exception as e:
        print(f"[MoversService] yfinance fallback also failed: {e}")
        return _empty_response()


def _fetch_from_nse() -> dict:
    from backend.services.nse_direct import _nse_get, _parse_movers
    gain_data = _nse_get("/api/live-analysis-variations?index=gainers")
    loss_data = _nse_get("/api/live-analysis-variations?index=loosers")
    gainers = _parse_movers(gain_data, "gainer")[:5]
    losers  = _parse_movers(loss_data, "loser")[:5]
    return {
        "gainers":      gainers,
        "losers":       losers,
        "source":       "nse",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_from_yfinance() -> dict:
    """Uses get_price() which calls history(period='5d') — works with yfinance >= 0.2.61."""
    from backend.services.yf_session import get_price

    results = []
    for symbol in NIFTY50_SYMBOLS:
        try:
            data = get_price(symbol)
            results.append({
                "name":       symbol.replace(".NS", ""),
                "symbol":     symbol,
                "price":      data["price"],
                "change_pct": data["change_pct"],
                "direction":  data["direction"],
                "source":     "yfinance",
            })
        except Exception:
            continue

    if not results:
        raise RuntimeError("yfinance returned no data for any symbol")

    results.sort(key=lambda x: x["change_pct"], reverse=True)
    return {
        "gainers":      results[:5],
        "losers":       results[-5:][::-1],
        "source":       "yfinance_fallback",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _empty_response() -> dict:
    return {
        "gainers":      [],
        "losers":       [],
        "source":       "unavailable",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def invalidate_cache():
    _cache["data"]       = None
    _cache["expires_at"] = 0