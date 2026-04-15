"""
yfinance Session Manager
Fixes Yahoo Finance 429 Too Many Requests errors.

Problems solved:
  1. Yahoo Finance blocks requests without proper browser headers
  2. Making too many calls too fast triggers rate limiting
  3. Repeated calls for the same symbol waste quota

Solutions:
  1. Custom session with realistic browser headers
  2. Per-symbol in-memory cache (5 min TTL)
  3. Minimum 0.5s delay between calls to same host
  4. Automatic retry with exponential backoff on 429
"""

import time
import threading
import yfinance as yf
import requests
from requests.adapters import HTTPAdapter


# ── Realistic browser headers ────────────────────────────────

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ── Rate limiter ─────────────────────────────────────────────

_lock           = threading.Lock()
_last_call_time = 0.0
MIN_INTERVAL    = 0.5   # seconds between yfinance calls


def _throttle():
    """Ensure minimum interval between calls."""
    global _last_call_time
    with _lock:
        now     = time.time()
        elapsed = now - _last_call_time
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        _last_call_time = time.time()


# ── Ticker cache ─────────────────────────────────────────────

_ticker_cache: dict = {}   # symbol → { ticker, expires_at }
TICKER_TTL = 300           # 5 minutes


def get_ticker(symbol: str) -> yf.Ticker:
    """
    Get a yfinance Ticker with rate limiting.
    Returns cached ticker if available and not expired.
    """
    now = time.time()
    if symbol in _ticker_cache and now < _ticker_cache[symbol]["expires_at"]:
        return _ticker_cache[symbol]["ticker"]

    _throttle()

    try:
        # Create session with proper headers to avoid 429
        session = requests.Session()
        session.headers.update(HEADERS)
        adapter = HTTPAdapter(max_retries=2)
        session.mount("https://", adapter)
        session.mount("http://",  adapter)

        ticker = yf.Ticker(symbol, session=session)

    except Exception:
        # Fallback — create ticker without custom session
        ticker = yf.Ticker(symbol)

    _ticker_cache[symbol] = {
        "ticker":     ticker,
        "expires_at": now + TICKER_TTL,
    }
    return ticker


def get_ticker_with_retry(symbol: str, max_retries: int = 3) -> yf.Ticker:
    """
    Get ticker with exponential backoff retry on 429 errors.
    Waits: 2s → 4s → 8s between retries.
    """
    for attempt in range(max_retries):
        try:
            ticker = get_ticker(symbol)
            # Quick probe to see if we're being rate-limited
            _ = ticker.fast_info.last_price
            return ticker
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "too many" in err_str:
                wait = 2 ** (attempt + 1)   # 2, 4, 8 seconds
                print(f"[YFinance] 429 rate limit for {symbol} — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                # Bust cache so we create a fresh session on retry
                _ticker_cache.pop(symbol, None)
            else:
                return get_ticker(symbol)   # non-429 error, don't retry
    return get_ticker(symbol)


def clear_cache(symbol: str = None):
    """Clear cache for one symbol or all."""
    if symbol:
        _ticker_cache.pop(symbol, None)
    else:
        _ticker_cache.clear()