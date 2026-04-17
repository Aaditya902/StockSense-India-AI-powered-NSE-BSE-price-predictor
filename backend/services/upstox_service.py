"""
Upstox Service
Handles token management and OAuth2 flow.

Two ways to get a token:
  1. UPSTOX_ACCESS_TOKEN in .env — paste the token from Upstox dashboard directly.
     Simplest approach. No login flow needed.
  2. OAuth flow via /upstox/login — redirects to Upstox login page.
     Token auto-saved, valid 24 hours.

Token priority: .env UPSTOX_ACCESS_TOKEN > saved file token > OAuth
"""

import os
import time
import json
import requests
from datetime import datetime, timezone
from typing import Optional

from config import UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI

_TOKEN_FILE   = "upstox_token.json"
_memory_token: Optional[str] = None
_memory_expiry: float = 0


# ── Token loading ─────────────────────────────────────────────

def load_token() -> Optional[str]:
    """
    Load valid token from any source.
    Priority: env var > memory > file
    """
    global _memory_token, _memory_expiry

    # 1. Direct token from .env (UPSTOX_ACCESS_TOKEN)
    env_token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    # Remove surrounding quotes if user accidentally included them in .env
    env_token = env_token.strip('"').strip("'")
    if env_token and len(env_token) > 20:   # basic sanity check
        return env_token

    # 2. Memory cache
    if _memory_token and time.time() < _memory_expiry:
        return _memory_token

    # 3. File cache
    try:
        with open(_TOKEN_FILE) as f:
            data = json.load(f)
        if time.time() < data.get("expiry", 0):
            _memory_token  = data["token"]
            _memory_expiry = data["expiry"]
            return _memory_token
    except Exception:
        pass

    return None


def has_valid_token() -> bool:
    return load_token() is not None


def save_token(token: str):
    """Save token to memory and file. Called after OAuth callback."""
    global _memory_token, _memory_expiry
    _memory_token  = token
    _memory_expiry = time.time() + 82800   # 23 hours
    try:
        with open(_TOKEN_FILE, "w") as f:
            json.dump({"token": token, "expiry": _memory_expiry}, f)
    except Exception:
        pass


# ── OAuth2 flow ───────────────────────────────────────────────

def get_login_url() -> str:
    """Generate Upstox OAuth2 login URL."""
    return (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={UPSTOX_API_KEY}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}"
    )


