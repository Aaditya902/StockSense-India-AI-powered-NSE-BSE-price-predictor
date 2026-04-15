"""
Service: Trending
Fetches trending stocks and commodity prices.

Trending stocks  : NSE India most-active / volume leaders API
Commodities      : yfinance futures symbols (Gold, Silver, Crude, Gas)
Cache            : 5-minute in-memory cache (same strategy as movers)

Called by: GET /market/trending
"""

import time
import requests
import yfinance as yf
from datetime import datetime, timezone


# ── In-memory cache 

_cache: dict = {
    "data":       None,
    "expires_at": 0,
}
CACHE_TTL = 300   # 5 minutes


# ── Commodity definitions ─────────────────────────────────────
# yfinance futures symbols — free, no key needed

COMMODITIES = [
    {"name": "Gold",        "symbol": "GC=F", "unit": "USD/oz"},
    {"name": "Silver",      "symbol": "SI=F", "unit": "USD/oz"},
    {"name": "Crude Oil",   "symbol": "CL=F", "unit": "USD/barrel"},
    {"name": "Natural Gas", "symbol": "NG=F", "unit": "USD/MMBtu"},
]

# NSE most-active stocks endpoint
NSE_BASE          = "https://www.nseindia.com"
NSE_MOST_ACTIVE   = f"{NSE_BASE}/api/live-analysis-variations?index=mostactive"

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         NSE_BASE + "/",
    "Connection":      "keep-alive",
}

# Fallback: hand-picked high-volume NSE stocks when NSE API fails
TRENDING_FALLBACK_SYMBOLS = [
    ("RELIANCE.NS",   "Reliance Industries"),
    ("TCS.NS",        "Tata Consultancy Services"),
    ("HDFCBANK.NS",   "HDFC Bank"),
    ("ICICIBANK.NS",  "ICICI Bank"),
    ("SBIN.NS",       "State Bank of India"),
    ("TATAMOTORS.NS", "Tata Motors"),
    ("ZOMATO.NS",     "Zomato"),
    ("ADANIENT.NS",   "Adani Enterprises"),
    ("INFY.NS",       "Infosys"),
    ("BAJFINANCE.NS", "Bajaj Finance"),
]


# ── Main function ─────────────────────────────────────────────

def get_trending() -> dict:
    """
    Returns trending stocks + commodity prices.
    Cached for 5 minutes.
    """
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    # Fetch both in parallel — independent sources
    trending_stocks = _fetch_trending_stocks()
    commodities     = _fetch_commodities()

    result = {
        "trending_stocks":      trending_stocks,
        "trending_commodities": commodities,
        "last_updated":         datetime.now(timezone.utc).isoformat(),
    }

    _cache["data"]       = result
    _cache["expires_at"] = now + CACHE_TTL
    return result


# ── Trending stocks ───────────────────────────────────────────

def _fetch_trending_stocks() -> list[dict]:
    """Try NSE most-active API, fall back to yfinance."""
    try:
        return _nse_most_active()
    except Exception as e:
        print(f"[TrendingService] NSE trending failed: {e} — using yfinance fallback")
        return _yfinance_trending_fallback()


def _nse_most_active() -> list[dict]:
    """Fetch most-actively traded stocks from NSE India."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    # Step 1 — grab session cookie
    session.get(NSE_BASE, timeout=10)
    time.sleep(0.5)

    # Step 2 — fetch most active
    r = session.get(NSE_MOST_ACTIVE, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])

    stocks = []
    for row in data[:8]:       # top 8 trending
        try:
            symbol = row.get("symbol", "").strip()
            if not symbol:
                continue

            name       = row.get("meta", {}).get("companyName", symbol) \
                         if isinstance(row.get("meta"), dict) else symbol
            price      = float(row.get("ltp", row.get("lastPrice", 0)))
            change_pct = float(row.get("pChange", row.get("perChange", 0)))
            volume     = int(row.get("tradedQuantity", row.get("totalTradedVolume", 0)))

            stocks.append({
                "name":       name,
                "symbol":     symbol + ".NS",
                "price":      round(price, 2),
                "change_pct": round(change_pct, 2),
                "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                "reason":     _trending_reason(volume, change_pct),
                "source":     "nse",
            })
        except (ValueError, TypeError, KeyError):
            continue

    return stocks


def _yfinance_trending_fallback() -> list[dict]:
    """Fetch a curated list of high-interest stocks via yfinance."""
    stocks = []
    for symbol, name in TRENDING_FALLBACK_SYMBOLS:
        try:
            info       = yf.Ticker(symbol).fast_info
            price      = round(float(info.last_price), 2)
            prev       = float(info.previous_close)
            change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0.0
            volume     = int(info.three_month_average_volume or 0)

            stocks.append({
                "name":       name,
                "symbol":     symbol,
                "price":      price,
                "change_pct": change_pct,
                "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                "reason":     _trending_reason(volume, change_pct),
                "source":     "yfinance",
            })
        except Exception:
            continue

    # Sort by absolute % move — most active movers are most interesting
    stocks.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return stocks[:8]


def _trending_reason(volume: int, change_pct: float) -> str:
    """Generate a short human-readable reason for trending."""
    if abs(change_pct) >= 4.0:
        return f"{'Up' if change_pct > 0 else 'Down'} {abs(change_pct):.1f}% today"
    if volume > 10_000_000:
        return "Very high trading volume"
    if volume > 5_000_000:
        return "High trading volume today"
    if abs(change_pct) >= 2.0:
        return f"Strong {'gain' if change_pct > 0 else 'loss'} today"
    return "Active trading today"


# ── Commodities ───────────────────────────────────────────────

def _fetch_commodities() -> list[dict]:
    """
    Fetch Gold, Silver, Crude Oil, Natural Gas prices from yfinance.
    These are global futures — no NSE dependency.
    """
    results = []
    for commodity in COMMODITIES:
        try:
            info       = yf.Ticker(commodity["symbol"]).fast_info
            price      = round(float(info.last_price), 2)
            prev       = float(info.previous_close)
            change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0.0

            results.append({
                "name":       commodity["name"],
                "symbol":     commodity["symbol"],
                "price":      price,
                "unit":       commodity["unit"],
                "change_pct": change_pct,
                "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            })
        except Exception as e:
            print(f"[TrendingService] Commodity {commodity['name']} failed: {e}")
            results.append(_fallback_commodity(commodity))

    return results


def _fallback_commodity(commodity: dict) -> dict:
    """Safe zero-value commodity when fetch fails."""
    return {
        "name":       commodity["name"],
        "symbol":     commodity["symbol"],
        "price":      0.0,
        "unit":       commodity["unit"],
        "change_pct": 0.0,
        "direction":  "flat",
    }


def invalidate_cache():
    _cache["data"]       = None
    _cache["expires_at"] = 0