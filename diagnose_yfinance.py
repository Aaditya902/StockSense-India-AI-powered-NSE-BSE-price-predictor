"""
Run this script FIRST to diagnose yfinance on your machine.

Usage:
  python diagnose_yfinance.py

It will tell you exactly which method works and what data is available.
"""

import sys
print(f"Python: {sys.version}")

try:
    import yfinance as yf
    print(f"yfinance: {yf.__version__}")
except ImportError:
    print("yfinance NOT installed. Run: pip install yfinance")
    sys.exit(1)

print("\n--- Testing RELIANCE.NS ---\n")

ticker = yf.Ticker("RELIANCE.NS")

# Test 1: fast_info
print("Test 1: fast_info")
try:
    fi = ticker.fast_info
    print(f"  last_price:     {fi.last_price}")
    print(f"  previous_close: {fi.previous_close}")
    print(f"  day_high:       {fi.day_high}")
    print(f"  day_low:        {fi.day_low}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 2: history
print("\nTest 2: history(period='5d')")
try:
    hist = ticker.history(period="5d")
    print(f"  rows returned: {len(hist)}")
    if not hist.empty:
        print(f"  last close:    {hist['Close'].iloc[-1]:.2f}")
        print(f"  dates:         {[str(d.date()) for d in hist.index[-3:]]}")
    else:
        print("  EMPTY — no data returned")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 3: history 1mo
print("\nTest 3: history(period='1mo')")
try:
    hist = ticker.history(period="1mo")
    print(f"  rows returned: {len(hist)}")
    if not hist.empty:
        print(f"  last close: {hist['Close'].iloc[-1]:.2f}")
    else:
        print("  EMPTY")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 4: download
print("\nTest 4: yf.download")
try:
    import pandas as pd
    df = yf.download("RELIANCE.NS", period="5d", progress=False)
    print(f"  rows returned: {len(df)}")
    if not df.empty:
        print(f"  last close: {df['Close'].iloc[-1]:.2f}")
    else:
        print("  EMPTY")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 5: ticker.info
print("\nTest 5: ticker.info (slowest)")
try:
    info = ticker.info
    price_keys = {k: v for k, v in info.items()
                  if any(x in k.lower() for x in ["price", "close", "open", "high", "low"])
                  and v and v != 0}
    if price_keys:
        for k, v in list(price_keys.items())[:6]:
            print(f"  {k}: {v}")
    else:
        print("  No price data in info dict")
        print(f"  Total keys: {len(info)}")
        if info:
            print(f"  Sample keys: {list(info.keys())[:5]}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 6: NSE index
print("\nTest 6: ^NSEI (Nifty50)")
try:
    nifty = yf.Ticker("^NSEI")
    hist  = nifty.history(period="5d")
    print(f"  rows: {len(hist)}")
    if not hist.empty:
        print(f"  last close: {hist['Close'].iloc[-1]:.2f}")
    else:
        print("  EMPTY")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 7: US stock (always available)
print("\nTest 7: AAPL (US stock — should always work)")
try:
    aapl = yf.Ticker("AAPL")
    hist = aapl.history(period="5d")
    print(f"  rows: {len(hist)}")
    if not hist.empty:
        print(f"  last close: {hist['Close'].iloc[-1]:.2f}")
    else:
        print("  EMPTY — yfinance itself may be broken")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n--- Done ---")
print("\nShare the output of this script to diagnose the issue.")