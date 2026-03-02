"""AKShare fetcher for etf_search.

Tries ak.fund_name_em() to get a comprehensive ETF list,
then filters by query string.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class AKShareEtfSearchFetcher(Fetcher):
    """Search ETFs using AKShare (EastMoney source)."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "etf_search"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG,
        Exchange.XSHE,
    ]

    supported_fields: ClassVar[list[str]] = [
        "symbol",
        "name",
        "fund_type",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "ETF list from ak.fund_name_em() or ak.fund_etf_spot_em(). "
        "Covers Shanghai and Shenzhen listed ETFs. "
        "Does not provide fund_family, expense_ratio, or total_assets."
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

        # Approach 1: fund_name_em (comprehensive fund list including ETFs)
        try:
            df = ak.fund_name_em()
            if df is not None and not df.empty:
                return {"source": "fund_name_em", "data": df}
        except Exception:
            pass

        # Approach 2: fund_etf_spot_em (ETF spot data)
        try:
            df = ak.fund_etf_spot_em()
            if df is not None and not df.empty:
                return {"source": "fund_etf_spot_em", "data": df}
        except Exception:
            pass

        return {"source": "none", "data": None}

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        source = raw_data.get("source", "none")
        data = raw_data.get("data")

        if data is None or (hasattr(data, "empty") and data.empty):
            return []

        search_query = getattr(query, "query", "")
        limit = getattr(query, "limit", 100) or 100

        records = data.to_dict(orient="records")
        results = []

        for item in records:
            # Normalize column names from different APIs
            symbol = str(
                item.get("基金代码", "") or item.get("代码", "") or item.get("symbol", "")
            ).strip()
            name = str(
                item.get("基金简称", "") or item.get("名称", "") or item.get("name", "")
            ).strip()
            fund_type = str(item.get("基金类型", "") or item.get("type", "")).strip()

            if not symbol:
                continue

            # For fund_name_em, filter to ETF types only
            if source == "fund_name_em" and fund_type:
                if "ETF" not in fund_type.upper() and "交易型" not in fund_type:
                    continue

            # Apply search filter
            if search_query and search_query not in name and search_query not in symbol:
                continue

            results.append(
                {
                    "symbol": symbol,
                    "name": name or None,
                    "exchange": None,
                    "fund_family": None,
                    "fund_type": fund_type or "ETF",
                    "list_date": None,
                    "expense_ratio": None,
                    "total_assets": None,
                }
            )

            if len(results) >= limit:
                break

        return results


provider_registry.register_fetcher(AKShareEtfSearchFetcher)