def exchange_code_for_token(auth_code: str) -> str:
    """Exchange OAuth2 code for access token."""
    r = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        data={
            "code":          auth_code,
            "client_id":     UPSTOX_API_KEY,
            "client_secret": UPSTOX_API_SECRET,
            "redirect_uri":  UPSTOX_REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise ValueError(f"No access_token in response: {r.json()}")
    save_token(token)
    return token


# ── WebSocket auth URL ────────────────────────────────────────

def get_ws_auth_url() -> str:
    """Get authorized WebSocket URL from Upstox."""
    token = load_token()
    if not token:
        raise RuntimeError("No valid token — add UPSTOX_ACCESS_TOKEN to .env or visit /upstox/login")
    r = requests.get(
        "https://api.upstox.com/v2/feed/market-data-feed/authorize",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]["authorizedRedirectUri"]


# ── Instrument key mapping ────────────────────────────────────

INSTRUMENT_KEYS = {
    "RELIANCE.NS":    "NSE_EQ|INE002A01018",
    "TCS.NS":         "NSE_EQ|INE467B01029",
    "HDFCBANK.NS":    "NSE_EQ|INE040A01034",
    "INFY.NS":        "NSE_EQ|INE009A01021",
    "ICICIBANK.NS":   "NSE_EQ|INE090A01021",
    "SBIN.NS":        "NSE_EQ|INE062A01020",
    "BHARTIARTL.NS":  "NSE_EQ|INE397D01024",
    "KOTAKBANK.NS":   "NSE_EQ|INE237A01028",
    "LT.NS":          "NSE_EQ|INE018A01030",
    "AXISBANK.NS":    "NSE_EQ|INE238A01034",
    "WIPRO.NS":       "NSE_EQ|INE075A01022",
    "HCLTECH.NS":     "NSE_EQ|INE860A01027",
    "MARUTI.NS":      "NSE_EQ|INE585B01010",
    "SUNPHARMA.NS":   "NSE_EQ|INE044A01036",
    "BAJFINANCE.NS":  "NSE_EQ|INE296A01024",
    "TITAN.NS":       "NSE_EQ|INE280A01028",
    "TATAMOTORS.NS":  "NSE_EQ|INE155A01022",
    "ULTRACEMCO.NS":  "NSE_EQ|INE481G01011",
    "NESTLEIND.NS":   "NSE_EQ|INE239A01024",
    "POWERGRID.NS":   "NSE_EQ|INE752E01010",
    "NTPC.NS":        "NSE_EQ|INE733E01010",
    "TECHM.NS":       "NSE_EQ|INE669C01036",
    "BAJAJFINSV.NS":  "NSE_EQ|INE918I01026",
    "JSWSTEEL.NS":    "NSE_EQ|INE019A01038",
    "TATASTEEL.NS":   "NSE_EQ|INE081A01020",
    "HINDALCO.NS":    "NSE_EQ|INE038A01020",
    "DRREDDY.NS":     "NSE_EQ|INE088B01022",
    "CIPLA.NS":       "NSE_EQ|INE059A01026",
    "ADANIENT.NS":    "NSE_EQ|INE423A01024",
    "ADANIPORTS.NS":  "NSE_EQ|INE742F01042",
    "COALINDIA.NS":   "NSE_EQ|INE522F01014",
    "ONGC.NS":        "NSE_EQ|INE213A01029",
    "ZOMATO.NS":      "NSE_EQ|INE758T01015",
    "DMART.NS":       "NSE_EQ|INE192R01011",
    "ITC.NS":         "NSE_EQ|INE154A01025",
    "HINDUNILVR.NS":  "NSE_EQ|INE030A01027",
    "EICHERMOT.NS":   "NSE_EQ|INE066A01021",
    "HEROMOTOCO.NS":  "NSE_EQ|INE158A01026",
    "BAJAJ-AUTO.NS":  "NSE_EQ|INE917I01010",
    "INDUSINDBK.NS":  "NSE_EQ|INE095A01012",
    "BRITANNIA.NS":   "NSE_EQ|INE216A01030",
    "APOLLOHOSP.NS":  "NSE_EQ|INE437A01024",
    "DIVISLAB.NS":    "NSE_EQ|INE361B01024",
    "TATACONSUM.NS":  "NSE_EQ|INE192A01025",
    "PERSISTENT.NS":  "NSE_EQ|INE262H01021",
    "LTTS.NS":        "NSE_EQ|INE010V01017",
    "^NSEI":          "NSE_INDEX|Nifty 50",
    "^NSEBANK":       "NSE_INDEX|Nifty Bank",
    "^BSESN":         "BSE_INDEX|SENSEX",
}


def symbol_to_key(symbol: str) -> Optional[str]:
    """
    Convert yfinance symbol to Upstox instrument key.
    Uses dynamic instruments service (all NSE/BSE stocks).
    Falls back to hardcoded INSTRUMENT_KEYS for indices.
    """
    try:
        from backend.services.instruments import symbol_to_key as _dynamic
        key = _dynamic(symbol)
        if key:
            return key
    except Exception:
        pass
    return INSTRUMENT_KEYS.get(symbol.upper())


def key_to_symbol(key: str) -> Optional[str]:
    """Convert Upstox instrument key to yfinance symbol."""
    try:
        from backend.services.instruments import key_to_symbol as _dynamic
        sym = _dynamic(key)
        if sym:
            return sym
    except Exception:
        pass
    reverse = {v: k for k, v in INSTRUMENT_KEYS.items()}
    return reverse.get(key)


# ── Tick decoder ──────────────────────────────────────────────

def decode_tick(raw_data: bytes) -> Optional[list]:
    """Decode Upstox protobuf or JSON tick data."""
    try:
        from upstox_client.feeder.proto import market_data_feed_pb2
        feed = market_data_feed_pb2.FeedResponse()
        feed.ParseFromString(raw_data)
        results = []
        for ikey, feed_data in feed.feeds.items():
            sym = key_to_symbol(ikey)
            if not sym:
                continue
            try:
                ltpc  = feed_data.ff.marketFF.ltpc
                price = float(ltpc.ltp or 0)
                close = float(ltpc.cp or price)
                chg   = round(price - close, 2)
                chgp  = round((chg / close) * 100, 2) if close else 0.0
                results.append({
                    "type": "price_update", "symbol": sym,
                    "current_price": round(price, 2),
                    "change": chg, "change_pct": chgp,
                    "direction": "up" if chg > 0 else "down" if chg < 0 else "flat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "upstox_ws",
                })
            except Exception:
                continue
        return results or None
    except Exception:
        pass

    # JSON fallback
    try:
        data = json.loads(raw_data.decode("utf-8"))
        results = []
        for ikey, fd in data.get("feeds", {}).items():
            sym = key_to_symbol(ikey)
            if not sym:
                continue
            try:
                ltpc  = fd.get("ff", {}).get("marketFF", {}).get("ltpc", {})
                price = float(ltpc.get("ltp", 0))
                close = float(ltpc.get("cp", price))
                chg   = round(price - close, 2)
                chgp  = round((chg / close) * 100, 2) if close else 0.0
                results.append({
                    "type": "price_update", "symbol": sym,
                    "current_price": round(price, 2),
                    "change": chg, "change_pct": chgp,
                    "direction": "up" if chg > 0 else "down" if chg < 0 else "flat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "upstox_ws",
                })
            except Exception:
                continue
        return results or None
    except Exception:
        return None


def build_subscribe_msg(symbols: list[str]) -> dict:
    keys = [symbol_to_key(s) for s in symbols if symbol_to_key(s)]
    return {
        "guid": "ss-sub", "method": "sub",
        "data": {"mode": "ltpc", "instrumentKeys": keys},
    }