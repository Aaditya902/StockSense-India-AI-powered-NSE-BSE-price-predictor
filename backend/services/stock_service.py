"""
Service: Stock Detail
Fetches current price, OHLCV chart data, and company info for a stock.

Data source : yfinance (free, no key needed)
Called by   : GET /stock/{symbol}
"""

import yfinance as yf
from datetime import datetime, timezone
from typing import Optional


# ── Period → yfinance interval mapping ───────────────────────
# Controls chart bar granularity shown to user

PERIOD_MAP = {
    "1d":  {"period": "1d",  "interval": "5m"},    # 5-min bars for intraday
    "1w":  {"period": "5d",  "interval": "15m"},   # 15-min bars for 1 week
    "1m":  {"period": "1mo", "interval": "1d"},    # daily bars for 1 month
    "3m":  {"period": "3mo", "interval": "1d"},    # daily bars for 3 months
}
DEFAULT_PERIOD = "1m"


# ── Main functions ────────────────────────────────────────────

def get_stock_detail(symbol: str, chart_period: str = DEFAULT_PERIOD) -> dict:
    """
    Fetch full stock detail:
      - current price + change
      - company info (PE, EPS, market cap, etc.)
      - OHLCV chart data for the requested period

    symbol: NSE format e.g. RELIANCE.NS
    chart_period: "1d" | "1w" | "1m" | "3m"
    """
    symbol      = _normalise_symbol(symbol)
    ticker      = yf.Ticker(symbol)
    period_cfg  = PERIOD_MAP.get(chart_period, PERIOD_MAP[DEFAULT_PERIOD])

    # Fetch price, info, and history in parallel calls
    price_data  = _fetch_price(ticker, symbol)
    company     = _fetch_company_info(ticker, symbol)
    chart_data  = _fetch_chart(ticker, period_cfg)

    return {
        "symbol":        symbol,
        "current_price": price_data["current_price"],
        "change":        price_data["change"],
        "change_pct":    price_data["change_pct"],
        "direction":     price_data["direction"],
        "company":       company,
        "chart_data":    chart_data,
        "chart_period":  chart_period,
        "last_updated":  datetime.now(timezone.utc).isoformat(),
    }


def get_current_price(symbol: str) -> dict:
    """
    Lightweight price-only fetch — used by the WebSocket live feed.
    Returns only price fields, no chart or company info.
    """
    symbol = _normalise_symbol(symbol)
    ticker = yf.Ticker(symbol)
    return _fetch_price(ticker, symbol)


# ── Internal fetchers ─────────────────────────────────────────

def _safe_float(val):
    """Return float or None — never raises, treats 0 as missing."""
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


def _fetch_price(ticker: yf.Ticker, symbol: str) -> dict:
    """
    Fetch current price using 3-strategy cascade.
    Strategy 1: fast_info (live, works during market hours)
    Strategy 2: history last close (works after hours)
    Strategy 3: ticker.info regularMarketPrice (slowest, most reliable)
    """
    current_price  = None
    previous_close = None

    # Strategy 1 — fast_info
    try:
        fi             = ticker.fast_info
        current_price  = _safe_float(fi.last_price)
        previous_close = _safe_float(fi.previous_close)
    except Exception:
        pass

    # Strategy 2 — history
    if current_price is None:
        try:
            hist = ticker.history(period="5d", interval="1d")
            if not hist.empty:
                closes = hist["Close"].dropna().tolist()
                if closes:
                    current_price  = current_price  or _safe_float(closes[-1])
                    previous_close = previous_close or _safe_float(closes[-2] if len(closes) >= 2 else closes[-1])
        except Exception:
            pass

    # Strategy 3 — ticker.info
    if current_price is None:
        try:
            info           = ticker.info
            current_price  = _safe_float(info.get("regularMarketPrice") or info.get("previousClose"))
            previous_close = _safe_float(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        except Exception:
            pass

    if current_price is None:
        raise RuntimeError(f"Price fetch failed for {symbol} — no data from yfinance")

    current_price  = round(current_price, 2)
    previous_close = round(previous_close or current_price, 2)
    change         = round(current_price - previous_close, 2)
    change_pct     = round((change / previous_close) * 100, 2) if previous_close else 0.0

    return {
        "symbol":         symbol,
        "current_price":  current_price,
        "previous_close": previous_close,
        "change":         change,
        "change_pct":     change_pct,
        "direction":      "up" if change > 0 else "down" if change < 0 else "flat",
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }


def _fetch_company_info(ticker: yf.Ticker, symbol: str) -> dict:
    """
    Fetch fundamental company data.
    Uses ticker.info — slightly slower but contains all fundamentals.
    Safe: every field has a fallback of None if yfinance doesn't return it.
    """
    try:
        info = ticker.info
    except Exception:
        info = {}

    def _safe_float(key: str) -> Optional[float]:
        val = info.get(key)
        try:
            return round(float(val), 2) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _safe_int(key: str) -> Optional[int]:
        val = info.get(key)
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    # Market cap in crores (Indian convention)
    market_cap_raw    = _safe_float("marketCap")
    market_cap_crores = round(market_cap_raw / 1e7, 2) if market_cap_raw else None

    return {
        "name":              info.get("longName") or info.get("shortName") or symbol,
        "symbol":            symbol,
        "sector":            info.get("sector", "N/A"),
        "industry":          info.get("industry", "N/A"),
        "website":           info.get("website"),
        "description":       (info.get("longBusinessSummary") or "")[:300],  # cap length

        # Valuation
        "market_cap":        market_cap_raw,
        "market_cap_crores": market_cap_crores,
        "pe_ratio":          _safe_float("trailingPE"),
        "pb_ratio":          _safe_float("priceToBook"),
        "eps":               _safe_float("trailingEps"),

        # Dividends
        "dividend_yield":    _safe_float("dividendYield"),
        "dividend_rate":     _safe_float("dividendRate"),

        # Price range
        "week_52_high":      _safe_float("fiftyTwoWeekHigh"),
        "week_52_low":       _safe_float("fiftyTwoWeekLow"),
        "day_high":          _safe_float("dayHigh"),
        "day_low":           _safe_float("dayLow"),

        # Volume
        "volume":            _safe_int("volume"),
        "avg_volume":        _safe_int("averageVolume"),

        # Analyst targets
        "target_mean_price": _safe_float("targetMeanPrice"),
        "recommendation":    info.get("recommendationKey", "N/A"),
    }


def _fetch_chart(ticker: yf.Ticker, period_cfg: dict) -> list[dict]:
    """
    Fetch OHLCV bars for the chart.
    Returns a list of bars the frontend can feed directly to Lightweight Charts.
    """
    try:
        hist = ticker.history(
            period   = period_cfg["period"],
            interval = period_cfg["interval"],
            auto_adjust = True,
        )
    except Exception as e:
        raise RuntimeError(f"Chart fetch failed: {e}")

    if hist.empty:
        return []

    bars = []
    for row in hist.itertuples():
        try:
            # Lightweight Charts expects UNIX timestamp in seconds
            ts = int(row.Index.timestamp())
            bars.append({
                "time":   ts,
                "open":   round(float(row.Open),   2),
                "high":   round(float(row.High),   2),
                "low":    round(float(row.Low),    2),
                "close":  round(float(row.Close),  2),
                "volume": int(row.Volume),
            })
        except (AttributeError, ValueError, TypeError):
            continue

    return bars


# ── Utility ───────────────────────────────────────────────────

def _normalise_symbol(symbol: str) -> str:
    """
    Ensure symbol is in yfinance NSE format.
    'RELIANCE'   → 'RELIANCE.NS'
    'reliance'   → 'RELIANCE.NS'
    'RELIANCE.NS' → 'RELIANCE.NS'  (unchanged)
    """
    symbol = symbol.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
    return symbol