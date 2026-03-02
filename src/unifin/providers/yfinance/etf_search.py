"""YFinance fetcher for etf_search."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceEtfSearchFetcher(Fetcher):
    """Search ETFs using Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "etf_search"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS,
        Exchange.XNAS,
        Exchange.XASE,
        Exchange.ARCX,
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX,
        Exchange.XLON,
        Exchange.XPAR,
        Exchange.XAMS,
        Exchange.XETR,
        Exchange.XSWX,
        Exchange.XMIL,
        Exchange.XSES,
        Exchange.XASX,
        Exchange.XKRX,
        Exchange.XTAI,
        Exchange.XBOM,
        Exchange.XNSE,
        Exchange.XTSE,
    ]

    supported_fields: ClassVar[list[str]] = [
        "symbol",
        "name",
        "exchange",
        "fund_type",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Uses yf.Search with 'ETF' appended to query to bias results toward ETFs. "
        "Does not provide fund_family, list_date, expense_ratio, or total_assets. "
        "Coverage of non-US ETFs may be limited."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        q = getattr(query, "query", "")
        limit = getattr(query, "limit", None)
        return {"query": q, "limit": limit or 25}

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        query = params["query"]
        if not query:
            return []

        # Append "ETF" to bias search toward ETFs
        search_query = f"{query} ETF" if "etf" not in query.lower() else query
        try:
            results = yf.Search(search_query)
            quotes = results.quotes if hasattr(results, "quotes") else []
            # Filter results to ETF-like types
            etf_types = {"ETF", "MUTUALFUND"}
            filtered = [
                q
                for q in quotes
                if isinstance(q, dict) and q.get("quoteType", "").upper() in etf_types
            ]
            # If filtering produced nothing, return all results (may include non-ETFs)
            return (filtered or quotes)[: params["limit"]]
        except Exception:
            return []

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if not raw_data:
            return []

        results = []
        for item in raw_data:
            if isinstance(item, dict):
                results.append(
                    {
                        "symbol": item.get("symbol"),
                        "name": (
                            item.get("shortname")
                            or item.get("longname")
                            or item.get("shortName")
                            or item.get("longName")
                        ),
                        "exchange": item.get("exchange") or item.get("exchDisp"),
                        "fund_family": None,
                        "fund_type": item.get("quoteType") or item.get("typeDisp"),
                        "list_date": None,
                        "expense_ratio": None,
                        "total_assets": None,
                    }
                )
        return results


provider_registry.register_fetcher(YFinanceEtfSearchFetcher)
