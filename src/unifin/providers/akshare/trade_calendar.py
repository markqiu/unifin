"""AKShare fetcher for trade_calendar.

Uses ak.tool_trade_date_hist_sina() to get the full list of historical
A-share trading dates from Sina Finance.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange, Market


class AKShareTradeCalendarFetcher(Fetcher):
    """Fetch A-share trading calendar from AKShare (Sina source)."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "trade_calendar"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG,
        Exchange.XSHE,
    ]

    supported_fields: ClassVar[list[str]] = ["date", "is_open", "market"]
    data_start_date: ClassVar[str] = "1990-12-19"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "A-share trading calendar from Sina via ak.tool_trade_date_hist_sina(). "
        "Only supports market='cn'. All returned dates are open days."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        today = dt.date.today()
        market: Market = getattr(query, "market", Market.CN)
        start = getattr(query, "start_date", None) or (today - dt.timedelta(days=365))
        end = getattr(query, "end_date", None) or today

        return {
            "market": market.value,
            "start_date": start,
            "end_date": end,
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is not installed. pip install 'unifin[akshare]'")

        # Only CN market supported
        if params["market"] != "cn":
            return {"dates": [], "market": params["market"]}

        try:
            df = ak.tool_trade_date_hist_sina()
            if df is None or df.empty:
                return {"dates": [], "market": params["market"]}

            # df contains a single column of trading dates
            dates = []
            start = params["start_date"]
            end = params["end_date"]

            for _, row in df.iterrows():
                # The column is typically "trade_date" as a date-like value
                d = row.iloc[0]
                if hasattr(d, "date"):
                    d = d.date()
                elif isinstance(d, str):
                    d = dt.date.fromisoformat(d)

                if isinstance(d, dt.date) and start <= d <= end:
                    dates.append(d)

            return {"dates": sorted(dates), "market": params["market"]}
        except Exception:
            return {"dates": [], "market": params["market"]}

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        dates = raw_data.get("dates", [])
        market = raw_data.get("market", "cn")

        return [{"date": d, "is_open": True, "market": market} for d in dates]


provider_registry.register_fetcher(AKShareTradeCalendarFetcher)
