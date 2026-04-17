"""
NSE Direct Data Fetcher — Robust version
Handles NSE API format changes with multiple fallback strategies.

Priority for index data:
  1. Upstox Market Quote API (if access token available) — most reliable
  2. NSE India /api/allIndices endpoint
  3. NSE India /api/market-data-pre-open
  4. yfinance history as final fallback
"""

import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Session management ────────────────────────────────────────

_session        = None
_session_expiry = 0
SESSION_TTL     = 600   # 10 minutes

NSE_BASE    = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}


def _get_session() -> requests.Session:
    global _session, _session_expiry
    now = time.time()
    if _session and now < _session_expiry:
        return _session
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    try:
        session.get(NSE_BASE, timeout=10)
        time.sleep(0.5)
    except Exception:
        pass
    _session        = session
    _session_expiry = now + SESSION_TTL
    return session


def _safe_json(r: requests.Response) -> dict:
    """
    Parse JSON from a response, raising a clear error if the body is empty
    or non-JSON (e.g. an Akamai/bot-detection HTML page).
    NSE returns HTTP 200 with an empty or HTML body when it blocks a request —
    raise_for_status() passes silently, then r.json() crashes with
    'Expecting value: line 1 column 1 (char 0)'.  This catches that case early.
    """
    body = r.text.strip()
    if not body:
        raise ValueError(f"NSE returned empty body for {r.url} (IP blocked or bot-detection)")
    if body[0] not in ('{', '['):
        raise ValueError(
            f"NSE returned non-JSON body for {r.url} "
            f"(likely HTML bot-check page, starts with: {body[:80]!r})"
        )
    return r.json()


def _nse_get(endpoint: str) -> dict:
    """GET from NSE API with session cookie. Refreshes session on 401/403."""
    global _session_expiry
    session = _get_session()
    url = f"{NSE_BASE}{endpoint}"
    try:
        r = session.get(url, timeout=12)
        r.raise_for_status()
        return _safe_json(r)
    except (requests.HTTPError) as e:
        if e.response is not None and e.response.status_code in (401, 403):
            _session_expiry = 0   # force session refresh
            session = _get_session()
            r = session.get(url, timeout=12)
            r.raise_for_status()
            return _safe_json(r)
        raise


# ── Safe helpers ──────────────────────────────────────────────

def _sf(val, default=0.0) -> float:
    """Safe float — never raises."""
    try:
        v = float(val)
        return v if v == v else default  # NaN check
    except (TypeError, ValueError):
        return default


def _parse_index_row(row) -> Optional[dict]:
    """
    Parse one row from NSE /api/allIndices response.
    Handles both dict format and unexpected formats defensively.
    """
    if not isinstance(row, dict):
        return None

    name = row.get("index") or row.get("indexSymbol") or ""
    last = _sf(row.get("last") or row.get("lastPrice") or row.get("indexValue"))
    prev = _sf(row.get("previousClose") or row.get("previousDay") or last)
    chg  = round(last - prev, 2)
    chgp = _sf(row.get("percentChange") or row.get("pChange"))

    if last == 0:
        return None   # skip rows with no data

    return {
        "index":          name,
        "last":           last,
        "previousClose":  prev,
        "change":         chg,
        "percentChange":  chgp,
        "high":           _sf(row.get("high") or row.get("yearHigh") or last),
        "low":            _sf(row.get("low")  or row.get("yearLow")  or last),
    }


# ── Index data ────────────────────────────────────────────────

def get_all_indices() -> list[dict]:
    """
    Fetch all NSE indices with multi-endpoint fallback.
    Always returns a list of parsed dicts (never strings).
    """
    # Try endpoint 1: /api/allIndices
    try:
        data = _nse_get("/api/allIndices")
        rows = data.get("data", [])
        parsed = [_parse_index_row(r) for r in rows]
        parsed = [p for p in parsed if p]   # remove None
        if parsed:
            return parsed
    except Exception as e:
        print(f"[NseDirect] allIndices failed: {e}")

    # Try endpoint 2: /api/market-data-pre-open?key=ALL
    try:
        data = _nse_get("/api/market-data-pre-open?key=ALL")
        rows = data.get("data", [])
        parsed = []
        for r in rows:
            # pre-open format: { metadata: {symbol, lastPrice, ...} }
            meta = r.get("metadata", r) if isinstance(r, dict) else {}
            p = _parse_index_row(meta)
            if p:
                parsed.append(p)
        if parsed:
            return parsed
    except Exception as e:
        print(f"[NseDirect] pre-open failed: {e}")

    return []


