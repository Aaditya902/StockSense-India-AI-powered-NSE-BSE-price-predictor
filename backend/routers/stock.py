"""
Router: Stock Detail
Powers Page 2 — the stock detail page.

Endpoints:
  GET  /stock/{symbol}             → price, company info, chart   ✅ Step 6
  WS   /stock/{symbol}/live        → live price every 60s         (Step 7)
  GET  /stock/{symbol}/factors     → 6 factor scores              (Step 8)
  GET  /stock/{symbol}/predict     → predicted price + % delta    (Step 10)
  GET  /stock/{symbol}/news        → last 5 headlines             (Step 11)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Path, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/stock", tags=["Stock"])


# ── Response models ───────────────────────────────────────────

class CompanyInfo(BaseModel):
    name:              str
    symbol:            str
    sector:            str
    industry:          str
    website:           Optional[str]
    description:       str
    market_cap:        Optional[float]
    market_cap_crores: Optional[float]
    pe_ratio:          Optional[float]
    pb_ratio:          Optional[float]
    eps:               Optional[float]
    dividend_yield:    Optional[float]
    dividend_rate:     Optional[float]
    week_52_high:      Optional[float]
    week_52_low:       Optional[float]
    day_high:          Optional[float]
    day_low:           Optional[float]
    volume:            Optional[int]
    avg_volume:        Optional[int]
    target_mean_price: Optional[float]
    recommendation:    Optional[str]


class OHLCVBar(BaseModel):
    time:   int         # Unix timestamp in seconds
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int


class StockDetail(BaseModel):
    symbol:        str
    current_price: float
    change:        float
    change_pct:    float
    direction:     str
    company:       CompanyInfo
    chart_data:    list[OHLCVBar]
    chart_period:  str
    last_updated:  str


class LivePrice(BaseModel):
    symbol:        str
    current_price: float
    change:        float
    change_pct:    float
    direction:     str
    timestamp:     str


class FactorScore(BaseModel):
    name:   str
    score:  float
    label:  str
    detail: str
    weight: float


class FactorsResponse(BaseModel):
    symbol:        str
    factors:       list[FactorScore]
    overall_score: float
    overall_label: str


class Prediction(BaseModel):
    symbol:          str
    current_price:   float
    predicted_low:   float
    predicted_high:  float
    predicted_mid:   float
    change_pct_low:  float
    change_pct_high: float
    change_pct_mid:  float
    direction:       str
    horizon_days:    int
    confidence:      str
    ai_reasoning:    str
    model_used:      str


class NewsArticle(BaseModel):
    title:           str
    source:          str
    published_at:    str
    url:             str
    sentiment:       str
    sentiment_score: float


class NewsResponse(BaseModel):
    symbol:            str
    articles:          list[NewsArticle]
    overall_sentiment: str


# ── Step 6: Stock detail ──────────────────────────────────────

@router.get("/{symbol}", response_model=StockDetail)
def get_stock_detail(
    symbol:       str = Path(..., description="NSE symbol e.g. RELIANCE.NS or RELIANCE"),
    chart_period: str = Query("1m", description="Chart period: 1d | 1w | 1m | 3m"),
):
    """
    Returns full stock detail for Page 2.

    Includes:
      - Current price + day change + direction
      - Company fundamentals (PE, EPS, market cap, 52-week range)
      - OHLCV chart data (bars in Unix timestamp format for Lightweight Charts)

    Data source : yfinance
    Chart period: 1d (5-min bars) | 1w (15-min) | 1m (daily) | 3m (daily)

    Examples:
      GET /stock/RELIANCE          → auto-adds .NS suffix
      GET /stock/RELIANCE.NS
      GET /stock/RELIANCE.NS?chart_period=1d
      GET /stock/TCS.NS?chart_period=3m
    """
    from backend.services.stock_service import get_stock_detail as _fetch

    valid_periods = ["1d", "1w", "1m", "3m"]
    if chart_period not in valid_periods:
        raise HTTPException(400, detail=f"chart_period must be one of {valid_periods}")

    try:
        data = _fetch(symbol, chart_period)
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))
    except Exception as e:
        raise HTTPException(503, detail=f"Stock data unavailable: {str(e)}")

    return StockDetail(
        symbol        = data["symbol"],
        current_price = data["current_price"],
        change        = data["change"],
        change_pct    = data["change_pct"],
        direction     = data["direction"],
        last_updated  = data["last_updated"],
        chart_period  = data["chart_period"],
        company       = CompanyInfo(**data["company"]),
        chart_data    = [OHLCVBar(**b) for b in data["chart_data"]],
    )


# ── Step 7: WebSocket live price ──────────────────────────────

@router.websocket("/{symbol}/live")
async def live_price_ws(websocket: WebSocket, symbol: str):
    """
    WebSocket — pushes live price to frontend every 60 seconds.

    Flow:
      1. Client connects  →  server accepts + sends price immediately
      2. Server polls yfinance every 60s  →  broadcasts to all clients
         watching the same symbol (one yfinance call serves many clients)
      3. Client disconnects  →  connection removed cleanly
         If last client for symbol disconnects → polling task cancelled

    Frontend usage (JavaScript):
      const ws = new WebSocket('ws://localhost:8000/stock/RELIANCE.NS/live');
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'price_update') {
          updatePriceDisplay(data.current_price, data.change_pct);
        }
      };

    Message format sent to client:
      {
        type:          'price_update',
        symbol:        'RELIANCE.NS',
        current_price: 2850.50,
        change:        50.50,
        change_pct:    1.80,
        direction:     'up',
        timestamp:     '2024-01-15T10:30:00+00:00'
      }
    """
    from backend.services.websocket_service import manager
    from backend.services.stock_service import _normalise_symbol

    symbol = _normalise_symbol(symbol)

    await manager.connect(symbol, websocket)

    # Send current price immediately on connect (don't wait 60s)
    from backend.services.websocket_service import _fetch_price_async
    initial_price = await _fetch_price_async(symbol)
    await manager.send_one(websocket, initial_price)

    try:
        # Keep connection alive — wait for disconnect
        while True:
            try:
                # Listen for client messages (e.g. ping/pong or period change)
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=120)
                # If client sends "ping", respond with "pong"
                if msg == "ping":
                    await manager.send_one(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                # No message in 2 min — send keepalive ping
                await manager.send_one(websocket, {"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(symbol, websocket)


import asyncio


# ── Step 8: 6-factor scorer ───────────────────────────────────

@router.get("/{symbol}/factors", response_model=FactorsResponse)
def get_stock_factors(
    symbol: str = Path(..., description="NSE symbol e.g. RELIANCE.NS")
):
    """
    Scores all 6 factors for a stock on a scale of -1.0 to +1.0.

    Factors:
      F1  Demand & Supply        (25%)  — RSI, volume ratio, 5-day momentum
      F2  Company Performance    (20%)  — EPS, PE ratio, dividend, 52-week range
      F3  Economic Conditions    (15%)  — Nifty trend, RBI rate context
      F4  Market Sentiment       (20%)  — NewsAPI NLP / analyst recommendation
      F5  External & Political   (10%)  — Policy/geopolitical news keywords
      F6  Liquidity & Activity   (10%)  — Volume vs 3-month avg, price vs VWAP

    Labels: score >= +0.2 = bullish | -0.2 to +0.2 = neutral | <= -0.2 = bearish
    Overall score = weighted average across all 6 factors.
    """
    from backend.services.factor_service import score_all_factors
    from backend.services.stock_service  import _normalise_symbol

    symbol = _normalise_symbol(symbol)

    try:
        data = score_all_factors(symbol)
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))
    except Exception as e:
        raise HTTPException(503, detail=f"Factor scoring unavailable: {str(e)}")

    return FactorsResponse(
        symbol        = data["symbol"],
        overall_score = data["overall_score"],
        overall_label = data["overall_label"],
        factors = [
            FactorScore(
                name   = f["name"],
                score  = f["score"],
                label  = f["label"],
                detail = f["detail"],
                weight = f["weight"],
            )
            for f in data["factors"]
        ],
    )


# ── Step 10: Prediction ───────────────────────────────────────

@router.get("/{symbol}/predict", response_model=Prediction)
def get_stock_prediction(
    symbol: str = Path(..., description="NSE symbol e.g. RELIANCE.NS")
):
    """
    Returns predicted price range and % upside/downside for 7 days.

    Pipeline:
      Tier 1  LSTM model + Groq/Gemini reasoning  (best — needs trained model)
      Tier 2  Factor-score rule + AI adjustment    (no model needed)
      Tier 3  Safe fallback with disclaimer        (always returns something)

    Response fields:
      current_price   — live price at prediction time
      predicted_low   — lower bound of 7-day range
      predicted_high  — upper bound of 7-day range
      predicted_mid   — midpoint (headline number shown on UI)
      change_pct_mid  — e.g. +4.6% upside or -3.2% downside
      confidence      — high | medium | low  (based on factor alignment)
      ai_reasoning    — 2-3 sentence explanation from AI
      model_used      — lstm+groq | lstm+gemini | factor_rule+groq | none

    To train the LSTM model for a stock:
      python ml/train.py --symbol RELIANCE.NS
    """
    from backend.services.prediction_service import get_prediction
    from backend.services.factor_service     import score_all_factors
    from backend.services.stock_service      import _normalise_symbol

    symbol = _normalise_symbol(symbol)

    # Score factors first — prediction engine needs them
    try:
        factors = score_all_factors(symbol)
    except Exception as e:
        raise HTTPException(503, detail=f"Factor scoring failed: {str(e)}")

    # Generate prediction
    try:
        pred = get_prediction(symbol, factors)
    except Exception as e:
        raise HTTPException(503, detail=f"Prediction failed: {str(e)}")

    return Prediction(
        symbol          = pred["symbol"],
        current_price   = pred["current_price"],
        predicted_low   = pred["predicted_low"],
        predicted_high  = pred["predicted_high"],
        predicted_mid   = pred["predicted_mid"],
        change_pct_low  = pred["change_pct_low"],
        change_pct_high = pred["change_pct_high"],
        change_pct_mid  = pred["change_pct_mid"],
        direction       = pred["direction"],
        horizon_days    = pred["horizon_days"],
        confidence      = pred["confidence"],
        ai_reasoning    = pred["ai_reasoning"],
        model_used      = pred["model_used"],
    )


# ── Step 11: News ─────────────────────────────────────────────

@router.get("/{symbol}/news", response_model=NewsResponse)
def get_stock_news(
    symbol: str = Path(..., description="NSE symbol e.g. RELIANCE.NS")
):
    """
    Returns last 5 news headlines with per-article sentiment.
    Primary: NewsAPI  |  Fallback: yfinance news  |  Cache: 15 min
    """
    from backend.services.news_service  import get_stock_news as _fetch
    from backend.services.stock_service import _normalise_symbol

    symbol = _normalise_symbol(symbol)

    try:
        data = _fetch(symbol)
    except Exception as e:
        raise HTTPException(503, detail=f"News unavailable: {str(e)}")

    return NewsResponse(
        symbol            = data["symbol"],
        overall_sentiment = data["overall_sentiment"],
        articles          = [
            NewsArticle(
                title           = a["title"],
                source          = a["source"],
                published_at    = a["published_at"],
                url             = a["url"],
                sentiment       = a["sentiment"],
                sentiment_score = a["sentiment_score"],
            )
            for a in data["articles"]
        ],
    )