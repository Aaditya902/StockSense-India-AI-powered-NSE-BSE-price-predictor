"""
Service: News & Sentiment
Fetches last 5 news headlines for a stock and scores sentiment.

Primary  : NewsAPI (free tier — 100 req/day)
Fallback : yfinance news feed (no key needed)
Cache    : 15-minute per-symbol cache

Each article returns:
  title, source, published_at, url,
  sentiment ("positive" | "negative" | "neutral"),
  sentiment_score (-1.0 to +1.0)

Called by: GET /stock/{symbol}/news
"""

import time
import requests
import yfinance as yf
from datetime import datetime, timezone

from config import NEWS_API_KEY



_cache: dict[str, dict] = {}   # { "RELIANCE.NS": { data, expires_at } }
CACHE_TTL = 900                # 15 minutes



BULLISH_WORDS = [
    "surge", "rally", "beat", "profit", "growth", "strong", "record",
    "upgrade", "outperform", "expansion", "bullish", "gains", "positive",
    "recovery", "robust", "optimistic", "soar", "jump", "rise", "high",
    "boost", "buy", "opportunity", "upside", "breakout", "momentum",
]
BEARISH_WORDS = [
    "fall", "drop", "miss", "loss", "weak", "decline", "downgrade",
    "underperform", "bearish", "slump", "negative", "concern", "risk",
    "crash", "plunge", "tumble", "cut", "warning", "sell", "downside",
    "pressure", "struggle", "trouble", "crisis", "fear", "uncertain",
]


def get_stock_news(symbol: str, company_name: str = "") -> dict:
    """
    Fetch and score news for a stock.
    Returns structured response with articles + overall sentiment.
    """
    now = time.time()

    # Cache hit
    if symbol in _cache and now < _cache[symbol]["expires_at"]:
        return _cache[symbol]["data"]

    # Determine company name for search query
    if not company_name:
        company_name = _get_company_name(symbol)

    # Try NewsAPI first
    articles = []
    source   = "none"

    if NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here":
        try:
            articles = _fetch_newsapi(company_name, symbol)
            source   = "newsapi"
        except Exception as e:
            print(f"[NewsService] NewsAPI failed: {e} — trying yfinance")

    # Fallback to yfinance news
    if not articles:
        try:
            articles = _fetch_yfinance_news(symbol)
            source   = "yfinance"
        except Exception as e:
            print(f"[NewsService] yfinance news failed: {e}")

    # Score each article
    scored = [_score_article(a) for a in articles]

    # Overall sentiment
    if scored:
        avg = sum(a["sentiment_score"] for a in scored) / len(scored)
    else:
        avg = 0.0

    overall = "positive" if avg > 0.15 else "negative" if avg < -0.15 else "neutral"

    result = {
        "symbol":            symbol,
        "articles":          scored,
        "overall_sentiment": overall,
        "overall_score":     round(avg, 3),
        "source":            source,
        "last_updated":      datetime.now(timezone.utc).isoformat(),
    }

    _cache[symbol] = {"data": result, "expires_at": now + CACHE_TTL}
    return result


def _fetch_newsapi(company_name: str, symbol: str) -> list[dict]:
    """
    Fetch from NewsAPI.
    Two queries: company name + stock market context.
    """
    clean_sym = symbol.replace(".NS", "").replace(".BO", "")
    query     = f'"{company_name}" OR "{clean_sym}" stock NSE India'

    url    = "https://newsapi.org/v2/everything"
    params = {
        "q":        query,
        "language": "en",
        "pageSize": 5,
        "sortBy":   "publishedAt",
        "apiKey":   NEWS_API_KEY,
    }

    r        = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    raw      = r.json().get("articles", [])

    articles = []
    for a in raw[:5]:
        if not a.get("title") or a["title"] == "[Removed]":
            continue
        articles.append({
            "title":        a.get("title", ""),
            "source":       a.get("source", {}).get("name", "Unknown"),
            "published_at": a.get("publishedAt", ""),
            "url":          a.get("url", ""),
            "description":  a.get("description", ""),
        })

    return articles


def _fetch_yfinance_news(symbol: str) -> list[dict]:
    """
    yfinance provides basic news via ticker.news.
    Less rich than NewsAPI but always available.
    """
    ticker   = yf.Ticker(symbol)
    raw_news = ticker.news or []

    articles = []
    for item in raw_news[:5]:
        # yfinance news format varies by version
        title   = item.get("title", "")
        if not title:
            continue

        # Convert Unix timestamp to ISO string
        pub_ts  = item.get("providerPublishTime", 0)
        pub_dt  = datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat() \
                  if pub_ts else ""

        articles.append({
            "title":        title,
            "source":       item.get("publisher", "Unknown"),
            "published_at": pub_dt,
            "url":          item.get("link", ""),
            "description":  item.get("summary", ""),
        })

    return articles



def _score_article(article: dict) -> dict:
    """
    Score a single article using keyword matching.
    Returns the article dict with sentiment fields added.
    """
    text  = f"{article.get('title','')} {article.get('description','')}".lower()

    bulls = sum(1 for w in BULLISH_WORDS if w in text)
    bears = sum(1 for w in BEARISH_WORDS if w in text)
    total = bulls + bears

    if total == 0:
        score     = 0.0
        sentiment = "neutral"
    else:
        score     = round((bulls - bears) / total, 3)
        sentiment = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"

    return {
        "title":           article["title"],
        "source":          article["source"],
        "published_at":    article["published_at"],
        "url":             article["url"],
        "sentiment":       sentiment,
        "sentiment_score": score,
    }



def _get_company_name(symbol: str) -> str:
    """Get company short name from yfinance for search query."""
    try:
        info = yf.Ticker(symbol).info
        return info.get("shortName") or info.get("longName") or symbol.replace(".NS", "")
    except Exception:
        return symbol.replace(".NS", "").replace(".BO", "")


def invalidate_cache(symbol: str = None):
    """Clear cache for one symbol or all symbols."""
    if symbol:
        _cache.pop(symbol, None)
    else:
        _cache.clear()