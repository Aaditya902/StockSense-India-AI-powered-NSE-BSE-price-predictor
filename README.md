# StockSense-India-AI-powered-NSE-BSE-price-predictor

### AI-powered NSE/BSE stock price predictor & market dashboard

Real-time market data · 6-factor analysis · LSTM + AI price prediction · Personal notes

---

## What it does

**Page 1 — Market Home**
- Live Sensex, Nifty 50, Bank Nifty with 30-day sparkline charts
- Top 5 gainers and losers (NSE India API)
- Trending stocks + Gold, Silver, Crude Oil, Natural Gas prices
- Search any NSE stock by name or symbol (fuzzy match — "jio" → Reliance)
- Recently viewed stocks (saved in browser)

**Page 2 — Stock Detail**
- Live price with WebSocket push every 60 seconds
- Candlestick chart (1D / 1W / 1M / 3M)
- Company fundamentals (PE, EPS, Market Cap, Dividend)
- 6-factor analysis (Supply & Demand, Company, Macro, Sentiment, Political, Liquidity)
- AI predicted price range + % upside/downside (7-day horizon)
- Latest news with sentiment scoring
- Personal notes (saved privately on your device)

---

## Quick start

### 1. Clone / download the project
```bash
cd stocksense
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up API keys
```bash
cp .env.example .env
```
Edit `.env` and fill in your keys:

| Key | Where to get | Free? |
|-----|-------------|-------|
| `GROQ_API_KEY` | console.groq.com | ✅ 14,400 req/day |
| `GEMINI_API_KEY` | aistudio.google.com | ✅ 1,500 req/day |
| `NEWS_API_KEY` | newsapi.org/register | ✅ 100 req/day |
| `FRED_API_KEY` | fred.stlouisfed.org/docs/api | ✅ Free |

> yfinance and NSE India API need no keys.

### 4. Start the backend
```bash
uvicorn main:app --reload
```
Backend runs at: http://localhost:8000
Swagger docs at: http://localhost:8000/docs

### 5. Open the frontend
Open `frontend/index.html` in your browser.

---

## Train the ML model (optional but recommended)

The prediction engine works in 3 tiers:
- **Tier 1** — LSTM trained model + Groq/Gemini reasoning *(best)*
- **Tier 2** — Factor-score rule + AI adjustment *(no training needed)*
- **Tier 3** — Safe fallback with disclaimer *(always works)*

To train for specific stocks (~5 min per stock on CPU):
```bash
# Single stock
python ml/train.py --symbol RELIANCE

# Multiple stocks
python ml/train_batch.py --only RELIANCE TCS HDFCBANK SBIN INFY

# All 15 default stocks (run overnight)
python ml/train_batch.py
```

Models are saved to `ml/models/` — one folder per stock.

---

## Project structure

```
stocksense/
│
├── main.py                    # FastAPI app entry point
├── config.py                  # All settings & API keys
├── requirements.txt
├── .env.example               # API key template
│
├── data/
│   ├── nse_stocks.json        # 158 NSE stocks with sectors & keywords
│   ├── nse_stocks_simple.json # Lightweight version for frontend
│   ├── search_resolver.py     # Fuzzy name → symbol matching
│   └── generate_nse_mapping.py
│
├── backend/
│   ├── routers/
│   │   ├── search.py          # GET /search?q=
│   │   ├── market.py          # GET /market/overview|movers|trending
│   │   └── stock.py           # GET+WS /stock/{symbol}/*
│   └── services/
│       ├── market_service.py  # yfinance index data
│       ├── movers_service.py  # NSE gainers/losers
│       ├── trending_service.py# NSE trending + commodities
│       ├── stock_service.py   # Stock detail + chart
│       ├── websocket_service.py# Live price WebSocket
│       ├── factor_service.py  # 6-factor scorer
│       ├── prediction_service.py# LSTM + Groq/Gemini prediction
│       └── news_service.py    # NewsAPI + sentiment
│
├── ml/
│   ├── lstm_model.py          # Model architecture + feature engineering
│   ├── train.py               # Single-stock training script
│   ├── train_batch.py         # Multi-stock batch training
│   └── models/                # Trained models saved here
│       └── RELIANCE_NS/
│           ├── model.keras
│           ├── scalers.pkl
│           └── meta.json
│
└── frontend/
    ├── index.html             # Page 1 — Market home dashboard
    └── stock.html             # Page 2 — Stock detail + prediction
```

---

## All API endpoints

```
GET  /health                         Server status + key check
GET  /search?q=reliance              Fuzzy stock search
GET  /search/all                     All 158 NSE stocks
GET  /search/sector/IT               Stocks by sector
GET  /market/overview                Sensex, Nifty50, BankNifty
GET  /market/overview/history        Index chart history
GET  /market/movers                  Top gainers + losers
GET  /market/trending                Trending stocks + commodities
GET  /stock/{symbol}                 Price, chart, company info
WS   /stock/{symbol}/live            Live price every 60s
GET  /stock/{symbol}/factors         6 factor scores
GET  /stock/{symbol}/predict         Predicted price + % delta
GET  /stock/{symbol}/news            Headlines + sentiment
```

---

## Prediction accuracy — honest disclaimer

| What we predict | Realistic accuracy |
|---|---|
| Price direction (up/down) | 55–65% |
| 7-day price range | 50–60% in range |
| Exact price | Not reliable |
| Trend strength | 65–75% useful |

**This app is for educational purposes only. It is not financial advice.**
Always combine this tool with your own research before making investment decisions.

---

## Tech stack

| Layer | Tool |
|-------|------|
| Price & indices | yfinance (free) |
| Gainers/losers | NSE India public API (free) |
| News | NewsAPI free tier |
| Macro data | FRED API (free) |
| AI reasoning | Groq (Llama 3) + Gemini fallback |
| ML model | Keras LSTM |
| Backend | FastAPI + WebSockets |
| Frontend charts | Lightweight Charts (TradingView) |
| Recently viewed / Notes | Browser localStorage |

**Total cost: ₹0**