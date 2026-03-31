"""
ML: Batch Training Script
Trains LSTM models for a curated list of popular NSE stocks.

Usage:
  python ml/train_batch.py                    # trains all stocks in list
  python ml/train_batch.py --only RELIANCE TCS HDFCBANK

This script skips stocks that already have a saved model unless
--retrain flag is passed.

Estimated time: ~5 min per stock on CPU.
For 10 stocks: ~50 minutes total.
Run this overnight or on a machine you don't need for a while.
"""

import os
import sys
import argparse
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.train import train, model_exists

DEFAULT_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "AXISBANK.NS",
    "WIPRO.NS",
    "TATAMOTORS.NS",
    "BAJFINANCE.NS",
    "ZOMATO.NS",
    "ADANIENT.NS",
    "MARUTI.NS",
    "LT.NS",
]


def train_batch(symbols: list[str], retrain: bool = False, years: int = 2) -> None:
    """
    Train LSTM models for all symbols in the list.
    Skips already-trained models unless retrain=True.
    """
    total    = len(symbols)
    success  = []
    failed   = []

    print(f"\nBatch training {total} stocks")
    print(f"{'='*50}\n")

    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{total}] {symbol}")

        if model_exists(symbol) and not retrain:
            print(f"  Skipping — model already exists. Use --retrain to force.")
            success.append(symbol)
            continue

        t_start = time.time()
        try:
            meta = train(symbol, years=years)
            elapsed = time.time() - t_start
            print(f"  Done in {elapsed:.0f}s — MAE ₹{meta['val_mae_rupees']:.2f}")
            success.append(symbol)
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((symbol, str(e)))

    print(f"\n{'='*50}")
    print(f"Batch training complete")
    print(f"  Success : {len(success)} / {total}")
    print(f"  Failed  : {len(failed)} / {total}")

    if failed:
        print("\nFailed stocks:")
        for sym, err in failed:
            print(f"  {sym}: {err}")

    print(f"\nModels saved to: ml/models/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch train LSTM for NSE stocks")
    parser.add_argument(
        "--only",
        nargs="+",
        help="Train only specific symbols e.g. --only RELIANCE TCS"
    )
    parser.add_argument(
        "--retrain",
        action="store_true",
        help="Retrain even if model already exists"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=2,
        help="Years of training history (default 2)"
    )
    args = parser.parse_args()

    if args.only:
        symbols = [
            s.upper() + (".NS" if not s.upper().endswith(".NS") else "")
            for s in args.only
        ]
    else:
        symbols = DEFAULT_SYMBOLS

    train_batch(symbols, retrain=args.retrain, years=args.years)