"""
Service: 6 Factor Scorer
Scores each of the 6 factors from -1.0 (bearish) to +1.0 (bullish).

Each factor returns:
  name        : display name
  score       : float  -1.0 to +1.0
  label       : "bullish" | "neutral" | "bearish"
  detail      : human-readable explanation shown on the card
  weight      : contribution to overall weighted score

Data sources:
  yfinance   → F1 (supply/demand), F2 (company), F6 (liquidity)
  NewsAPI    → F4 (sentiment), F5 (external/political)
  yfinance   → F3 (macro — Nifty trend as proxy, FRED if key present)

Called by: GET /stock/{symbol}/factors
"""

import yfinance as yf
import requests
from datetime import datetime, timezone
from typing import Optional

from config import NEWS_API_KEY, FRED_API_KEY, NIFTY50_SYMBOL


# ── Factor weights — must sum to 1.0 ─────────────────────────

WEIGHTS = {
    "supply_demand":   0.25,
    "company":         0.20,
    "economic":        0.15,
    "sentiment":       0.20,
    "external":        0.10,
    "liquidity":       0.10,
}

# ── Label thresholds ──────────────────────────────────────────

def _label(score: float) -> str:
    if score >= 0.2:  return "bullish"
    if score <= -0.2: return "bearish"
    return "neutral"

def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, round(v, 3)))


# ── Main function ─────────────────────────────────────────────

def score_all_factors(symbol: str) -> dict:
    """
    Score all 6 factors for a stock symbol.
    Returns structured response ready for the API endpoint.
    """
    ticker = yf.Ticker(symbol)

    # Fetch data once — reuse across factors
    try:
        fast_info = ticker.fast_info
        info      = ticker.info
        hist_60   = ticker.history(period="60d", interval="1d")
        hist_20   = hist_60.tail(20)
        hist_5    = hist_60.tail(5)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data for {symbol}: {e}")

    # Score each factor
    f1 = _score_supply_demand(fast_info, hist_60, hist_5)
    f2 = _score_company(info, fast_info)
    f3 = _score_economic()
    f4 = _score_sentiment(symbol, info)
    f5 = _score_external(symbol, info)
    f6 = _score_liquidity(fast_info, hist_20)

    factors = [f1, f2, f3, f4, f5, f6]

    # Weighted overall score
    overall = sum(f["score"] * f["weight"] for f in factors)
    overall = _clamp(overall)

    return {
        "symbol":        symbol,
        "factors":       factors,
        "overall_score": overall,
        "overall_label": _label(overall),
        "last_updated":  datetime.now(timezone.utc).isoformat(),
    }


# ── F1: Supply & Demand ───────────────────────────────────────

def _score_supply_demand(fast_info, hist_60, hist_5) -> dict:
    """
    Signals: RSI, volume vs average, 5-day price momentum.
    """
    score  = 0.0
    detail = []

    try:
        closes  = hist_60["Close"].tolist()
        volumes = hist_60["Volume"].tolist()

        # RSI (14-day)
        rsi = _calc_rsi(closes, period=14)
        if rsi is not None:
            if rsi > 65:
                score += 0.5; detail.append(f"RSI {rsi:.0f} — overbought momentum")
            elif rsi > 55:
                score += 0.3; detail.append(f"RSI {rsi:.0f} — bullish momentum")
            elif rsi < 35:
                score -= 0.5; detail.append(f"RSI {rsi:.0f} — oversold, potential reversal")
            elif rsi < 45:
                score -= 0.3; detail.append(f"RSI {rsi:.0f} — weak momentum")
            else:
                detail.append(f"RSI {rsi:.0f} — neutral zone")

        # Volume ratio vs 20-day average
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            today_vol = float(fast_info.three_month_average_volume or avg_vol)
            ratio = today_vol / avg_vol if avg_vol > 0 else 1.0
            if ratio > 2.0:
                score += 0.3; detail.append(f"Volume {ratio:.1f}x above avg — very high activity")
            elif ratio > 1.5:
                score += 0.2; detail.append(f"Volume {ratio:.1f}x above avg — elevated interest")
            elif ratio < 0.5:
                score -= 0.2; detail.append(f"Volume {ratio:.1f}x avg — low conviction")

        # 5-day price momentum (slope)
        if len(closes) >= 5:
            recent = closes[-5:]
            slope  = (recent[-1] - recent[0]) / recent[0] * 100
            if slope > 3:
                score += 0.2; detail.append(f"5-day trend +{slope:.1f}% — strong upward move")
            elif slope > 1:
                score += 0.1; detail.append(f"5-day trend +{slope:.1f}%")
            elif slope < -3:
                score -= 0.2; detail.append(f"5-day trend {slope:.1f}% — downward pressure")
            elif slope < -1:
                score -= 0.1; detail.append(f"5-day trend {slope:.1f}%")

    except Exception as e:
        detail.append(f"Partial data: {str(e)[:40]}")

    score = _clamp(score)
    return {
        "name":   "Supply & Demand",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "Insufficient data",
        "weight": WEIGHTS["supply_demand"],
    }


# ── F2: Company Performance ───────────────────────────────────

def _score_company(info: dict, fast_info) -> dict:
    """
    Signals: EPS, PE vs sector, dividend yield, 52-week position.
    """
    score  = 0.0
    detail = []

    try:
        # EPS
        eps = info.get("trailingEps")
        if eps is not None:
            eps = float(eps)
            if eps > 0:
                score += 0.3; detail.append(f"EPS ₹{eps:.2f} — profitable")
            else:
                score -= 0.4; detail.append(f"EPS ₹{eps:.2f} — loss-making")

        # PE ratio (reasonable range 10-40 for NSE)
        pe = info.get("trailingPE")
        if pe is not None:
            pe = float(pe)
            if 10 < pe < 25:
                score += 0.2; detail.append(f"PE {pe:.1f} — reasonable valuation")
            elif pe >= 25 and pe < 50:
                score += 0.0; detail.append(f"PE {pe:.1f} — growth priced in")
            elif pe >= 50:
                score -= 0.2; detail.append(f"PE {pe:.1f} — expensive valuation")
            elif pe <= 10:
                score += 0.1; detail.append(f"PE {pe:.1f} — value territory")

        # Dividend yield
        div_yield = info.get("dividendYield")
        if div_yield and float(div_yield) > 0:
            dy = float(div_yield) * 100
            score += 0.1; detail.append(f"Dividend yield {dy:.2f}%")

        # 52-week position
        high_52 = info.get("fiftyTwoWeekHigh")
        low_52  = info.get("fiftyTwoWeekLow")
        price   = float(fast_info.last_price)
        if high_52 and low_52:
            high_52 = float(high_52)
            low_52  = float(low_52)
            rng     = high_52 - low_52
            if rng > 0:
                position = (price - low_52) / rng   # 0 = at 52w low, 1 = at 52w high
                if position > 0.8:
                    score += 0.2; detail.append(f"Near 52-week high ({position*100:.0f}% of range)")
                elif position < 0.2:
                    score -= 0.1; detail.append(f"Near 52-week low ({position*100:.0f}% of range)")
                else:
                    detail.append(f"Mid-range ({position*100:.0f}% of 52-week range)")

    except Exception as e:
        detail.append(f"Partial data: {str(e)[:40]}")

    score = _clamp(score)
    return {
        "name":   "Company Performance",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "Insufficient data",
        "weight": WEIGHTS["company"],
    }


# ── F3: Economic Conditions ───────────────────────────────────

def _score_economic() -> dict:
    """
    Signals: Nifty 50 trend (proxy for macro health), RBI rate context.
    Falls back to static Indian macro context if APIs unavailable.
    """
    score  = 0.0
    detail = []

    try:
        # Use Nifty 50 trend as macro proxy — always available via yfinance
        nifty    = yf.Ticker(NIFTY50_SYMBOL)
        n_hist   = nifty.history(period="1mo", interval="1d")

        if not n_hist.empty:
            n_closes = n_hist["Close"].tolist()
            if len(n_closes) >= 2:
                n_slope = (n_closes[-1] - n_closes[0]) / n_closes[0] * 100
                if n_slope > 3:
                    score += 0.4; detail.append(f"Nifty up {n_slope:.1f}% this month — strong macro")
                elif n_slope > 0:
                    score += 0.2; detail.append(f"Nifty up {n_slope:.1f}% this month — positive macro")
                elif n_slope < -3:
                    score -= 0.4; detail.append(f"Nifty down {abs(n_slope):.1f}% this month — weak macro")
                else:
                    score -= 0.1; detail.append(f"Nifty down {abs(n_slope):.1f}% this month")

        # Static Indian macro context (updated manually or via FRED if key available)
        if FRED_API_KEY and FRED_API_KEY != "your_fred_key_here":
            fred_score, fred_detail = _fetch_fred_signal()
            score  += fred_score
            detail += fred_detail
        else:
            # Reasonable static context for Indian market
            detail.append("Macro: RBI repo rate 6.5% — stable policy")

    except Exception as e:
        score  = 0.0
        detail = [f"Macro data unavailable: {str(e)[:40]}"]

    score = _clamp(score)
    return {
        "name":   "Economic Conditions",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "No macro data available",
        "weight": WEIGHTS["economic"],
    }


def _fetch_fred_signal() -> tuple[float, list[str]]:
    """Fetch US Fed rate as global macro proxy from FRED API."""
    try:
        url    = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id":      "FEDFUNDS",
            "api_key":        FRED_API_KEY,
            "file_type":      "json",
            "sort_order":     "desc",
            "limit":          2,
        }
        r    = requests.get(url, params=params, timeout=8)
        obs  = r.json().get("observations", [])
        if len(obs) >= 2:
            latest = float(obs[0]["value"])
            prev   = float(obs[1]["value"])
            if latest > prev:
                return -0.2, [f"Fed rate rising ({latest:.2f}%) — global headwind"]
            elif latest < prev:
                return  0.2, [f"Fed rate easing ({latest:.2f}%) — global tailwind"]
            else:
                return  0.0, [f"Fed rate stable ({latest:.2f}%)"]
    except Exception:
        pass
    return 0.0, []


# ── F4: Market Sentiment ──────────────────────────────────────

BULLISH_WORDS = [
    "surge", "rally", "beat", "profit", "growth", "strong", "record",
    "upgrade", "outperform", "expansion", "bullish", "buy", "gains",
    "positive", "recovery", "robust", "optimistic", "soar", "jump"
]
BEARISH_WORDS = [
    "fall", "drop", "miss", "loss", "weak", "decline", "downgrade",
    "underperform", "contraction", "bearish", "sell", "slump",
    "negative", "concern", "risk", "crash", "plunge", "tumble", "cut"
]

def _score_sentiment(symbol: str, info: dict) -> dict:
    """
    Score news sentiment for the stock using NewsAPI.
    Falls back to yfinance recommendation key if NewsAPI unavailable.
    """
    score  = 0.0
    detail = []

    # Try NewsAPI
    if NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here":
        try:
            company_name = info.get("shortName", symbol.replace(".NS", ""))
            score, detail = _newsapi_sentiment(company_name)
        except Exception:
            pass

    # Fallback: yfinance analyst recommendation
    if not detail:
        rec = info.get("recommendationKey", "").lower()
        rec_map = {
            "strong_buy":  ( 0.8, "Analysts: strong buy"),
            "buy":         ( 0.5, "Analysts: buy"),
            "hold":        ( 0.0, "Analysts: hold"),
            "underperform":(-0.4, "Analysts: underperform"),
            "sell":        (-0.7, "Analysts: sell"),
        }
        if rec in rec_map:
            score, txt = rec_map[rec]
            detail      = [txt]
        else:
            detail = ["No sentiment data available"]

    score = _clamp(score)
    return {
        "name":   "Market Sentiment",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "No sentiment data",
        "weight": WEIGHTS["sentiment"],
    }


def _newsapi_sentiment(company_name: str) -> tuple[float, list[str]]:
    """Score sentiment from NewsAPI headlines."""
    url    = "https://newsapi.org/v2/everything"
    params = {
        "q":        f"{company_name} stock",
        "language": "en",
        "pageSize": 5,
        "sortBy":   "publishedAt",
        "apiKey":   NEWS_API_KEY,
    }
    r        = requests.get(url, params=params, timeout=8)
    articles = r.json().get("articles", [])

    if not articles:
        return 0.0, ["No recent news found"]

    total_score = 0.0
    for art in articles:
        text  = f"{art.get('title', '')} {art.get('description', '')}".lower()
        bulls = sum(1 for w in BULLISH_WORDS if w in text)
        bears = sum(1 for w in BEARISH_WORDS if w in text)
        total = bulls + bears
        if total > 0:
            total_score += (bulls - bears) / total

    avg = total_score / len(articles)
    label = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "mixed"
    return (
        round(avg, 3),
        [f"News sentiment: {label} across {len(articles)} recent articles"]
    )


# ── F5: External & Political ──────────────────────────────────

POLICY_BULLISH = [
    "stimulus", "reform", "infrastructure", "incentive", "subsidy",
    "ease", "cut rate", "deregulate", "boost", "support", "invest"
]
POLICY_BEARISH = [
    "sanction", "war", "conflict", "geopolitical", "ban", "regulate",
    "tax hike", "rate hike", "crisis", "inflation", "recession", "risk"
]

