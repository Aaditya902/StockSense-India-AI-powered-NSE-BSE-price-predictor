"""
Run this to diagnose and fix the Yahoo Finance block.
Usage: python fix_yahoo.py
"""

import sys
import requests

print("=== Step 1: Testing raw Yahoo Finance connectivity ===\n")

urls_to_test = [
    ("Yahoo Finance v8 chart",  "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=5d"),
    ("Yahoo Finance v2 quote",  "https://query2.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=5d"),
    ("Yahoo Finance home",      "https://finance.yahoo.com"),
    ("Google (connectivity)",   "https://www.google.com"),
]

for label, url in urls_to_test:
    try:
        r = requests.get(url, timeout=8)
        print(f"  {label}: HTTP {r.status_code}  ({len(r.content)} bytes)")
    except Exception as e:
        print(f"  {label}: FAILED — {e}")

print()
print("=== Step 2: Testing with browser headers ===\n")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://finance.yahoo.com",
}

try:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?interval=1d&range=5d"
    r   = requests.get(url, headers=HEADERS, timeout=10)
    print(f"  With headers: HTTP {r.status_code}  ({len(r.content)} bytes)")
    if r.status_code == 200:
        import json
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c]
            print(f"  Last close: {closes[-1]:.2f}" if closes else "  No price data in response")
        else:
            err = data.get("chart", {}).get("error", "unknown")
            print(f"  API error: {err}")
    else:
        print(f"  Response: {r.text[:200]}")
except Exception as e:
    print(f"  With headers: FAILED — {e}")

print()
print("=== Step 3: Testing nsepy (alternative to yfinance) ===\n")
try:
    import nsepy
    print("  nsepy is installed")
except ImportError:
    print("  nsepy not installed — run: pip install nsepy")

print()
print("=== Step 4: Testing jugaad-finance / nsetools ===\n")
try:
    import nsetools
    print("  nsetools is installed")
except ImportError:
    print("  nsetools not installed")

print()
print("=== Diagnosis ===\n")
print("If Google works but Yahoo fails: Yahoo is blocked on your network/ISP.")
print("If both fail: No internet connection from this machine.")
print("If Yahoo works with headers: yfinance cookie/crumb issue — fixable.")
print()
print("=== Recommended fixes based on result ===")
print()
print("Fix A — Force yfinance to use a fresh cookie:")
print("  pip install yfinance --upgrade")
print("  python -c \"import yfinance; yfinance.utils.get_all_by_isin('INE002A01018')\"")
print()
print("Fix B — Use yfinance with proxy bypass:")
print("  Set env variable: set YFINANCE_PROXY=socks5://127.0.0.1:1080")
print()
print("Fix C — Switch to NSE direct API (no Yahoo needed):")
print("  pip install jugaad-data")
print()
print("Fix D — Upgrade yfinance (it has cookie auto-refresh in newer versions):")
print("  pip install yfinance==0.2.54")