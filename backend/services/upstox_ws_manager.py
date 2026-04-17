"""
Upstox WebSocket Manager
Manages a single connection to Upstox that serves all frontend clients.

Architecture:
  One Upstox WS connection → receives all subscribed ticks
  Per-symbol subscription tracking
  Broadcast to all frontend WebSocket clients watching that symbol

This is more efficient than one connection per symbol.
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket


# ── Latest price cache (for immediate send on new connection) ──
_latest_prices: dict[str, dict] = {}

# ── Frontend connections (same as original websocket_service) ──
_connections: dict[str, set[WebSocket]] = defaultdict(set)
_subscribed_keys: set[str] = set()

# ── Upstox WS task ────────────────────────────────────────────
_upstox_task: Optional[asyncio.Task] = None
_upstox_ws   = None


# ── Frontend WebSocket management ────────────────────────────

async def connect_client(symbol: str, websocket: WebSocket):
    """Connect a frontend client and start Upstox feed if needed."""
    await websocket.accept()
    _connections[symbol].add(websocket)

    # Send latest cached price immediately
    if symbol in _latest_prices:
        await _send_one(websocket, _latest_prices[symbol])

    # Ensure Upstox WS is running and symbol is subscribed
    await _ensure_upstox_running()
    await _subscribe_symbol(symbol)


def disconnect_client(symbol: str, websocket: WebSocket):
    _connections[symbol].discard(websocket)
    if not _connections[symbol]:
        del _connections[symbol]


async def broadcast_to_clients(symbol: str, data: dict):
    """Send a price update to all clients watching this symbol."""
    _latest_prices[symbol] = data
    dead = set()
    for ws in list(_connections.get(symbol, [])):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _connections[symbol].discard(ws)


async def _send_one(websocket: WebSocket, data: dict):
    try:
        await websocket.send_json(data)
    except Exception:
        pass


# ── Upstox connection management ─────────────────────────────

async def _ensure_upstox_running():
    """Start the Upstox WebSocket task if not already running."""
    global _upstox_task
    if _upstox_task is None or _upstox_task.done():
        _upstox_task = asyncio.create_task(_upstox_feed_loop())


async def _subscribe_symbol(symbol: str):
    """Add a symbol to the subscription set and refresh subscription."""
    global _upstox_ws
    from backend.services.upstox_service import symbol_to_key, build_subscribe_msg

    key = symbol_to_key(symbol)
    if not key or key in _subscribed_keys:
        return

    _subscribed_keys.add(key)

    # Send updated subscription to Upstox WS if connected
    if _upstox_ws:
        try:
            all_symbols = [s for s, ws in _connections.items() if ws]
            msg = build_subscribe_msg(all_symbols)
            await _upstox_ws.send(json.dumps(msg))
        except Exception:
            pass


async def _upstox_feed_loop():
    """
    Main loop: connects to Upstox WebSocket, receives ticks,
    decodes them and broadcasts to frontend clients.
    Reconnects automatically on disconnect.
    """
    global _upstox_ws

    while True:
        try:
            from backend.services.upstox_service import (
                get_ws_auth_url, build_subscribe_msg, decode_tick, has_valid_token
            )

            if not has_valid_token():
                print("[UpstoxWS] No valid token — waiting for login")
                await asyncio.sleep(10)
                continue

            ws_url = get_ws_auth_url()
            print(f"[UpstoxWS] Connecting to Upstox WebSocket...")

            import websockets
            async with websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                _upstox_ws = ws
                print("[UpstoxWS] Connected")

                # Subscribe to all currently watched symbols
                all_symbols = list(_connections.keys())
                if all_symbols:
                    sub_msg = build_subscribe_msg(all_symbols)
                    await ws.send(json.dumps(sub_msg))
                    print(f"[UpstoxWS] Subscribed to {len(all_symbols)} symbols")

                async for raw_msg in ws:
                    try:
                        # Upstox sends binary protobuf or JSON
                        if isinstance(raw_msg, bytes):
                            ticks = decode_tick(raw_msg)
                        else:
                            ticks = decode_tick(raw_msg.encode())

                        if ticks:
                            for tick in ticks:
                                sym = tick.get("symbol")
                                if sym:
                                    await broadcast_to_clients(sym, tick)
                    except Exception as e:
                        print(f"[UpstoxWS] Tick decode error: {e}")

        except Exception as e:
            print(f"[UpstoxWS] Disconnected: {e} — reconnecting in 5s")
            _upstox_ws = None
            await asyncio.sleep(5)


# ── Fallback: polling when Upstox not connected ───────────────

async def get_price_fallback(symbol: str) -> dict:
    """
    Use NSE direct API as fallback when Upstox is not connected.
    Called when no valid Upstox token exists.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_price_sync, symbol)


def _fetch_price_sync(symbol: str) -> dict:
    """Sync price fetch — NSE direct first, yfinance fallback."""
    try:
        from backend.services.nse_direct import get_quote
        q = get_quote(symbol)
        return {
            "type":          "price_update",
            "symbol":        symbol,
            "current_price": q["price"],
            "change":        q["change"],
            "change_pct":    q["change_pct"],
            "direction":     q["direction"],
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "source":        "nse_direct",
        }
    except Exception:
        pass

    try:
        from backend.services.yf_session import get_ticker
        ticker = get_ticker(symbol)
        hist   = ticker.history(period="2d", interval="1d")
        if not hist.empty:
            closes = hist["Close"].dropna().tolist()
            price  = round(float(closes[-1]), 2)
            prev   = round(float(closes[-2]), 2) if len(closes) >= 2 else price
            change     = round(price - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0.0
            return {
                "type":          "price_update",
                "symbol":        symbol,
                "current_price": price,
                "change":        change,
                "change_pct":    change_pct,
                "direction":     "up" if change > 0 else "down" if change < 0 else "flat",
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "source":        "yfinance",
            }
    except Exception:
        pass

    return {
        "type":      "error",
        "symbol":    symbol,
        "message":   "Price unavailable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }