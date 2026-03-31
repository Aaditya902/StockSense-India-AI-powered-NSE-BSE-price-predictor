"""
ML: LSTM Model Definition + Feature Engineering
Defines the model architecture and all feature calculations.

Architecture:
  Input  → LSTM(128) → LSTM(64) → Dense(32) → Dropout(0.2) → Dense(1)
Features: Close, Open, Volume, RSI-14, MACD, SMA-20, Price/SMA ratio
Window  : 60-day lookback → predict next day close price
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


LOOKBACK   = 60      # days of history as input window
N_FEATURES = 7       # number of input features per day
EPOCHS     = 50
BATCH_SIZE = 32
VALIDATION_SPLIT = 0.2


def build_features(hist: pd.DataFrame) -> pd.DataFrame:
    """
    Take raw yfinance OHLCV history and produce a feature DataFrame.
    All features are calculated here — one row per trading day.

    Input columns expected: Open, High, Low, Close, Volume
    Output columns: close, open, volume, rsi, macd, sma20, price_sma_ratio
    """
    df = hist.copy()
    df.columns = [c.lower() for c in df.columns]

    delta   = df["close"].diff()
    gain    = delta.clip(lower=0)
    loss    = -delta.clip(upper=0)
    avg_g   = gain.ewm(com=13, adjust=False).mean()
    avg_l   = loss.ewm(com=13, adjust=False).mean()
    rs      = avg_g / avg_l.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)        # neutral fallback

    # ── MACD (12/26 EMA difference, normalised by price) ──────
    ema12      = df["close"].ewm(span=12, adjust=False).mean()
    ema26      = df["close"].ewm(span=26, adjust=False).mean()
    macd_raw   = ema12 - ema26
    # Normalise MACD as % of price so it's scale-independent
    df["macd"] = macd_raw / df["close"]

    # ── SMA 20 ────────────────────────────────────────────────
    df["sma20"] = df["close"].rolling(window=20).mean()
    df["sma20"] = df["sma20"].fillna(df["close"])   # fill early rows

    # ── Price / SMA ratio (momentum signal) ───────────────────
    df["price_sma_ratio"] = df["close"] / df["sma20"]

    features = df[["close", "open", "volume", "rsi", "macd", "sma20", "price_sma_ratio"]]

    features = features.dropna()

    return features


def prepare_sequences(features: pd.DataFrame, lookback: int = LOOKBACK):
    """
    Convert feature DataFrame into (X, y) sequences for LSTM training.

    X shape: (n_samples, lookback, n_features)
    y shape: (n_samples,)  — next day close price (raw, unscaled)

    Returns: X, y, scaler (fitted on close column only for inverse transform)
    """
    # Scale all features to 0–1
    scaler    = MinMaxScaler(feature_range=(0, 1))
    scaled    = scaler.fit_transform(features.values)

    # Close is feature index 0 — we predict this
    close_scaler = MinMaxScaler(feature_range=(0, 1))
    close_scaler.fit(features[["close"]].values)

    X, y = [], []
    for i in range(lookback, len(scaled)):
        X.append(scaled[i - lookback : i])         # 60 days of all features
        y.append(scaled[i, 0])                     # next day close (scaled)

    return np.array(X), np.array(y), scaler, close_scaler


def build_model(lookback: int = LOOKBACK, n_features: int = N_FEATURES):
    """
    Build and return the LSTM model.
    Uses tensorflow.keras — installed as part of tensorflow.
    """
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.optimizers import Adam

    model = Sequential([
        # Layer 1: LSTM with sequence output (feeds into layer 2)
        LSTM(
            128,
            return_sequences=True,
            input_shape=(lookback, n_features)
        ),
        Dropout(0.2),

        # Layer 2: LSTM — outputs single vector
        LSTM(64, return_sequences=False),
        Dropout(0.2),

        # Dense head
        Dense(32, activation="relu"),
        Dropout(0.2),

        # Output: single price value
        Dense(1),
    ])

    model.compile(
        optimizer = Adam(learning_rate=0.001),
        loss      = "mean_squared_error",
        metrics   = ["mae"],
    )

    return model


def predict_next_price(
    model,
    recent_features: pd.DataFrame,
    close_scaler,
    scaler,
    lookback: int = LOOKBACK,
) -> float:
    """
    Given the last `lookback` days of features, predict the next close price.

    Returns: predicted price in original ₹ scale (not normalised)
    """
    if len(recent_features) < lookback:
        raise ValueError(f"Need at least {lookback} rows, got {len(recent_features)}")

    # Use last `lookback` rows
    window = recent_features.tail(lookback).values
    scaled = scaler.transform(window)

    # Shape: (1, lookback, n_features)
    X = np.expand_dims(scaled, axis=0)

    # Predict (returns scaled value)
    pred_scaled = model.predict(X, verbose=0)[0][0]

    # Inverse transform back to ₹
    pred_price  = close_scaler.inverse_transform([[pred_scaled]])[0][0]
    return round(float(pred_price), 2)