def get_index(index_name: str) -> Optional[dict]:
    """Get a specific index by name from the indices list."""
    indices = get_all_indices()
    name_upper = index_name.upper()
    for idx in indices:
        if idx.get("index", "").upper() == name_upper:
            last = idx["last"]
            prev = idx["previousClose"]
            chg  = round(last - prev, 2)
            chgp = round(idx["percentChange"], 2)
            return {
                "name":           index_name,
                "current":        round(last, 2),
                "previous_close": round(prev, 2),
                "change":         chg,
                "change_pct":     chgp,
                "direction":      "up" if chg > 0 else "down" if chg < 0 else "flat",
                "day_high":       idx["high"],
                "day_low":        idx["low"],
                "last_updated":   datetime.now(timezone.utc).isoformat(),
                "source":         "nse_direct",
            }
    return None


# ── Stock quote ───────────────────────────────────────────────

def get_quote(symbol: str) -> dict:
    """
    Get real-time quote for an NSE stock.
    Tries Upstox first (if token available), then NSE direct.
    """
    symbol_clean = symbol.replace(".NS", "").replace(".BO", "").upper()

    # Try Upstox market quote first (most reliable)
    try:
        return _get_quote_upstox(symbol)
    except Exception:
        pass

    # Try NSE direct
    try:
        data = _nse_get(f"/api/quote-equity?symbol={symbol_clean}")
        price_info = data.get("priceInfo", {})
        meta       = data.get("metadata", {})
        info       = data.get("info", {})
        securities = data.get("securityInfo", {})

        price      = _sf(price_info.get("lastPrice"))
        prev_close = _sf(price_info.get("previousClose"), price)
        change     = round(price - prev_close, 2)
        change_pct = round(_sf(price_info.get("pChange")), 2)
        idhl       = price_info.get("intraDayHighLow", {})

        if price == 0:
            raise ValueError("Zero price from NSE")

        return {
            "symbol":         symbol,
            "name":           info.get("companyName", symbol_clean),
            "price":          round(price, 2),
            "previous_close": round(prev_close, 2),
            "change":         change,
            "change_pct":     change_pct,
            "direction":      "up" if change > 0 else "down" if change < 0 else "flat",
            "open":           _sf(price_info.get("open")),
            "day_high":       _sf(idhl.get("max") if isinstance(idhl, dict) else 0),
            "day_low":        _sf(idhl.get("min") if isinstance(idhl, dict) else 0),
            "week_52_high":   _sf((price_info.get("weekHighLow") or {}).get("max")),
            "week_52_low":    _sf((price_info.get("weekHighLow") or {}).get("min")),
            "volume":         int(_sf(securities.get("tradedVolume"))),
            "pe_ratio":       _sf(meta.get("pdSymbolPe")) or None,
            "market_cap":     None,
            "sector":         meta.get("industry", ""),
            "last_updated":   datetime.now(timezone.utc).isoformat(),
            "source":         "nse_direct",
        }
    except Exception as e:
        raise RuntimeError(f"get_quote failed for {symbol}: {e}")


