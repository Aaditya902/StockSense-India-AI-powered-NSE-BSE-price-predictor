"""
Search Resolver — Dynamic version
Now powered by instruments.py which has ALL NSE/BSE stocks.
Falls back to static nse_stocks.json if instruments not loaded.
"""

import sys
import os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class SearchResolver:

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search all NSE/BSE stocks dynamically."""
        q = query.strip()
        if not q:
            return []

        # Try dynamic instruments first
        try:
            from backend.services.instruments import search_stocks
            results = search_stocks(q, max_results=max_results)
            if results:
                return [self._format(r) for r in results]
        except Exception:
            pass

        # Fallback to static JSON
        return self._static_search(q, max_results)

    def resolve(self, query: str) -> Optional[str]:
        """Resolve a name/keyword to best matching symbol."""
        results = self.search(query, max_results=1)
        return results[0]["symbol"] if results else None

    def all_stocks(self) -> list[dict]:
        """Return all available stocks."""
        try:
            from backend.services.instruments import get_all_stocks
            stocks = get_all_stocks()
            if stocks:
                return [self._format(s) for s in stocks]
        except Exception:
            pass
        return self._static_all()

    def get_by_symbol(self, symbol: str) -> Optional[dict]:
        try:
            from backend.services.instruments import get_by_symbol
            s = get_by_symbol(symbol)
            return self._format(s) if s else None
        except Exception:
            return None

    def get_by_sector(self, sector: str) -> list[dict]:
        """Sector filtering — works on static data only for now."""
        return self._static_sector(sector)

    # ── Formatters ────────────────────────────────────────────

    @staticmethod
    def _format(stock: dict) -> dict:
        return {
            "name":   stock.get("name") or stock.get("short_name", ""),
            "symbol": stock.get("symbol", ""),
            "sector": stock.get("sector") or stock.get("exchange", ""),
        }

    # ── Static fallbacks ──────────────────────────────────────

    def _static_search(self, query: str, max_results: int) -> list[dict]:
        data   = self._load_static()
        q      = query.lower().strip()
        result = []
        seen   = set()

        for stock in data.get("stocks", []):
            sym = stock["symbol"]
            if sym in seen:
                continue
            name_l = stock["name"].lower()
            sym_l  = sym.lower()
            kws    = [k.lower() for k in stock.get("keywords", [])]
            all_t  = f"{name_l} {sym_l} {' '.join(kws)}"
            if q in all_t:
                result.append(self._format(stock))
                seen.add(sym)
                if len(result) >= max_results:
                    break
        return result

    def _static_all(self) -> list[dict]:
        data = self._load_static()
        return [self._format(s) for s in data.get("stocks", [])]

    def _static_sector(self, sector: str) -> list[dict]:
        data    = self._load_static()
        symbols = data.get("sectors", {}).get(sector, [])
        by_sym  = data.get("by_symbol", {})
        return [self._format(by_sym[s]) for s in symbols if s in by_sym]

    @staticmethod
    def _load_static() -> dict:
        import json
        path = os.path.join(os.path.dirname(__file__), "nse_stocks.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"stocks": [], "by_symbol": {}, "sectors": {}}