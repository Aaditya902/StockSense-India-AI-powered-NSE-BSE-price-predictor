"""
Router: Search
Endpoint: GET /search?q=reliance

Returns a list of matching NSE stocks for the search query.
Powers the frontend search bar autocomplete dropdown.
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
from search_resolver import SearchResolver

router = APIRouter(prefix="/search", tags=["Search"])

# Initialise once at startup — loads JSON into memory
_resolver = SearchResolver()


# ── Response model ────────────────────────────────────────────

class StockMatch(BaseModel):
    name:   str
    symbol: str
    sector: str


class SearchResponse(BaseModel):
    query:   str
    count:   int
    results: list[StockMatch]


# ── Endpoint ──────────────────────────────────────────────────

@router.get("", response_model=SearchResponse)
def search_stocks(
    q: str = Query(..., min_length=1, max_length=50, description="Stock name or symbol")
):
    """
    Search for NSE stocks by name, symbol, or keyword.

    Examples:
      GET /search?q=reliance   → Reliance Industries
      GET /search?q=tcs        → TCS
      GET /search?q=jio        → Reliance Industries  (keyword match)
      GET /search?q=bank       → All banks
      GET /search?q=hdfc       → HDFC Bank, HDFC Life
    """
    if len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="Query too short")

    matches = _resolver.search(q.strip(), max_results=8)

    return SearchResponse(
        query=q,
        count=len(matches),
        results=[StockMatch(**m) for m in matches]
    )


@router.get("/all", response_model=list[StockMatch])
def get_all_stocks(
    exchange: str = Query("NSE", description="NSE | BSE | ALL"),
    limit: int    = Query(500,   description="Max results (default 500)"),
):
    """
    Returns all available stocks from NSE and/or BSE.
    Powered by Upstox instrument master — thousands of stocks.
    exchange: NSE | BSE | ALL
    limit: max results to return (default 500 for frontend performance)
    """
    try:
        from backend.services.instruments import get_all_stocks as _dynamic, total_count
        stocks = get_all_stocks(exchange)
        result = [
            StockMatch(
                name   = s.get("name", s.get("short_name", "")),
                symbol = s.get("symbol", ""),
                sector = s.get("exchange", ""),
            )
            for s in stocks[:limit]
            if s.get("symbol")
        ]
        if result:
            return result
    except Exception:
        pass
    return [StockMatch(**s) for s in _resolver.all_stocks()][:limit]


@router.get("/count")
def get_stock_count():
    """Returns total number of available instruments."""
    try:
        from backend.services.instruments import total_count
        return {"total": total_count(), "source": "upstox_instruments"}
    except Exception:
        return {"total": len(_resolver.all_stocks()), "source": "static_json"}


@router.get("/sector/{sector}", response_model=list[StockMatch])
def get_by_sector(sector: str):
    """
    Returns all stocks in a given sector.

    Example:
      GET /search/sector/IT        → all IT stocks
      GET /search/sector/Banking   → all banks
    """
    stocks = _resolver.get_by_sector(sector)
    if not stocks:
        raise HTTPException(status_code=404, detail=f"No stocks found for sector: {sector}")
    return [StockMatch(**s) for s in stocks]