def _get_quote_upstox(symbol: str) -> dict:
    """
    Fetch quote from Upstox Market Quote API.
    Requires valid access token in upstox_service.
    """
    from backend.services.upstox_service import (
        load_token, symbol_to_key
    )
    token = load_token()
    if not token:
        raise RuntimeError("No Upstox token")

    key = symbol_to_key(symbol)
    if not key:
        raise RuntimeError(f"No Upstox key for {symbol}")

    r = requests.get(
        "https://api.upstox.com/v2/market-quote/ltp",
        params={"instrument_key": key},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=8,
    )
    r.raise_for_status()
    data = r.json().get("data", {})

    # Upstox returns keyed by instrument_key
    item = data.get(key.replace("|", ":")) or next(iter(data.values()), {})
    ltp  = _sf(item.get("last_price"))
    if ltp == 0:
        raise ValueError("Zero LTP from Upstox")

    return {
        "symbol":         symbol,
        "name":           symbol.replace(".NS", ""),
        "price":          round(ltp, 2),
        "previous_close": round(_sf(item.get("close_price"), ltp), 2),
        "change":         round(ltp - _sf(item.get("close_price"), ltp), 2),
        "change_pct":     round(_sf(item.get("net_change")), 2),
        "direction":      "up" if _sf(item.get("net_change")) > 0 else "down",
        "open":           _sf(item.get("open_price")),
        "day_high":       _sf(item.get("high_price")),
        "day_low":        _sf(item.get("low_price")),
        "week_52_high":   None,
        "week_52_low":    None,
        "volume":         int(_sf(item.get("volume"))),
        "pe_ratio":       None,
        "market_cap":     None,
        "sector":         "",
        "last_updated":   datetime.now(timezone.utc).isoformat(),
        "source":         "upstox",
    }


# ── Gainers / Losers ──────────────────────────────────────────

def get_gainers(count: int = 5) -> list[dict]:
    try:
        return _parse_movers(
            _nse_get("/api/live-analysis-variations?index=gainers"), "gainer"
        )[:count]
    except Exception as e:
        print(f"[NseDirect] gainers failed: {e}")
        return []


def get_losers(count: int = 5) -> list[dict]:
    try:
        return _parse_movers(
            _nse_get("/api/live-analysis-variations?index=loosers"), "loser"
        )[:count]
    except Exception as e:
        print(f"[NseDirect] losers failed: {e}")
        return []


def _parse_movers(data: dict, side: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    rows   = data.get("data", [])
    movers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            sym = row.get("symbol", "").strip()
            if not sym:
                continue
            price      = _sf(row.get("ltp") or row.get("lastPrice"))
            change_pct = _sf(row.get("pChange") or row.get("perChange"))
            name       = sym
            if isinstance(row.get("meta"), dict):
                name = row["meta"].get("companyName", sym)
            movers.append({
                "name":       name,
                "symbol":     sym + ".NS",
                "price":      round(price, 2),
                "change_pct": round(change_pct, 2),
                "direction":  "up" if change_pct > 0 else "down",
            })
        except Exception:
            continue
    movers.sort(key=lambda x: x["change_pct"], reverse=(side == "gainer"))
    return movers


# ── Historical data ───────────────────────────────────────────

def get_history(symbol: str, days: int = 30) -> list[dict]:
    """OHLCV history for a stock from NSE."""
    symbol   = symbol.replace(".NS", "").replace(".BO", "").upper()
    to_dt    = datetime.now()
    from_dt  = to_dt - timedelta(days=days + 10)
    from_str = from_dt.strftime("%d-%m-%Y")
    to_str   = to_dt.strftime("%d-%m-%Y")

    try:
        endpoint = (
            f"/api/historical/cm/equity"
            f"?symbol={symbol}&series=[%22EQ%22]"
            f"&from={from_str}&to={to_str}"
        )
        data = _nse_get(endpoint)
        rows = data.get("data", [])
        bars = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                dt  = datetime.strptime(row.get("CH_TIMESTAMP", ""), "%Y-%m-%d")
                ts  = int(dt.replace(tzinfo=timezone.utc).timestamp())
                bars.append({
                    "time":   ts,
                    "open":   _sf(row.get("CH_OPENING_PRICE")),
                    "high":   _sf(row.get("CH_TRADE_HIGH_PRICE")),
                    "low":    _sf(row.get("CH_TRADE_LOW_PRICE")),
                    "close":  _sf(row.get("CH_CLOSING_PRICE")),
                    "volume": int(_sf(row.get("CH_TOT_TRADED_QTY"))),
                })
            except Exception:
                continue
        return sorted(bars, key=lambda x: x["time"])
    except Exception:
        return []