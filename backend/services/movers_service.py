"""
Service: Market Movers
Fetches top gainers and top losers from NSE India.

Primary  : NSE India public API (no key needed, needs cookie session)
Fallback : yfinance — fetches Nifty 50 stocks, sorts by % change
Cache    : 5-minute in-memory cache (gainers/losers don't change every second)

Called by: GET /market/movers
"""

import time
import requests
import yfinance as yf
from backend.services.yf_session import get_ticker
from datetime import datetime, timezone


# ── In-memory cache ───────────────────────────────────────────

_cache: dict = {
    "data":       None,
    "expires_at": 0,       # Unix timestamp
}
CACHE_TTL = 300            # 5 minutes


# ── NSE India API config ──────────────────────────────────────

NSE_BASE    = "https://www.nseindia.com"
NSE_GAINERS = f"{NSE_BASE}/api/live-analysis-variations?index=gainers"
NSE_LOSERS  = f"{NSE_BASE}/api/live-analysis-variations?index=loosers"  # NSE spells it this way

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         NSE_BASE + "/",
    "Connection":      "keep-alive",
}

# Nifty 50 constituent symbols for yfinance fallback
NIFTY50_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "HCLTECH.NS", "WIPRO.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATAMOTORS.NS",
    "ULTRACEMCO.NS", "NESTLEIND.NS", "POWERGRID.NS", "NTPC.NS", "TECHM.NS",
    "BAJAJFINSV.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "HINDALCO.NS", "DRREDDY.NS",
    "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "GRASIM.NS",
    "INDUSINDBK.NS", "BRITANNIA.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
    "ONGC.NS", "APOLLOHOSP.NS", "SHREECEM.NS", "TATACONSUM.NS", "DIVISLAB.NS",
    "DMART.NS", "TRENT.NS", "ZOMATO.NS", "LTTS.NS", "PERSISTENT.NS",
]


# ── Main function called by router ────────────────────────────

def get_market_movers() -> dict:
    """
    Returns top 5 gainers and top 5 losers.
    Uses cache — only fetches fresh data every 5 minutes.
    """
    now = time.time()

    # Return cached result if still fresh
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    # Try NSE India first
    try:
        result = _fetch_from_nse()
        if result and len(result["gainers"]) > 0:
            _cache["data"] = result
            _cache["expires_at"] = now + CACHE_TTL
            return result
    except Exception as e:
        print(f"[MoversService] NSE API failed: {e} — trying yfinance fallback")

    # Fallback to yfinance
    try:
        result = _fetch_from_yfinance()
        _cache["data"] = result
        _cache["expires_at"] = now + CACHE_TTL
        return result
    except Exception as e:
        print(f"[MoversService] yfinance fallback also failed: {e}")
        return _empty_response()


# ── NSE India fetcher ─────────────────────────────────────────

def _fetch_from_nse() -> dict:
    """
    Two-step fetch:
    1. GET nseindia.com homepage → grab session cookies
    2. GET gainers/losers API with those cookies
    """
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    # Step 1 — get session cookie
    session.get(NSE_BASE, timeout=10)
    time.sleep(0.5)   # brief pause — NSE rate-limits fast requests

    # Step 2 — fetch gainers
    r_gain = session.get(NSE_GAINERS, timeout=10)
    r_gain.raise_for_status()
    gain_data = r_gain.json()

    # Step 3 — fetch losers
    r_loss = session.get(NSE_LOSERS, timeout=10)
    r_loss.raise_for_status()
    loss_data = r_loss.json()

    gainers = _parse_nse_movers(gain_data, side="gainer")[:5]
    losers  = _parse_nse_movers(loss_data, side="loser")[:5]

    return {
        "gainers":      gainers,
        "losers":       losers,
        "source":       "nse",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _parse_nse_movers(data: dict, side: str) -> list[dict]:
    """
    Parse NSE API response into our standard mover format.
    NSE returns data under 'data' key with 'symbol', 'ltp', 'pChange' fields.
    """
    rows = data.get("data", [])
    movers = []

    for row in rows:
        try:
            symbol = row.get("symbol", "").strip()
            if not symbol:
                continue                          # skip rows with no symbol
            name       = row.get("meta", {}).get("companyName", symbol) if isinstance(row.get("meta"), dict) else symbol
            price      = float(row.get("ltp", row.get("lastPrice", 0)))
            change_pct = float(row.get("pChange", row.get("perChange", 0)))

            movers.append({
                "name":       name,
                "symbol":     symbol + ".NS",
                "price":      round(price, 2),
                "change_pct": round(change_pct, 2),
                "direction":  "up" if change_pct > 0 else "down",
                "source":     "nse",
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Sort correctly by magnitude
    reverse = side == "gainer"
    movers.sort(key=lambda x: x["change_pct"], reverse=reverse)
    return movers


# ── yfinance fallback ─────────────────────────────────────────

# ── yfinance fallback ─────────────────────────────────────────

def _fetch_from_yfinance() -> dict:
    """
    Fetch top Nifty 50 stocks individually with rate limiting and sort by % change.
    Replaces the batch yf.Tickers call which caused 429 errors.
    """
    from backend.services.yf_session import get_ticker

    results = []
    for symbol in NIFTY50_SYMBOLS[:15]:   # limit to 15 to avoid rate limits
        try:
            ticker = get_ticker(symbol)
            fi     = ticker.fast_info

            price = float(fi.last_price or 0)
            prev  = float(fi.previous_close or price)

            # Fallback to history if fast_info gives zeros
            if price == 0:
                hist = ticker.history(period="5d", interval="1d")
                if not hist.empty:
                    closes = hist["Close"].dropna().tolist()
                    price  = float(closes[-1]) if closes else 0
                    prev   = float(closes[-2]) if len(closes) >= 2 else price

            if price == 0:
                continue

            change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0.0
            results.append({
                "name":       symbol.replace(".NS", ""),
                "symbol":     symbol,
                "price":      round(price, 2),
                "change_pct": change_pct,
                "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                "source":     "yfinance",
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["change_pct"], reverse=True)
    return {
        "gainers":      results[:5],
        "losers":       results[-5:][::-1] if len(results) >= 5 else results,
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