"""AKShare fetcher for equity_historical.

A-shares: ak.stock_zh_a_hist()
HK: ak.stock_hk_hist()
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Adjust, Exchange, Interval

_PERIOD_MAP: dict[Interval, str] = {
    Interval.DAILY: "daily",
    Interval.WEEKLY: "weekly",
    Interval.MONTHLY: "monthly",
}

_ADJUST_MAP: dict[Adjust, str] = {
    Adjust.NONE: "",
    Adjust.FORWARD: "qfq",
    Adjust.BACKWARD: "hfq",
}


class AKShareEquityHistoricalFetcher(Fetcher):
    """Fetch equity historical data from AKShare (EastMoney source)."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "equity_historical"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG, Exchange.XSHE, Exchange.XHKG,
    ]

    supported_fields: ClassVar[list[str]] = [
        "date", "open", "high", "low", "close", "volume", "amount",
    ]
    data_start_date: ClassVar[str] = "1990-12-19"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Data from EastMoney via AKShare. Daily/weekly/monthly only. "
        "Supports qfq (前复权) and hfq (后复权). "
        "Does not provide vwap or turnover_rate."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        today = dt.date.today()
        start = getattr(query, "start_date", None) or (today - dt.timedelta(days=365))
        end = getattr(query, "end_date", None) or today
        interval = getattr(query, "interval", Interval.DAILY)
        adjust = getattr(query, "adjust", Adjust.NONE)
        symbol = getattr(query, "symbol", "")

        return {
            "symbol": symbol,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
            "period": _PERIOD_MAP.get(interval, "daily"),
            "adjust": _ADJUST_MAP.get(adjust, ""),
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is not installed. pip install 'unifin[akshare]'")

        symbol = params["symbol"]
        # Detect market from symbol format
        # After Router conversion, akshare symbols are plain codes (e.g. "000001", "600519")
        # HK symbols may come as "0700" or similar

        # Check if it looks like an HK stock (typically 4-5 digits, sometimes starts with 0)
        # For simplicity, try A-share first, fall back to HK
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=params["period"],
                start_date=params["start_date"],
                end_date=params["end_date"],
                adjust=params["adjust"],
            )
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

        # Try HK
        try:
            df = ak.stock_hk_hist(
                symbol=symbol,
                period=params["period"],
                start_date=params["start_date"],
                end_date=params["end_date"],
                adjust=params["adjust"],
            )
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

        return None

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if raw_data is None or (hasattr(raw_data, "empty") and raw_data.empty):
            return []

        # AKShare returns a pandas DataFrame with Chinese column names
        col_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }

        records = raw_data.to_dict(orient="records")
        results = []
        for row in records:
            mapped = {}
            for cn_name, en_name in col_map.items():
                if cn_name in row:
                    mapped[en_name] = row[cn_name]
            # Ensure required fields
            if "date" in mapped:
                mapped.setdefault("open", None)
                mapped.setdefault("high", None)
                mapped.setdefault("low", None)
                mapped.setdefault("close", None)
                mapped.setdefault("volume", None)
                mapped.setdefault("amount", None)
                mapped["vwap"] = None
                mapped["turnover_rate"] = None
                results.append(mapped)

        return results


provider_registry.register_fetcher(AKShareEquityHistoricalFetcher)
