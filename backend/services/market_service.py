"""
Market Service
Fetches Sensex, Nifty50, BankNifty.

Priority:
  1. Upstox Market Quote API (if token available) — real-time
  2. NSE direct /api/allIndices
  3. yfinance history (last close)
"""

import time
from datetime import datetime, timezone
from typing import Optional

_cache: dict = {"data": None, "expires_at": 0}
CACHE_TTL = 120  # 2 minutes — reduces yfinance 429


def _sf(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if v == v and v != 0.0 else default
    except (TypeError, ValueError):
        return default


def get_market_overview() -> dict:
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    result = None

    # Strategy 1: Upstox index quotes
    try:
        result = _fetch_from_upstox()
    except Exception as e:
        print(f"[MarketService] Upstox failed: {e}")

    # Strategy 2: NSE direct
    if not result or _all_zero(result):
        try:
            result = _fetch_from_nse()
        except Exception as e:
            print(f"[MarketService] NSE direct failed: {e}")

    # Strategy 3: yfinance
    if not result or _all_zero(result):
        try:
            result = _fetch_from_yfinance()
        except Exception as e:
            print(f"[MarketService] yfinance failed: {e}")

    if not result:
        result = {
            "sensex":    _zero_index("BSE Sensex",  "^BSESN"),
            "nifty50":   _zero_index("Nifty 50",    "^NSEI"),
            "banknifty": _zero_index("Bank Nifty",  "^NSEBANK"),
        }

    result["last_updated"] = datetime.now(timezone.utc).isoformat()
    _cache["data"]       = result
    _cache["expires_at"] = now + CACHE_TTL
    return result


def _all_zero(result: dict) -> bool:
    """True if all index values are zero — means fetch failed."""
    return all(
        result.get(k, {}).get("current", 0) == 0
        for k in ["sensex", "nifty50", "banknifty"]
    )


def _fetch_from_upstox() -> dict:
    """Fetch index data from Upstox Market Quote API."""
    from backend.services.upstox_service import load_token
    import requests

    token = load_token()
    if not token:
        raise RuntimeError("No Upstox token")

    INDEX_KEYS = {
        "sensex":    "BSE_INDEX|SENSEX",
        "nifty50":   "NSE_INDEX|Nifty 50",
        "banknifty": "NSE_INDEX|Nifty Bank",
    }
    DISPLAY = {
        "sensex":    ("BSE Sensex",  "^BSESN"),
        "nifty50":   ("Nifty 50",    "^NSEI"),
        "banknifty": ("Bank Nifty",  "^NSEBANK"),
    }

    keys_str = ",".join(INDEX_KEYS.values())
    r = requests.get(
        "https://api.upstox.com/v2/market-quote/ltp",
        params={"instrument_key": keys_str},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=8,
    )
    r.raise_for_status()
    data = r.json().get("data", {})

    result = {}
    for key, ikey in INDEX_KEYS.items():
        display_name, symbol = DISPLAY[key]
        # Upstox returns keys with : instead of |
        item = data.get(ikey.replace("|", ":")) or {}
        ltp  = _sf(item.get("last_price"))
        cp   = _sf(item.get("close_price"), ltp)
        chg  = round(ltp - cp, 2)
        chgp = round((chg / cp) * 100, 2) if cp else 0.0

        result[key] = {
            "name":           display_name,
            "symbol":         symbol,
            "current":        round(ltp, 2),
            "previous_close": round(cp,  2),
            "change":         chg,
            "change_pct":     chgp,
            "direction":      "up" if chg > 0 else "down" if chg < 0 else "flat",
            "day_high":       _sf(item.get("high_price"), ltp),
            "day_low":        _sf(item.get("low_price"),  ltp),
            "last_updated":   datetime.now(timezone.utc).isoformat(),
        }
    return result


def _fetch_from_nse() -> dict:
    """Fetch from NSE direct /api/allIndices."""
    from backend.services.nse_direct import get_all_indices

    indices = get_all_indices()
    if not indices:
        raise RuntimeError("NSE returned empty indices list")

    idx_map = {i.get("index", "").upper(): i for i in indices}

    TARGETS = {
        "sensex":    (["S&P BSE SENSEX", "SENSEX"],    "BSE Sensex",  "^BSESN"),
        "nifty50":   (["NIFTY 50"],                    "Nifty 50",    "^NSEI"),
        "banknifty": (["NIFTY BANK", "BANK NIFTY"],    "Bank Nifty",  "^NSEBANK"),
    }

    result = {}
    for key, (names, display_name, symbol) in TARGETS.items():
        idx = {}
        for n in names:
            idx = idx_map.get(n.upper(), {})
            if idx:
                break

        last = _sf(idx.get("last"))
        prev = _sf(idx.get("previousClose"), last)
        chg  = round(last - prev, 2)
        chgp = round(_sf(idx.get("percentChange")), 2)

        result[key] = {
            "name":           display_name,
            "symbol":         symbol,
            "current":        round(last, 2),
            "previous_close": round(prev, 2),
            "change":         chg,
            "change_pct":     chgp,
            "direction":      "up" if chg > 0 else "down" if chg < 0 else "flat",
            "day_high":       _sf(idx.get("high"), last),
            "day_low":        _sf(idx.get("low"),  last),
            "last_updated":   datetime.now(timezone.utc).isoformat(),
        }
    return result


def _fetch_from_yfinance() -> dict:
    """yfinance history fallback — uses last close price."""
    from backend.services.yf_session import get_ticker

    INDICES = {
        "sensex":    ("^BSESN",   "BSE Sensex"),
        "nifty50":   ("^NSEI",    "Nifty 50"),
        "banknifty": ("^NSEBANK", "Bank Nifty"),
    }
    result = {}
    for key, (yf_sym, name) in INDICES.items():
        current = prev = 0.0
        try:
            hist = get_ticker(yf_sym).history(period="5d", interval="1d")
            if not hist.empty:
                closes = hist["Close"].dropna().tolist()
                current = round(float(closes[-1]), 2) if closes else 0.0
                prev    = round(float(closes[-2]), 2) if len(closes) >= 2 else current
        except Exception:
            pass
        chg  = round(current - prev, 2)
        chgp = round((chg / prev) * 100, 2) if prev else 0.0
        result[key] = {
            "name": name, "symbol": yf_sym,
            "current": current, "previous_close": prev,
            "change": chg, "change_pct": chgp,
            "direction": "up" if chg > 0 else "down" if chg < 0 else "flat",
            "day_high": current, "day_low": current,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    return result


# History cache — separate from overview cache
_hist_cache: dict = {}
HIST_CACHE_TTL = 3600   # 1 hour — index history doesn't change minute by minute


def get_index_history(index_key: str, period: str = "1mo") -> list[dict]:
    """Index price history for sparkline charts. Cached for 1 hour."""
    cache_key = f"{index_key}_{period}"
    now       = time.time()

    if cache_key in _hist_cache and now < _hist_cache[cache_key]["expires_at"]:
        return _hist_cache[cache_key]["data"]

    # Try Upstox historical data first (no rate limits)
    try:
        data = _fetch_history_upstox(index_key, period)
        if data:
            _hist_cache[cache_key] = {"data": data, "expires_at": now + HIST_CACHE_TTL}
            return data
    except Exception as e:
        print(f"[MarketService] Upstox history failed for {index_key}: {e}")

    # yfinance fallback
    YF_MAP = {"sensex": "^BSESN", "nifty50": "^NSEI", "banknifty": "^NSEBANK"}
    yf_sym = YF_MAP.get(index_key, "^NSEI")
    try:
        from backend.services.yf_session import get_ticker
        hist = get_ticker(yf_sym).history(period=period, interval="1d")
        if not hist.empty:
            data = [
                {"date": str(row.Index.date()), "close": round(float(row.Close), 2),
                 "open": round(float(row.Open), 2), "high": round(float(row.High), 2),
                 "low":  round(float(row.Low),  2)}
                for row in hist.itertuples()
                if row.Close and float(row.Close) > 0
            ]
            if data:
                _hist_cache[cache_key] = {"data": data, "expires_at": now + HIST_CACHE_TTL}
                return data
    except Exception as e:
        print(f"[MarketService] history failed for {index_key}: {e}")

    # Return last cached even if stale
    return _hist_cache.get(cache_key, {}).get("data", [])


def _fetch_history_upstox(index_key: str, period: str) -> list[dict]:
    """Fetch index history from Upstox historical data API."""
    from backend.services.upstox_service import load_token
    import requests, datetime

    token = load_token()
    if not token:
        raise RuntimeError("No token")

    KEY_MAP = {
        "sensex":    "BSE_INDEX|SENSEX",
        "nifty50":   "NSE_INDEX|Nifty 50",
        "banknifty": "NSE_INDEX|Nifty Bank",
    }
    ikey = KEY_MAP.get(index_key)
    if not ikey:
        raise ValueError(f"Unknown index: {index_key}")

    DAYS_MAP = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90}
    days   = DAYS_MAP.get(period, 30)
    to_dt  = datetime.date.today()
    fr_dt  = to_dt - datetime.timedelta(days=days + 10)

    r = requests.get(
        "https://api.upstox.com/v2/historical-candle/" + ikey.replace("|", "%7C") + "/day/" +
        to_dt.strftime("%Y-%m-%d") + "/" + fr_dt.strftime("%Y-%m-%d"),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=10,
    )
    r.raise_for_status()
    candles = r.json().get("data", {}).get("candles", [])
    bars    = []
    for c in candles:
        try:
            # Upstox candle: [timestamp, open, high, low, close, volume, oi]
            bars.append({
                "date":  c[0][:10],
                "open":  round(float(c[1]), 2),
                "high":  round(float(c[2]), 2),
                "low":   round(float(c[3]), 2),
                "close": round(float(c[4]), 2),
            })
        except Exception:
            continue
    return sorted(bars, key=lambda x: x["date"])


def _zero_index(name: str, symbol: str) -> dict:
    return {
        "name": name, "symbol": symbol,
        "current": 0.0, "previous_close": 0.0,
        "change": 0.0, "change_pct": 0.0, "direction": "flat",
        "day_high": 0.0, "day_low": 0.0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }