"""
Service: Prediction Engine
Combines LSTM model output with AI reasoning (Groq/Gemini)
to produce a final predicted price range and % upside/downside.

Pipeline:
  1. Load trained LSTM model for the symbol
  2. Fetch last 60 days of features
  3. LSTM predicts next close price (70% weight)
  4. Groq/Gemini reads factor scores + news → adjustment multiplier (30% weight)
  5. Fuse into predicted range: mid ± volatility band
  6. Compute % upside or downside vs current price

Fallback chain (app never crashes):
  Tier 1 → LSTM model + AI adjustment   (best quality)
  Tier 2 → Factor-score-only rule       (no trained model needed)
  Tier 3 → Current price + disclaimer   (last resort)

Called by: GET /stock/{symbol}/predict
"""

import os
import sys
import yfinance as yf
from backend.services.yf_session import get_ticker
import requests
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config import (
    GROQ_API_KEY, GEMINI_API_KEY,
    GROQ_MODEL,   GEMINI_MODEL,
    PREDICTION_HORIZON_DAYS,
    has_groq, has_gemini,
)


# ── Weights ───────────────────────────────────────────────────

LSTM_WEIGHT = 0.70
AI_WEIGHT   = 0.30

# Confidence thresholds based on factor score alignment
CONFIDENCE_HIGH   =  0.40   # overall factor score above this
CONFIDENCE_LOW    = -0.10   # overall factor score below this


# ── Main function ─────────────────────────────────────────────

def get_prediction(symbol: str, factors: dict) -> dict:
    """
    Generate price prediction for a stock.

    Tier 1 → LSTM model + AI  (best — needs trained model)
    Tier 2 → Factor score + AI (works without trained model)
    Tier 3 → Safe fallback     (always returns something)
    """
    try:
        current_price = _get_current_price(symbol)
    except Exception:
        current_price = 0.0

    # Tier 1: LSTM + AI
    if current_price > 0:
        try:
            return _predict_lstm_plus_ai(symbol, current_price, factors)
        except Exception as e:
            print(f"[Prediction] Tier 1 failed: {e}")

    # Tier 2: Factor rule + AI (works without any trained model)
    if current_price > 0:
        try:
            return _predict_factor_only(symbol, current_price, factors)
        except Exception as e:
            print(f"[Prediction] Tier 2 failed: {e}")

    # Tier 3: safe fallback
    return _predict_safe_fallback(symbol, current_price)


# ── Tier 1: LSTM + AI ─────────────────────────────────────────

def _predict_lstm_plus_ai(symbol: str, current_price: float, factors: dict) -> dict:
    """
    Load trained LSTM model, predict next close,
    then adjust using Groq/Gemini reasoning.
    """
    from ml.train      import load_model, model_exists
    from ml.lstm_model import build_features, predict_next_price

    if not model_exists(symbol):
        raise FileNotFoundError(f"No trained model for {symbol}")

    # Load model
    model, scaler, close_scaler, meta = load_model(symbol)

    # Fetch recent history for prediction window
    hist     = get_ticker(symbol).history(period="90d", interval="1d")
    if hist.empty:
        raise RuntimeError("No history available for prediction")

    features = build_features(hist)
    if len(features) < 60:
        raise RuntimeError(f"Need 60+ rows, got {len(features)}")

    # LSTM raw prediction
    lstm_price = predict_next_price(model, features, close_scaler, scaler)

    # AI adjustment
    ai_mult, ai_reasoning, model_used = _get_ai_adjustment(symbol, factors, current_price)

    # Weighted fusion
    ai_price  = current_price * ai_mult
    mid_price = round(LSTM_WEIGHT * lstm_price + AI_WEIGHT * ai_price, 2)

    return _build_response(
        symbol        = symbol,
        current_price = current_price,
        mid_price     = mid_price,
        factors       = factors,
        ai_reasoning  = ai_reasoning,
        model_used    = f"lstm+{model_used}",
    )


# ── Tier 2: Factor score only ─────────────────────────────────

def _predict_factor_only(symbol: str, current_price: float, factors: dict) -> dict:
    """
    No trained model available.
    Use overall factor score as a directional signal to estimate price.
    This is rule-based, not ML-based.
    """
    overall = factors.get("overall_score", 0.0)

    # Map factor score to expected % move
    # Score of +1.0 → +8% expected | Score of -1.0 → -8% expected
    expected_pct = overall * 8.0
    mid_price    = round(current_price * (1 + expected_pct / 100), 2)

    ai_mult, ai_reasoning, model_used = _get_ai_adjustment(
        symbol, factors, current_price
    )

    # Blend factor estimate with AI
    ai_price  = current_price * ai_mult
    mid_price = round(0.6 * mid_price + 0.4 * ai_price, 2)

    return _build_response(
        symbol        = symbol,
        current_price = current_price,
        mid_price     = mid_price,
        factors       = factors,
        ai_reasoning  = ai_reasoning,
        model_used    = f"factor_rule+{model_used}",
    )


# ── Tier 3: Safe fallback ─────────────────────────────────────

def _predict_safe_fallback(symbol: str, current_price: float) -> dict:
    """Last resort — returns current price with honest disclaimer."""
    return {
        "symbol":          symbol,
        "current_price":   current_price,
        "predicted_low":   current_price,
        "predicted_high":  current_price,
        "predicted_mid":   current_price,
        "change_pct_low":  0.0,
        "change_pct_high": 0.0,
        "change_pct_mid":  0.0,
        "direction":       "flat",
        "horizon_days":    PREDICTION_HORIZON_DAYS,
        "confidence":      "low",
        "ai_reasoning":    "Prediction temporarily unavailable. Using factor analysis above as a guide.",
        "model_used":      "none",
        "last_updated":    datetime.now(timezone.utc).isoformat(),
    }


# ── Shared response builder ───────────────────────────────────

def _build_response(
    symbol:        str,
    current_price: float,
    mid_price:     float,
    factors:       dict,
    ai_reasoning:  str,
    model_used:    str,
) -> dict:
    """
    Build the full prediction response dict from a mid price.
    Adds a ± volatility band based on factor confidence.
    """
    overall     = factors.get("overall_score", 0.0)

    # Volatility band: tighter when factors are aligned, wider when mixed
    # Scale: high confidence = ±1.5%, low confidence = ±4%
    band_pct    = 4.0 - abs(overall) * 2.5   # 1.5% to 4%
    band        = mid_price * (band_pct / 100)

    pred_low    = round(mid_price - band, 2)
    pred_high   = round(mid_price + band, 2)

    def pct_change(target):
        return round((target - current_price) / current_price * 100, 2)

    chg_low  = pct_change(pred_low)
    chg_mid  = pct_change(mid_price)
    chg_high = pct_change(pred_high)

    direction   = "upside" if chg_mid > 0 else "downside" if chg_mid < 0 else "flat"

    # Confidence based on factor alignment
    if overall >= CONFIDENCE_HIGH:
        confidence = "high"
    elif overall <= CONFIDENCE_LOW:
        confidence = "low"
    else:
        confidence = "medium"

    return {
        "symbol":          symbol,
        "current_price":   current_price,
        "predicted_low":   pred_low,
        "predicted_high":  pred_high,
        "predicted_mid":   mid_price,
        "change_pct_low":  chg_low,
        "change_pct_high": chg_high,
        "change_pct_mid":  chg_mid,
        "direction":       direction,
        "horizon_days":    PREDICTION_HORIZON_DAYS,
        "confidence":      confidence,
        "ai_reasoning":    ai_reasoning,
        "model_used":      model_used,
        "last_updated":    datetime.now(timezone.utc).isoformat(),
    }


# ── AI adjustment (Groq primary → Gemini fallback) ────────────

