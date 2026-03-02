"""YFinance fetcher for equity_profile."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceEquityProfileFetcher(Fetcher):
    """Fetch company profile from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "equity_profile"
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

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "symbol",
        "name",
        "legal_name",
        "exchange",
        "sector",
        "industry",
        "employees",
        "description",
        "country",
        "city",
        "website",
        "market_cap",
        "currency",
        "is_active",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Does not provide CEO or list_date. Non-US company profiles may have limited coverage."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        return {"symbol": getattr(query, "symbol", "")}

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        ticker = yf.Ticker(params["symbol"])
        info = ticker.info
        return info if info else {}

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if not raw_data:
            return []

        info = raw_data if isinstance(raw_data, dict) else {}
        if not info.get("symbol"):
            return []

        return [
            {
                "symbol": info.get("symbol"),
                "name": info.get("shortName") or info.get("longName"),
                "legal_name": info.get("longName"),
                "exchange": info.get("exchange"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "description": info.get("longBusinessSummary"),
                "country": info.get("country"),
                "city": info.get("city"),
                "website": info.get("website"),
                "ceo": None,  # yfinance doesn't have CEO directly
                "market_cap": info.get("marketCap"),
                "currency": info.get("currency"),
                "list_date": None,
                "is_active": True,  # if accessible via yfinance, it's active
            }
        ]


provider_registry.register_fetcher(YFinanceEquityProfileFetcher)
