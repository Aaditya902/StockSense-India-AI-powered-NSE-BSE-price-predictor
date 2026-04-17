"""
Instruments Service
Fetches the complete list of all NSE and BSE listed stocks from Upstox.

Replaces:
  - data/nse_stocks.json (hardcoded 158 stocks)
  - INSTRUMENT_KEYS dict in upstox_service.py (hardcoded 50 stocks)

Upstox Instruments API:
  GET https://api.upstox.com/v2/option/chain (not this)
  GET https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
  GET https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz

  These are public JSON files — no authentication needed.
  They contain every listed instrument with name, symbol, ISIN, instrument_key.

Cache strategy:
  - Download once at server startup
  - Cache in memory + save to instruments_cache.json
  - Refresh every 24 hours (new listings / delistings)
  - Falls back to cached file if download fails

Usage:
  from backend.services.instruments import get_all_stocks, search_stocks, symbol_to_key
"""

import os
import json
import time
import gzip
import requests
import io
from datetime import datetime, timezone
from typing import Optional

# ── Cache ─────────────────────────────────────────────────────

_cache: dict = {
    "stocks":      [],        # list of all stock dicts
    "by_symbol":   {},        # RELIANCE.NS → stock dict
    "by_key":      {},        # NSE_EQ|INE002A01018 → stock dict
    "by_isin":     {},        # INE002A01018 → stock dict
    "loaded_at":   0,
}

CACHE_FILE = "instruments_cache.json"
CACHE_TTL  = 86400   # 24 hours

# Upstox public instrument files (no auth needed)
INSTRUMENT_URLS = {
    "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
}


# ── Main loader ───────────────────────────────────────────────

def load_instruments(force: bool = False) -> bool:
    """
    Load all instruments into memory.
    Downloads from Upstox if cache is stale or force=True.
    Returns True if loaded successfully.
    """
    global _cache

    now = time.time()

    # Return cached if fresh
    if not force and _cache["loaded_at"] and now - _cache["loaded_at"] < CACHE_TTL:
        return True

    # Try loading from local file first
    if not force and _load_from_file():
        return True

    # Download fresh from Upstox
    return _download_and_cache()


def _download_and_cache() -> bool:
    """Download instrument files from Upstox and build lookup indexes."""
    global _cache

    all_instruments = []

    for exchange, url in INSTRUMENT_URLS.items():
        try:
            print(f"[Instruments] Downloading {exchange} instrument list...")
            r = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Encoding": "gzip",
            })
            r.raise_for_status()

            # Decompress gzip
            with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as gz:
                data = json.loads(gz.read().decode("utf-8"))

            # Filter to equity only
            equities = [
                inst for inst in data
                if isinstance(inst, dict)
                and inst.get("instrument_type") in ("EQUITY", "EQ", "BE", "SM")
                and inst.get("trading_symbol")
            ]

            print(f"[Instruments] {exchange}: {len(equities)} equity instruments")
            all_instruments.extend(equities)

        except Exception as e:
            print(f"[Instruments] Failed to download {exchange}: {e}")

    if not all_instruments:
        print("[Instruments] Download failed — falling back to cached data")
        return _load_from_file()

    _build_indexes(all_instruments)
    _save_to_file(all_instruments)
    return True


def _build_indexes(raw_instruments: list) -> None:
    """Build fast lookup indexes from raw instrument list."""
    global _cache

    stocks     = []
    by_symbol  = {}
    by_key     = {}
    by_isin    = {}

    for inst in raw_instruments:
        try:
            # Normalise fields across NSE and BSE formats
            trading_sym  = (inst.get("trading_symbol") or "").strip().upper()
            name         = (inst.get("name") or inst.get("company_name") or trading_sym).strip()
            isin         = (inst.get("isin") or "").strip()
            exchange     = (inst.get("exchange") or "").strip()
            instrument_key = inst.get("instrument_key") or f"{exchange}|{isin}"
            short_name   = (inst.get("short_name") or name)[:60]

            if not trading_sym or not name:
                continue

            # Build NSE/BSE yfinance-style symbol
            if "NSE" in exchange.upper():
                yf_symbol = trading_sym + ".NS"
                exch_label = "NSE"
            elif "BSE" in exchange.upper():
                yf_symbol = trading_sym + ".BO"
                exch_label = "BSE"
            else:
                continue

            # Determine sector from instrument type or series
            series    = inst.get("series", "EQ")
            inst_type = inst.get("instrument_type", "EQUITY")

            stock = {
                "name":           name,
                "short_name":     short_name,
                "symbol":         yf_symbol,
                "trading_symbol": trading_sym,
                "instrument_key": instrument_key,
                "isin":           isin,
                "exchange":       exch_label,
                "series":         series,
                "lot_size":       int(inst.get("lot_size", 1)),
                "tick_size":      float(inst.get("tick_size", 0.05)),
            }

            stocks.append(stock)
            by_symbol[yf_symbol]     = stock
            by_symbol[trading_sym]   = stock   # also index without suffix
            if instrument_key:
                by_key[instrument_key] = stock
            if isin:
                by_isin[isin] = stock

        except Exception:
            continue

    _cache["stocks"]    = stocks
    _cache["by_symbol"] = by_symbol
    _cache["by_key"]    = by_key
    _cache["by_isin"]   = by_isin
    _cache["loaded_at"] = time.time()

    print(f"[Instruments] Indexed {len(stocks)} instruments "
          f"({len([s for s in stocks if s['exchange']=='NSE'])} NSE, "
          f"{len([s for s in stocks if s['exchange']=='BSE'])} BSE)")


def _save_to_file(instruments: list) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "instruments": instruments,
                "saved_at": time.time(),
            }, f, ensure_ascii=False)
        print(f"[Instruments] Saved {len(instruments)} instruments to {CACHE_FILE}")
    except Exception as e:
        print(f"[Instruments] Failed to save cache: {e}")


def _load_from_file() -> bool:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > CACHE_TTL * 2:   # 48h max age for file
            return False
        instruments = data.get("instruments", [])
        if not instruments:
            return False
        _build_indexes(instruments)
        print(f"[Instruments] Loaded {len(instruments)} instruments from cache file")
        return True
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────

def get_all_stocks(exchange: str = "ALL") -> list[dict]:
    """
    Return all stocks, optionally filtered by exchange.
    exchange: 'NSE' | 'BSE' | 'ALL'
    """
    _ensure_loaded()
    stocks = _cache["stocks"]
    if exchange == "ALL":
        return stocks
    return [s for s in stocks if s["exchange"] == exchange.upper()]


def search_stocks(query: str, max_results: int = 10) -> list[dict]:
    """
    Fuzzy search across all instruments by name or symbol.
    Returns matched stock dicts sorted by relevance.
    Works for 5,000+ instruments efficiently.
    """
    _ensure_loaded()
    q = query.strip().upper()
    if not q:
        return []

    exact   = []
    starts  = []
    contains= []
    seen    = set()

    for stock in _cache["stocks"]:
        key = stock["symbol"]
        if key in seen:
            continue

        sym  = stock["trading_symbol"].upper()
        name = stock["name"].upper()
        sname= stock["short_name"].upper()

        # Exact match (symbol or ISIN)
        if q == sym or q == stock.get("isin", ""):
            exact.append(stock)
            seen.add(key)
        # Starts with
        elif sym.startswith(q) or name.startswith(q) or sname.startswith(q):
            starts.append(stock)
            seen.add(key)
        # Contains
        elif q in sym or q in name or q in sname:
            contains.append(stock)
            seen.add(key)

        if len(exact) + len(starts) >= max_results:
            break

    results = exact + starts + contains
    return results[:max_results]


def symbol_to_key(symbol: str) -> Optional[str]:
    """
    Convert yfinance symbol to Upstox instrument key.
    RELIANCE.NS → NSE_EQ|INE002A01018
    Falls back to hardcoded map if instrument not in dynamic list.
    """
    _ensure_loaded()
    sym   = symbol.upper().strip()
    stock = _cache["by_symbol"].get(sym)
    if stock:
        return stock.get("instrument_key")

    # Fallback to hardcoded map for indices and edge cases
    FALLBACK = {
        "^NSEI":    "NSE_INDEX|Nifty 50",
        "^NSEBANK": "NSE_INDEX|Nifty Bank",
        "^BSESN":   "BSE_INDEX|SENSEX",
    }
    return FALLBACK.get(sym)


def key_to_symbol(key: str) -> Optional[str]:
    """Convert Upstox instrument key back to yfinance symbol."""
    _ensure_loaded()
    stock = _cache["by_key"].get(key)
    return stock["symbol"] if stock else None


def get_by_symbol(symbol: str) -> Optional[dict]:
    """Get full instrument info by symbol."""
    _ensure_loaded()
    return _cache["by_symbol"].get(symbol.upper())


def get_by_isin(isin: str) -> Optional[dict]:
    """Get instrument by ISIN."""
    _ensure_loaded()
    return _cache["by_isin"].get(isin.upper())


def total_count() -> int:
    _ensure_loaded()
    return len(_cache["stocks"])


def _ensure_loaded():
    """Load instruments if not already loaded."""
    if not _cache["loaded_at"]:
        load_instruments()