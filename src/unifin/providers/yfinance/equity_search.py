"""YFinance fetcher for equity_search."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceEquitySearchFetcher(Fetcher):
    """Search equities using Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "equity_search"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS, Exchange.XNAS, Exchange.XASE, Exchange.ARCX,
        Exchange.XSHG, Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX, Exchange.XLON, Exchange.XPAR, Exchange.XAMS,
        Exchange.XETR, Exchange.XSWX, Exchange.XMIL,
        Exchange.XSES, Exchange.XASX, Exchange.XKRX, Exchange.XTAI,
        Exchange.XBOM, Exchange.XNSE, Exchange.XTSE,
    ]

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "symbol", "name", "exchange", "asset_type",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Does not provide list_date or is_active. "
        "Search quality varies; non-US results may be incomplete."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        q = getattr(query, "query", "")
        limit = getattr(query, "limit", None)
        is_symbol = getattr(query, "is_symbol", False)
        return {"query": q, "limit": limit or 25, "is_symbol": is_symbol}

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        query = params["query"]
        if not query:
            return []

        # Use yfinance search
        try:
            results = yf.Search(query)
            quotes = results.quotes if hasattr(results, "quotes") else []
            return quotes[: params["limit"]]
        except Exception:
            # Fallback: try as a single ticker
            try:
                ticker = yf.Ticker(query)
                info = ticker.info
                if info and info.get("symbol"):
                    return [info]
            except Exception:
                pass
            return []

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if not raw_data:
            return []

        results = []
        for item in raw_data:
            if isinstance(item, dict):
                results.append({
                    "symbol": item.get("symbol"),
                    "name": item.get("shortname") or item.get("longname") or item.get("shortName") or item.get("longName"),
                    "exchange": item.get("exchange") or item.get("exchDisp"),
                    "asset_type": item.get("quoteType") or item.get("typeDisp"),
                    "list_date": None,
                    "is_active": None,
                })
        return results


provider_registry.register_fetcher(YFinanceEquitySearchFetcher)
