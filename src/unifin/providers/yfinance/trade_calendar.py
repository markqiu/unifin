"""YFinance fetcher for trade_calendar.

Yahoo Finance does not expose a native trading calendar API.
This fetcher generates a calendar by downloading a known liquid ticker's
historical data for the requested period — any date with a trade record
is treated as an open day.

Limitations:
  - Only supports markets where a representative ticker is known.
  - Cannot detect half-days or early closes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange, Market

# Representative high-liquidity tickers per market.
# If the ticker traded on a given day, the market was open.
_MARKET_PROXY: dict[Market, tuple[str, str]] = {
    # (yfinance_symbol, market_label)
    Market.US: ("SPY", "us"),
    Market.CN: ("000001.SS", "cn"),
    Market.HK: ("0005.HK", "hk"),
    Market.JP: ("^N225", "jp"),
    Market.GB: ("^FTSE", "gb"),
    Market.DE: ("^GDAXI", "de"),
    Market.AU: ("^AXJO", "au"),
    Market.KR: ("^KS11", "kr"),
    Market.CA: ("XIU.TO", "ca"),
    Market.SG: ("^STI", "sg"),
    Market.IN: ("^BSESN", "in"),
    Market.TW: ("^TWII", "tw"),
}


class YFinanceTradeCalendarFetcher(Fetcher):
    """Derive trading calendar from Yahoo Finance historical data."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "trade_calendar"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS, Exchange.XNAS,
        Exchange.XSHG, Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX, Exchange.XLON,
        Exchange.XETR,
        Exchange.XASX, Exchange.XKRX,
        Exchange.XTSE, Exchange.XSES,
        Exchange.XBOM, Exchange.XNSE,
        Exchange.XTAI,
    ]

    supported_fields: ClassVar[list[str]] = ["date", "is_open", "market"]
    data_start_date: ClassVar[str] = "1990-01-01"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Calendar is inferred from actual trade dates of a proxy ticker. "
        "Half-days and early closes are not distinguished. "
        "Requires network access and is best suited for historical lookback."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        today = dt.date.today()
        market: Market = getattr(query, "market", Market.CN)
        start = getattr(query, "start_date", None) or (today - dt.timedelta(days=365))
        end = getattr(query, "end_date", None) or today

        proxy_symbol, market_label = _MARKET_PROXY.get(market, ("SPY", market.value))

        return {
            "symbol": proxy_symbol,
            "start": start.isoformat(),
            "end": (end + dt.timedelta(days=1)).isoformat(),
            "market": market_label,
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        ticker = yf.Ticker(params["symbol"])
        df = ticker.history(start=params["start"], end=params["end"], interval="1d")

        if df is None or df.empty:
            return {"dates": [], "market": params["market"]}

        # Extract dates where trades occurred
        trade_dates = sorted(d.date() if hasattr(d, "date") else d for d in df.index)
        return {"dates": trade_dates, "market": params["market"]}

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        dates = raw_data.get("dates", [])
        market = raw_data.get("market", "")

        return [
            {"date": d, "is_open": True, "market": market}
            for d in dates
        ]


provider_registry.register_fetcher(YFinanceTradeCalendarFetcher)
