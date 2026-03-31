"""
Router: Market
Powers Page 1 — the home dashboard.

Endpoints:
  GET /market/overview          → Sensex, Nifty50, BankNifty       ✅ Step 3
  GET /market/overview/history  → index price history for charts    ✅ Step 3
  GET /market/movers            → top gainers + losers              (Step 4)
  GET /market/trending          → trending stocks + commodities     (Step 5)
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/market", tags=["Market"])


class IndexData(BaseModel):
    name:           str
    symbol:         str
    current:        float
    previous_close: float
    change:         float
    change_pct:     float
    direction:      str
    day_high:       float
    day_low:        float
    last_updated:   str


class MarketOverview(BaseModel):
    sensex:       IndexData
    nifty50:      IndexData
    banknifty:    IndexData
    last_updated: str


class IndexBar(BaseModel):
    date:  str
    close: float
    open:  float
    high:  float
    low:   float


class StockMover(BaseModel):
    name:       str
    symbol:     str
    price:      float
    change_pct: float
    direction:  str


class MoversResponse(BaseModel):
    gainers: list[StockMover]
    losers:  list[StockMover]


class TrendingStock(BaseModel):
    name:       str
    symbol:     str
    price:      float
    change_pct: float
    reason:     str


class Commodity(BaseModel):
    name:       str
    symbol:     str
    price:      float
    unit:       str
    change_pct: float
    direction:  str


class TrendingResponse(BaseModel):
    trending_stocks:      list[TrendingStock]
    trending_commodities: list[Commodity]



@router.get("/overview", response_model=MarketOverview)
def get_market_overview():
    """
    Returns live Sensex, Nifty50, and BankNifty index values.
    Data source : yfinance (^BSESN, ^NSEI, ^NSEBANK)
    Refresh     : call every 60 seconds from frontend
    """
    from backend.services.market_service import get_market_overview as _fetch

    try:
        data = _fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {str(e)}")

    def _to_index(d: dict) -> IndexData:
        return IndexData(
            name           = d["name"],
            symbol         = d["symbol"],
            current        = d["current"],
            previous_close = d["previous_close"],
            change         = d["change"],
            change_pct     = d["change_pct"],
            direction      = d["direction"],
            day_high       = d["day_high"],
            day_low        = d["day_low"],
            last_updated   = d["last_updated"],
        )

    return MarketOverview(
        sensex    = _to_index(data["sensex"]),
        nifty50   = _to_index(data["nifty50"]),
        banknifty = _to_index(data["banknifty"]),
        last_updated = data["last_updated"],
    )


@router.get("/overview/history", response_model=list[IndexBar])
def get_index_history(
    index:  str = Query("nifty50", description="sensex | nifty50 | banknifty"),
    period: str = Query("1mo",     description="1d | 5d | 1mo | 3mo"),
):
    """
    Returns OHLCV history bars for a given index.
    Used to draw mini sparkline charts on the home page.

    Example:
      GET /market/overview/history?index=sensex&period=1mo
    """
    from backend.services.market_service import get_index_history as _fetch

    valid_indices = ["sensex", "nifty50", "banknifty"]
    valid_periods = ["1d", "5d", "1mo", "3mo"]

    if index not in valid_indices:
        raise HTTPException(400, detail=f"index must be one of {valid_indices}")
    if period not in valid_periods:
        raise HTTPException(400, detail=f"period must be one of {valid_periods}")

    try:
        bars = _fetch(index, period)
    except Exception as e:
        raise HTTPException(503, detail=str(e))

    return [IndexBar(**b) for b in bars]


@router.get("/movers", response_model=MoversResponse)
def get_market_movers():
    """
    Returns top 5 gainers and top 5 losers from NSE today.

    Primary source : NSE India public API
    Fallback       : yfinance (Nifty 50 stocks sorted by % change)
    Cache          : 5 minutes — call freely, won't hammer NSE servers

    Example response:
      gainers: [{ name, symbol, price, change_pct, direction }, ...]
      losers:  [{ name, symbol, price, change_pct, direction }, ...]
    """
    from backend.services.movers_service import get_market_movers as _fetch

    try:
        data = _fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Movers data unavailable: {str(e)}")

    def _to_mover(m: dict) -> StockMover:
        return StockMover(
            name       = m["name"],
            symbol     = m["symbol"],
            price      = m["price"],
            change_pct = m["change_pct"],
            direction  = m["direction"],
        )

    return MoversResponse(
        gainers = [_to_mover(m) for m in data["gainers"]],
        losers  = [_to_mover(m) for m in data["losers"]],
    )


# ── Step 5: Trending ──────────────────────────────────────────

@router.get("/trending", response_model=TrendingResponse)
def get_trending():
    """
    Returns top 8 trending stocks (highest volume / biggest movers)
    and live prices for Gold, Silver, Crude Oil, Natural Gas.

    Primary source : NSE India most-active API + yfinance futures
    Fallback       : curated yfinance watchlist sorted by absolute % move
    Cache          : 5 minutes
    """
    from backend.services.trending_service import get_trending as _fetch

    try:
        data = _fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Trending data unavailable: {str(e)}")

    def _to_trending(s: dict) -> TrendingStock:
        return TrendingStock(
            name       = s["name"],
            symbol     = s["symbol"],
            price      = s["price"],
            change_pct = s["change_pct"],
            reason     = s["reason"],
        )

    def _to_commodity(c: dict) -> Commodity:
        return Commodity(
            name       = c["name"],
            symbol     = c["symbol"],
            price      = c["price"],
            unit       = c["unit"],
            change_pct = c["change_pct"],
            direction  = c["direction"],
        )

    return TrendingResponse(
        trending_stocks      = [_to_trending(s) for s in data["trending_stocks"]],
        trending_commodities = [_to_commodity(c) for c in data["trending_commodities"]],
    )