"""AKShare fetcher for equity_search.

Uses ak.stock_info_a_code_name() to get all A-share symbols,
then filters by query string.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


def _infer_exchange(code: str) -> str:
    """Infer exchange name from A-share code prefix."""
    if code.startswith("6"):
        return "XSHG"
    elif code.startswith(("0", "3")):
        return "XSHE"
    elif code.startswith(("4", "8")):
        return "XBSE"
    return ""


class AKShareEquitySearchFetcher(Fetcher):
    """Search A-share equities using AKShare."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "equity_search"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XBSE,
    ]

    supported_fields: ClassVar[list[str]] = [
        "symbol",
        "name",
        "exchange",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Returns all A-share symbols from ak.stock_info_a_code_name(), "
        "filtered by query. Does not provide asset_type, list_date, or is_active."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        q = getattr(query, "query", "")
        limit = getattr(query, "limit", None)
        return {"query": q, "limit": limit or 100}

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is not installed. pip install 'unifin[akshare]'")

        try:
            df = ak.stock_info_a_code_name()
            if df is None or df.empty:
                return []
            return df.to_dict(orient="records")
        except Exception:
            return []

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if not raw_data:
            return []

        search_query = getattr(query, "query", "")
        limit = getattr(query, "limit", 100) or 100

        results = []
        for item in raw_data:
            code = str(item.get("code", ""))
            name = str(item.get("name", ""))

            # Filter by query string (match code or name)
            if search_query and search_query not in name and search_query not in code:
                continue

            exchange = _infer_exchange(code)
            results.append(
                {
                    "symbol": f"{code}.{exchange}" if exchange else code,
                    "name": name,
                    "exchange": exchange,
                    "asset_type": "EQUITY",
                    "list_date": None,
                    "is_active": None,
                }
            )

            if len(results) >= limit:
                break

        return results


provider_registry.register_fetcher(AKShareEquitySearchFetcher)
