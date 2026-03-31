"""
ML: LSTM Training Script
Trains the LSTM model for a given NSE stock symbol.

Usage:
  python train.py --symbol RELIANCE.NS
  python train.py --symbol TCS.NS --epochs 100
  python train.py --symbol HDFCBANK.NS --years 3

What it does:
  1. Downloads 2 years of OHLCV history from yfinance
  2. Engineers 7 features (RSI, MACD, SMA, etc.)
  3. Creates 60-day lookback sequences
  4. Trains LSTM model (80/20 train/val split)
  5. Saves model + scalers to ml/models/{SYMBOL}/
  6. Prints final MAE and a sample prediction

Run this once per stock before using the prediction endpoint.
Takes ~5 minutes on CPU for 2 years of daily data.
"""

import os
import sys
import json
import pickle
import argparse
import numpy as np
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.lstm_model import (
    build_features,
    prepare_sequences,
    build_model,
    EPOCHS,
    BATCH_SIZE,
    LOOKBACK,
)


# ── Paths ─────────────────────────────────────────────────────

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def get_model_dir(symbol: str) -> str:
    """Returns path to model directory for a symbol."""
    safe_sym = symbol.replace(".", "_").replace("^", "")
    return os.path.join(MODELS_DIR, safe_sym)


def model_exists(symbol: str) -> bool:
    """Check if a trained model exists for this symbol."""
    d = get_model_dir(symbol)
    return (
        os.path.exists(os.path.join(d, "model.keras")) and
        os.path.exists(os.path.join(d, "scalers.pkl")) and
        os.path.exists(os.path.join(d, "meta.json"))
    )


# ── Training ──────────────────────────────────────────────────

