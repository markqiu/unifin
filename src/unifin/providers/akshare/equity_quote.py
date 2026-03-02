"""AKShare fetcher for equity_quote.

Uses ak.stock_sh_a_spot_em() / ak.stock_sz_a_spot_em() for A-share real-time quotes.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class AKShareEquityQuoteFetcher(Fetcher):
    """Fetch equity real-time quotes from AKShare (EastMoney source)."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "equity_quote"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XHKG,
    ]

    supported_fields: ClassVar[list[str]] = [
        "symbol",
        "name",
        "last_price",
        "open",
        "high",
        "low",
        "prev_close",
        "volume",
        "change",
        "change_percent",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Real-time or 15-min delayed A-share quotes from EastMoney via AKShare. "
        "Fetches bulk market data and filters by symbol. "
        "Does not provide bid/ask, year_high/low, or market_cap."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        symbol = getattr(query, "symbol", "")
        return {"symbol": symbol}

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is not installed. pip install 'unifin[akshare]'")

        symbol = params["symbol"]
        # Strip MIC suffix to get plain code
        code = symbol.split(".")[0] if "." in symbol else symbol

        # Try each market's spot data
        spot_apis = [
            ("ak.stock_sh_a_spot_em", lambda: ak.stock_sh_a_spot_em()),
            ("ak.stock_sz_a_spot_em", lambda: ak.stock_sz_a_spot_em()),
        ]

        for api_name, api_fn in spot_apis:
            try:
                df = api_fn()
                if df is None or df.empty:
                    continue
                # Filter for the specific symbol
                code_col = "代码" if "代码" in df.columns else None
                if code_col is None:
                    continue
                match = df[df[code_col] == code]
                if not match.empty:
                    return match.to_dict(orient="records")
            except Exception:
                continue

        # Try HK
        try:
            df = ak.stock_hk_spot_em()
            if df is not None and not df.empty:
                code_col = "代码" if "代码" in df.columns else None
                if code_col:
                    match = df[df[code_col] == code]
                    if not match.empty:
                        return match.to_dict(orient="records")
        except Exception:
            pass

        return []

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if not raw_data:
            return []

        results = []
        for item in raw_data:
            results.append(
                {
                    "symbol": item.get("代码"),
                    "name": item.get("名称"),
                    "last_price": item.get("最新价"),
                    "open": item.get("今开"),
                    "high": item.get("最高"),
                    "low": item.get("最低"),
                    "prev_close": item.get("昨收"),
                    "volume": item.get("成交量"),
                    "amount": item.get("成交额"),
                    "change": item.get("涨跌额"),
                    "change_percent": item.get("涨跌幅"),
                    "turnover_rate": item.get("换手率"),
                    "year_high": None,
                    "year_low": None,
                    "market_cap": item.get("流通市值"),
                    "bid_price": None,
                    "bid_size": None,
                    "ask_price": None,
                    "ask_size": None,
                    "timestamp": None,
                }
            )

        return results


provider_registry.register_fetcher(AKShareEquityQuoteFetcher)