def _score_external(symbol: str, info: dict) -> dict:
    """
    Score macro/political news signals.
    Separate from F4 — focuses on policy/geopolitical keywords.
    """
    score  = 0.0
    detail = []

    if NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here":
        try:
            sector       = info.get("sector", "")
            company_name = info.get("shortName", symbol.replace(".NS", ""))
            query        = f"{company_name} government policy regulation India"
            url          = "https://newsapi.org/v2/everything"
            params       = {
                "q":        query,
                "language": "en",
                "pageSize": 5,
                "sortBy":   "publishedAt",
                "apiKey":   NEWS_API_KEY,
            }
            r        = requests.get(url, params=params, timeout=8)
            articles = r.json().get("articles", [])

            bull_hits = 0
            bear_hits = 0
            for art in articles:
                text = f"{art.get('title', '')} {art.get('description', '')}".lower()
                bull_hits += sum(1 for w in POLICY_BULLISH if w in text)
                bear_hits += sum(1 for w in POLICY_BEARISH if w in text)

            total = bull_hits + bear_hits
            if total > 0:
                score = (bull_hits - bear_hits) / total
                if score > 0.2:
                    detail.append(f"Positive policy signals detected ({bull_hits} bullish keywords)")
                elif score < -0.2:
                    detail.append(f"Risk/policy headwinds detected ({bear_hits} bearish keywords)")
                else:
                    detail.append("Mixed external signals — no strong political catalyst")
            else:
                detail.append("No significant political/policy news found")

        except Exception as e:
            detail.append(f"External signals data unavailable: {str(e)[:30]}")
    else:
        detail.append("External signals: no NewsAPI key — using neutral")

    score = _clamp(score)
    return {
        "name":   "External & Political",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "No external signals",
        "weight": WEIGHTS["external"],
    }


# ── F6: Liquidity & Activity ──────────────────────────────────

def _score_liquidity(fast_info, hist_20) -> dict:
    """
    Signals: volume vs 3-month avg, price vs 20-day VWAP.
    """
    score  = 0.0
    detail = []

    try:
        # Volume ratio
        avg_3m = float(fast_info.three_month_average_volume or 0)
        today  = float(fast_info.three_month_average_volume or 0)  # proxy

        if not hist_20.empty:
            recent_vols = hist_20["Volume"].tolist()
            recent_avg  = sum(recent_vols) / len(recent_vols) if recent_vols else 1

            if avg_3m > 0:
                ratio = recent_avg / avg_3m
                if ratio > 1.8:
                    score += 0.4; detail.append(f"Volume {ratio:.1f}x 3-month avg — very active")
                elif ratio > 1.3:
                    score += 0.2; detail.append(f"Volume {ratio:.1f}x 3-month avg — above average")
                elif ratio < 0.6:
                    score -= 0.3; detail.append(f"Volume {ratio:.1f}x 3-month avg — low activity")
                else:
                    detail.append(f"Volume {ratio:.1f}x 3-month avg — normal")

        # Price vs 20-day VWAP (proxy)
        if not hist_20.empty and len(hist_20) >= 5:
            closes  = hist_20["Close"].tolist()
            volumes = hist_20["Volume"].tolist()

            # VWAP = sum(close * volume) / sum(volume)
            total_vol  = sum(volumes)
            if total_vol > 0:
                vwap = sum(c * v for c, v in zip(closes, volumes)) / total_vol
                curr = float(fast_info.last_price)
                pct_vs_vwap = (curr - vwap) / vwap * 100

                if pct_vs_vwap > 2:
                    score += 0.3; detail.append(f"Price {pct_vs_vwap:.1f}% above VWAP — buying pressure")
                elif pct_vs_vwap > 0:
                    score += 0.1; detail.append(f"Price {pct_vs_vwap:.1f}% above VWAP")
                elif pct_vs_vwap < -2:
                    score -= 0.3; detail.append(f"Price {abs(pct_vs_vwap):.1f}% below VWAP — selling pressure")
                else:
                    score -= 0.1; detail.append(f"Price {abs(pct_vs_vwap):.1f}% below VWAP")

    except Exception as e:
        detail.append(f"Liquidity data partial: {str(e)[:40]}")

    score = _clamp(score)
    return {
        "name":   "Liquidity & Activity",
        "score":  score,
        "label":  _label(score),
        "detail": " | ".join(detail) or "Insufficient data",
        "weight": WEIGHTS["liquidity"],
    }


# ── RSI calculator ────────────────────────────────────────────

def _calc_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Standard RSI calculation from a list of closing prices."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i])  / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)