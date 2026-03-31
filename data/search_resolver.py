"""
Search Resolver — Step 1 output
Powers the GET /search?q= endpoint.

Usage:
    from search_resolver import SearchResolver
    resolver = SearchResolver()
    results = resolver.search("reliance")   # → list of matches
    symbol  = resolver.resolve("Reliance")  # → "RELIANCE.NS"
"""

import json
import os
from typing import Optional

DATA_PATH = os.path.join(os.path.dirname(__file__), "nse_stocks.json")


class SearchResolver:
    def __init__(self):
        with open(DATA_PATH, encoding="utf-8") as f:
            self._data = json.load(f)
        self._stocks = self._data["stocks"]

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        """
        Fuzzy search by name, keyword, or symbol.
        Returns list of {name, symbol, sector} dicts.
        """
        q = query.lower().strip()
        if not q:
            return []

        results = []
        seen = set()

        for stock in self._stocks:
            sym = stock["symbol"]
            if sym in seen:
                continue
            name_lower = stock["name"].lower()
            sym_lower = sym.lower().replace(".ns", "")
            keywords = [k.lower() for k in stock.get("keywords", [])]

            if (
                name_lower.startswith(q)
                or sym_lower.startswith(q)
                or any(k.startswith(q) for k in keywords)
            ):
                results.append(self._format(stock))
                seen.add(sym)

        if len(results) < max_results:
            for stock in self._stocks:
                sym = stock["symbol"]
                if sym in seen:
                    continue
                name_lower = stock["name"].lower()
                sym_lower = sym.lower()
                keywords = [k.lower() for k in stock.get("keywords", [])]
                all_text = f"{name_lower} {sym_lower} {' '.join(keywords)}"

                if q in all_text:
                    results.append(self._format(stock))
                    seen.add(sym)
                    if len(results) >= max_results:
                        break

        if len(results) < max_results:
            query_words = q.split()
            for stock in self._stocks:
                sym = stock["symbol"]
                if sym in seen:
                    continue
                name_lower = stock["name"].lower()
                keywords = [k.lower() for k in stock.get("keywords", [])]
                all_text = f"{name_lower} {' '.join(keywords)}"

                if any(word in all_text for word in query_words):
                    results.append(self._format(stock))
                    seen.add(sym)
                    if len(results) >= max_results:
                        break

        return results[:max_results]

    def resolve(self, query: str) -> Optional[str]:
        """
        Resolve a name/keyword to an NSE symbol.
        Returns the best match symbol or None.
        e.g. "Reliance" → "RELIANCE.NS"
        """
        results = self.search(query, max_results=1)
        return results[0]["symbol"] if results else None

    def get_by_symbol(self, symbol: str) -> Optional[dict]:
        """
        Get stock info by exact symbol.
        e.g. "RELIANCE.NS" → {name, symbol, sector}
        """
        sym = symbol.upper()
        if not sym.endswith(".NS"):
            sym += ".NS"
        stock = self._data["by_symbol"].get(sym)
        return self._format(stock) if stock else None

    def get_by_sector(self, sector: str) -> list[dict]:
        """Return all stocks in a given sector."""
        symbols = self._data["sectors"].get(sector, [])
        results = []
        for sym in symbols:
            stock = self._data["by_symbol"].get(sym)
            if stock:
                results.append(self._format(stock))
        return results

    def all_stocks(self) -> list[dict]:
        """Return full list for frontend autocomplete."""
        return [self._format(s) for s in self._stocks]

    @staticmethod
    def _format(stock: dict) -> dict:
        return {
            "name": stock["name"],
            "symbol": stock["symbol"],
            "sector": stock["sector"],
        }