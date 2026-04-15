"""
Service: Live Price WebSocket
Pushes live price updates to the frontend every 60 seconds.

How it works:
  1. Frontend connects to WS /stock/{symbol}/live
  2. Server immediately sends current price
  3. Server polls yfinance every 60s and pushes updated price
  4. If frontend disconnects — connection is cleanly removed
  5. Multiple clients watching same stock → one yfinance call serves all

Architecture: ConnectionManager handles all active WebSocket connections
grouped by symbol. One polling task per symbol, shared across all clients.

Called by: WS /stock/{symbol}/live
"""

import asyncio
import json
from datetime import datetime, timezone
from collections import defaultdict
from fastapi import WebSocket

import yfinance as yf
from backend.services.yf_session import get_ticker

from config import PRICE_REFRESH_SECONDS


# ── Connection Manager ────────────────────────────────────────

class ConnectionManager:
    """
    Manages all active WebSocket connections grouped by stock symbol.

    Structure:
        _connections = {
            "RELIANCE.NS": {websocket1, websocket2, ...},
            "TCS.NS":      {websocket3},
        }
        _tasks = {
            "RELIANCE.NS": asyncio.Task,
            "TCS.NS":      asyncio.Task,
        }
    """

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._tasks:       dict[str, asyncio.Task]   = {}

    async def connect(self, symbol: str, websocket: WebSocket):
        """
        Accept a new WebSocket connection for a symbol.
        Starts a polling task for that symbol if not already running.
        """
        await websocket.accept()
        self._connections[symbol].add(websocket)
        print(f"[WS] Connected: {symbol}  ({len(self._connections[symbol])} clients)")

        # Start polling task only if one isn't already running for this symbol
        if symbol not in self._tasks or self._tasks[symbol].done():
            task = asyncio.create_task(self._poll_symbol(symbol))
            self._tasks[symbol] = task

    def disconnect(self, symbol: str, websocket: WebSocket):
        """Remove a disconnected client. Cancel polling if no clients left."""
        self._connections[symbol].discard(websocket)
        remaining = len(self._connections[symbol])
        print(f"[WS] Disconnected: {symbol}  ({remaining} clients remaining)")

        if remaining == 0:
            # No clients watching this symbol — cancel the polling task
            task = self._tasks.pop(symbol, None)
            if task and not task.done():
                task.cancel()
            del self._connections[symbol]

    async def broadcast(self, symbol: str, data: dict):
        """
        Send price update to all clients watching this symbol.
        Removes dead connections silently.
        """
        dead = set()
        for ws in list(self._connections.get(symbol, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)

        # Clean up dead connections
        for ws in dead:
            self._connections[symbol].discard(ws)

    async def send_one(self, websocket: WebSocket, data: dict):
        """Send a message to one specific client."""
        try:
            await websocket.send_json(data)
        except Exception:
            pass

    # ── Polling task ──────────────────────────────────────────

    async def _poll_symbol(self, symbol: str):
        """
        Background task — fetches price every PRICE_REFRESH_SECONDS
        and broadcasts to all connected clients for this symbol.

        Runs until all clients disconnect.
        """
        print(f"[WS] Polling started: {symbol}  (every {PRICE_REFRESH_SECONDS}s)")
        try:
            while symbol in self._connections and self._connections[symbol]:

                price_data = await _fetch_price_async(symbol)
                await self.broadcast(symbol, price_data)

                # Wait for next refresh — sleep in small chunks
                # so the task responds quickly to cancellation
                for _ in range(PRICE_REFRESH_SECONDS):
                    if symbol not in self._connections:
                        return
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass
        finally:
            print(f"[WS] Polling stopped: {symbol}")


# ── Singleton manager (shared across all requests) ────────────

manager = ConnectionManager()


# ── Price fetcher (async wrapper) ─────────────────────────────

async def _fetch_price_async(symbol: str) -> dict:
    """
    Run yfinance in a thread pool so it doesn't block the event loop.
    FastAPI is async — blocking calls must be offloaded.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_price_sync, symbol)


def _fetch_price_sync(symbol: str) -> dict:
    """
    Synchronous yfinance price fetch — runs in thread pool.
    Uses 3-strategy cascade same as stock_service.
    """
    try:
        ticker         = get_ticker(symbol)
        current_price  = None
        previous_close = None

        # Strategy 1 — fast_info
        try:
            fi             = ticker.fast_info
            v = fi.last_price
            current_price  = round(float(v), 2) if v and float(v) != 0 else None
            v = fi.previous_close
            previous_close = round(float(v), 2) if v and float(v) != 0 else None
        except Exception:
            pass

        # Strategy 2 — history
        if current_price is None:
            hist = ticker.history(period="5d", interval="1d")
            if not hist.empty:
                closes = hist["Close"].dropna().tolist()
                if closes:
                    current_price  = round(float(closes[-1]), 2)
                    previous_close = round(float(closes[-2]), 2) if len(closes) >= 2 else current_price

        if current_price is None:
            raise ValueError("No price data")

        previous_close = previous_close or current_price
        change         = round(current_price - previous_close, 2)
        change_pct     = round((change / previous_close) * 100, 2) if previous_close else 0.0

        return {
            "type":          "price_update",
            "symbol":        symbol,
            "current_price": current_price,
            "change":        change,
            "change_pct":    change_pct,
            "direction":     "up" if change > 0 else "down" if change < 0 else "flat",
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        return {
            "type":      "error",
            "symbol":    symbol,
            "message":   f"Price fetch failed: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }