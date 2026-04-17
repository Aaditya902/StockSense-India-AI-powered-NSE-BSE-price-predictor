"""
Trending Service
Fetches trending stocks and commodity prices.
Uses Upstox for stock data, NSE direct for trending, yfinance for commodities.
Cache: 5 minutes — reduces all external calls significantly.

FIX: Commodities and yfinance trending now use get_price() (history-based)
instead of fast_info, which broke in yfinance < 0.2.61.
"""

import time
import requests
from datetime import datetime, timezone

_cache: dict = {"data": None, "expires_at": 0}
CACHE_TTL = 300  # 5 minutes

COMMODITIES = [
    {"name": "Gold",        "symbol": "GC=F", "unit": "USD/oz"},
    {"name": "Silver",      "symbol": "SI=F", "unit": "USD/oz"},
    {"name": "Crude Oil",   "symbol": "CL=F", "unit": "USD/barrel"},
    {"name": "Natural Gas", "symbol": "NG=F", "unit": "USD/MMBtu"},
]

FALLBACK_TRENDING = [
    ("RELIANCE.NS",   "Reliance Industries"),
    ("TCS.NS",        "Tata Consultancy Services"),
    ("HDFCBANK.NS",   "HDFC Bank"),
    ("INFY.NS",       "Infosys"),
    ("ICICIBANK.NS",  "ICICI Bank"),
    ("SBIN.NS",       "State Bank of India"),
    ("TATAMOTORS.NS", "Tata Motors"),
    ("ZOMATO.NS",     "Zomato"),
]


def get_trending() -> dict:
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    stocks      = _fetch_trending_stocks()
    commodities = _fetch_commodities()

    result = {
        "trending_stocks":      stocks,
        "trending_commodities": commodities,
        "last_updated":         datetime.now(timezone.utc).isoformat(),
    }
    _cache["data"]       = result
    _cache["expires_at"] = now + CACHE_TTL
    return result


# ── Trending stocks ───────────────────────────────────────────

def _fetch_trending_stocks() -> list[dict]:
    try:
        result = _nse_most_active()
        if result:
            return result
    except Exception as e:
        print(f"[TrendingService] NSE trending failed: {e} — using Upstox fallback")

    try:
        result = _upstox_trending()
        if result:
            return result
    except Exception as e:
        print(f"[TrendingService] Upstox trending failed: {e} — using yfinance fallback")

    return _yfinance_trending()


def _nse_most_active() -> list[dict]:
    """Fetch from NSE most-active endpoint."""
    session = requests.Session()
    session.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    })
    session.get("https://www.nseindia.com", timeout=8)
    time.sleep(0.5)

    r = session.get(
        "https://www.nseindia.com/api/live-analysis-variations?index=vol",
        timeout=10,
    )
    r.raise_for_status()

    body = r.text.strip()
    if not body or body[0] not in ('{', '['):
        raise ValueError(f"NSE most-active returned non-JSON (bot block): {body[:80]!r}")

    data = r.json()
    rows = data.get("data", [])[:8]
    stocks = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym  = row.get("symbol", "").strip()
        if not sym:
            continue
        price = float(row.get("ltp", 0) or 0)
        chgp  = float(row.get("pChange", 0) or 0)
        vol   = int(row.get("tradedQuantity", 0) or 0)
        name  = row.get("meta", {}).get("companyName", sym) if isinstance(row.get("meta"), dict) else sym
        stocks.append({
            "name":       name,
            "symbol":     sym + ".NS",
            "price":      round(price, 2),
            "change_pct": round(chgp, 2),
            "direction":  "up" if chgp > 0 else "down" if chgp < 0 else "flat",
            "reason":     f"{'Up' if chgp>0 else 'Down'} {abs(chgp):.1f}% today" if abs(chgp) >= 2 else "High volume today",
        })
    return stocks


def _upstox_trending() -> list[dict]:
    from backend.services.upstox_service import load_token, symbol_to_key
    token = load_token()
    if not token:
        raise RuntimeError("No Upstox token")

    keys    = [symbol_to_key(sym) for sym, _ in FALLBACK_TRENDING if symbol_to_key(sym)]
    sym_map = {symbol_to_key(sym): (sym, name) for sym, name in FALLBACK_TRENDING if symbol_to_key(sym)}

    r = requests.get(
        "https://api.upstox.com/v2/market-quote/ltp",
        params={"instrument_key": ",".join(keys)},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=8,
    )
    r.raise_for_status()
    data = r.json().get("data", {})

    stocks = []
    for ikey, item in data.items():
        orig_key = ikey.replace(":", "|")
        sym_info = sym_map.get(orig_key)
        if not sym_info:
            continue
        sym, name  = sym_info
        price      = float(item.get("last_price", 0) or 0)
        close      = float(item.get("close_price", price) or price)
        chgp       = round(((price - close) / close * 100) if close else 0, 2)
        stocks.append({
            "name":       name,
            "symbol":     sym,
            "price":      round(price, 2),
            "change_pct": chgp,
            "direction":  "up" if chgp > 0 else "down" if chgp < 0 else "flat",
            "reason":     "Active trading today",
        })
    stocks.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return stocks[:8]


def _yfinance_trending() -> list[dict]:
    """yfinance fallback — uses get_price() (history-based, works with yfinance >= 0.2.61)."""
    from backend.services.yf_session import get_price
    stocks = []
    for sym, name in FALLBACK_TRENDING[:6]:
        try:
            data = get_price(sym)
            stocks.append({
                "name":       name,
                "symbol":     sym,
                "price":      data["price"],
                "change_pct": data["change_pct"],
                "direction":  data["direction"],
                "reason":     "Active trading today",
            })
        except Exception:
            continue
    return stocks


# ── Commodities ───────────────────────────────────────────────

_commodity_cache: dict = {"data": None, "expires_at": 0}
COMMODITY_TTL = 1800  # 30 minutes


def _fetch_commodities() -> list[dict]:
    now = time.time()
    if _commodity_cache["data"] and now < _commodity_cache["expires_at"]:
        return _commodity_cache["data"]

    results = []
    for c in COMMODITIES:
        price = _fetch_commodity_price(c["symbol"])
        results.append({
            "name":       c["name"],
            "symbol":     c["symbol"],
            "price":      price["price"],
            "unit":       c["unit"],
            "change_pct": price["change_pct"],
            "direction":  price["direction"],
        })

    if any(r["price"] > 0 for r in results):
        _commodity_cache["data"]       = results
        _commodity_cache["expires_at"] = now + COMMODITY_TTL

    return _commodity_cache["data"] or results


def _fetch_commodity_price(symbol: str) -> dict:
    """
    Uses get_price() which calls history(period='5d').
    This is reliable across yfinance versions unlike fast_info.
    """
    from backend.services.yf_session import get_price
    try:
        return get_price(symbol)
    except Exception as e:
        print(f"[TrendingService] Commodity {symbol} failed: {e}")
        return {"price": 0.0, "change_pct": 0.0, "direction": "flat"}


def invalidate_cache():
    _cache["data"]                 = None
    _cache["expires_at"]           = 0
    _commodity_cache["data"]       = None
    _commodity_cache["expires_at"] = 0