def _get_ai_adjustment(
    symbol:        str,
    factors:       dict,
    current_price: float,
) -> tuple[float, str, str]:
    """
    Ask Groq (or Gemini) to reason over factor scores and suggest
    a price adjustment multiplier.

    Returns: (multiplier, reasoning_text, model_name)
    e.g.    (1.045, "Strong bullish signals across...", "groq")

    Multiplier: 1.0 = no change | 1.05 = +5% | 0.97 = -3%
    """
    prompt = _build_ai_prompt(symbol, factors, current_price)

    # Try Groq first
    if has_groq():
        try:
            mult, reasoning = _call_groq(prompt)
            return mult, reasoning, "groq"
        except Exception as e:
            print(f"[PredictionEngine] Groq failed: {e} — trying Gemini")

    # Try Gemini
    if has_gemini():
        try:
            mult, reasoning = _call_gemini(prompt)
            return mult, reasoning, "gemini"
        except Exception as e:
            print(f"[PredictionEngine] Gemini failed: {e} — using factor default")

    # Both failed — use factor score as multiplier directly
    overall  = factors.get("overall_score", 0.0)
    mult     = 1.0 + (overall * 0.05)   # max ±5%
    return mult, "AI reasoning unavailable — using factor score estimate.", "none"


def _build_ai_prompt(symbol: str, factors: dict, current_price: float) -> str:
    """Build a concise prompt for Groq/Gemini."""
    factor_lines = "\n".join(
        f"  {f['name']}: {f['label'].upper()} (score {f['score']:+.2f}) — {f['detail']}"
        for f in factors.get("factors", [])
    )
    overall = factors.get("overall_score", 0.0)
    label   = factors.get("overall_label", "neutral")

    return f"""You are a quantitative stock analyst for Indian equities (NSE).

Stock: {symbol}
Current price: ₹{current_price:,.2f}
Overall signal: {label.upper()} (score: {overall:+.2f})

Factor analysis:
{factor_lines}

Based on these 6 factor signals, estimate the likely price direction 
and magnitude over the next 7 trading days.

Respond in this EXACT format — no other text:
MULTIPLIER: <number between 0.85 and 1.15>
REASONING: <2-3 sentences explaining your assessment>

Rules:
- MULTIPLIER > 1.0 means expected price increase
- MULTIPLIER < 1.0 means expected price decrease  
- MULTIPLIER = 1.0 means no expected change
- Maximum range: 0.85 to 1.15 (never exceed ±15%)
- Be conservative — most stocks move ±5% in a week"""


def _parse_ai_response(text: str) -> tuple[float, str]:
    """
    Parse AI response into (multiplier, reasoning).
    Safe parser — never crashes on unexpected output.
    """
    multiplier = 1.0
    reasoning  = text.strip()

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("MULTIPLIER:"):
            try:
                val = float(line.split(":", 1)[1].strip())
                # Safety clamp — never let AI suggest wild swings
                multiplier = max(0.85, min(1.15, val))
            except (ValueError, IndexError):
                pass
        elif line.startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return multiplier, reasoning


def _call_groq(prompt: str) -> tuple[float, str]:
    """Call Groq API with Llama 3."""
    url     = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  200,
        "temperature": 0.3,   # low temp for more consistent financial reasoning
    }
    r   = requests.post(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"]
    return _parse_ai_response(txt)


def _call_gemini(prompt: str) -> tuple[float, str]:
    """Call Gemini API."""
    url     = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 200,
            "temperature":     0.3,
        },
    }
    r   = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_ai_response(txt)


# ── Utility ───────────────────────────────────────────────────

def _get_current_price(symbol: str) -> float:
    """
    Fetch current price — tries 3 sources, never raises.
    Returns 0.0 only as absolute last resort.
    """
    # Source 1: NSE direct
    try:
        from backend.services.nse_direct import get_quote
        price = get_quote(symbol).get("price", 0)
        if price and price > 0:
            return round(float(price), 2)
    except Exception:
        pass

    # Source 2: yfinance history
    try:
        hist = get_ticker(symbol).history(period="5d", interval="1d")
        if not hist.empty:
            closes = hist["Close"].dropna().tolist()
            if closes:
                return round(float(closes[-1]), 2)
    except Exception:
        pass

    # Source 3: yfinance fast_info
    try:
        price = get_ticker(symbol).fast_info.last_price
        if price and float(price) > 0:
            return round(float(price), 2)
    except Exception:
        pass

    raise RuntimeError(f"Cannot fetch current price for {symbol}")