def train(symbol: str, years: int = 2, epochs: int = EPOCHS) -> dict:
    """
    Full training pipeline for a stock symbol.
    Returns metadata dict with training results.
    """
    print(f"\n{'='*50}")
    print(f"  Training LSTM for: {symbol}")
    print(f"  History: {years} years  |  Epochs: {epochs}")
    print(f"{'='*50}\n")

    # ── Step 1: Download history ──────────────────────────────
    print("1. Downloading historical data...")
    period = f"{years}y"
    hist   = yf.Ticker(symbol).history(period=period, interval="1d")

    if hist.empty or len(hist) < LOOKBACK + 50:
        raise ValueError(
            f"Insufficient data for {symbol}. "
            f"Got {len(hist)} rows, need at least {LOOKBACK + 50}."
        )
    print(f"   Downloaded {len(hist)} trading days")

    # ── Step 2: Feature engineering ───────────────────────────
    print("2. Engineering features...")
    features = build_features(hist)
    print(f"   Features: {list(features.columns)}")
    print(f"   Rows after feature build: {len(features)}")

    # ── Step 3: Prepare sequences ─────────────────────────────
    print("3. Preparing sequences...")
    X, y, scaler, close_scaler = prepare_sequences(features, LOOKBACK)
    print(f"   X shape: {X.shape}  y shape: {y.shape}")

    # Train / validation split
    split  = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]
    print(f"   Train: {len(X_train)} samples  |  Val: {len(X_val)} samples")

    # ── Step 4: Build and train model ─────────────────────────
    print("4. Building model...")
    model = build_model(LOOKBACK, X.shape[2])
    model.summary()

    print("\n5. Training...")
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

    callbacks = [
        EarlyStopping(
            monitor   = "val_loss",
            patience  = 10,
            restore_best_weights = True,
            verbose   = 1,
        ),
        ReduceLROnPlateau(
            monitor  = "val_loss",
            factor   = 0.5,
            patience = 5,
            verbose  = 1,
        ),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data = (X_val, y_val),
        epochs          = epochs,
        batch_size      = BATCH_SIZE,
        callbacks       = callbacks,
        verbose         = 1,
    )

    # ── Step 5: Evaluate ──────────────────────────────────────
    print("\n6. Evaluating...")
    val_loss, val_mae = model.evaluate(X_val, y_val, verbose=0)

    # MAE in original ₹ scale
    # val_mae is normalised — convert back to approximate ₹ error
    price_range = float(features["close"].max() - features["close"].min())
    mae_rupees  = val_mae * price_range
    print(f"   Val loss: {val_loss:.6f}")
    print(f"   Val MAE (normalised): {val_mae:.4f}")
    print(f"   Val MAE (~₹): {mae_rupees:.2f}")

    # ── Step 6: Sample prediction ─────────────────────────────
    from ml.lstm_model import predict_next_price
    last_60    = features.tail(LOOKBACK)
    pred_price = predict_next_price(model, last_60, close_scaler, scaler)
    actual_last = float(features["close"].iloc[-1])
    print(f"\n   Last known price : ₹{actual_last:,.2f}")
    print(f"   Predicted next   : ₹{pred_price:,.2f}")
    print(f"   Delta            : {((pred_price - actual_last) / actual_last * 100):+.2f}%")

    # ── Step 7: Save model + scalers ──────────────────────────
    print("\n7. Saving model...")
    model_dir = get_model_dir(symbol)
    os.makedirs(model_dir, exist_ok=True)

    # Save model
    model.save(os.path.join(model_dir, "model.keras"))

    # Save scalers
    with open(os.path.join(model_dir, "scalers.pkl"), "wb") as f:
        pickle.dump({"scaler": scaler, "close_scaler": close_scaler}, f)

    # Save metadata
    meta = {
        "symbol":          symbol,
        "trained_on":      str(features.index[-1].date()),
        "n_rows":          len(features),
        "lookback":        LOOKBACK,
        "n_features":      X.shape[2],
        "epochs_run":      len(history.history["loss"]),
        "val_loss":        round(val_loss, 6),
        "val_mae_norm":    round(val_mae, 4),
        "val_mae_rupees":  round(mae_rupees, 2),
        "last_price":      actual_last,
        "predicted_next":  pred_price,
    }
    with open(os.path.join(model_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n   Saved to: {model_dir}/")
    print(f"     model.keras")
    print(f"     scalers.pkl")
    print(f"     meta.json")
    print(f"\nTraining complete for {symbol}!")
    return meta


# ── Loader (used by prediction service) ──────────────────────

def load_model(symbol: str):
    """
    Load trained model + scalers for inference.
    Called by the prediction service at request time.
    Returns: (model, scaler, close_scaler, meta)
    """
    import pickle
    from tensorflow.keras.models import load_model as keras_load

    model_dir = get_model_dir(symbol)

    if not model_exists(symbol):
        raise FileNotFoundError(
            f"No trained model found for {symbol}. "
            f"Run: python ml/train.py --symbol {symbol}"
        )

    model        = keras_load(os.path.join(model_dir, "model.keras"))
    with open(os.path.join(model_dir, "scalers.pkl"), "rb") as f:
        scalers  = pickle.load(f)
    with open(os.path.join(model_dir, "meta.json")) as f:
        meta     = json.load(f)

    return model, scalers["scaler"], scalers["close_scaler"], meta


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LSTM for an NSE stock")
    parser.add_argument("--symbol", required=True,  help="NSE symbol e.g. RELIANCE.NS")
    parser.add_argument("--years",  type=int, default=2, help="Years of history (default 2)")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help=f"Max epochs (default {EPOCHS})")
    args = parser.parse_args()

    # Normalise symbol
    sym = args.symbol.upper()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        sym += ".NS"

    meta = train(sym, years=args.years, epochs=args.epochs)

    print("\n── Summary ──────────────────────────────")
    print(f"  Symbol      : {meta['symbol']}")
    print(f"  Trained on  : {meta['trained_on']}")
    print(f"  Data rows   : {meta['n_rows']}")
    print(f"  Epochs run  : {meta['epochs_run']}")
    print(f"  MAE (~₹)    : {meta['val_mae_rupees']}")
    print(f"  Last price  : ₹{meta['last_price']:,.2f}")
    print(f"  Next pred   : ₹{meta['predicted_next']:,.2f}")