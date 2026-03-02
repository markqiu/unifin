"""YFinance fetcher for equity_quote."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceEquityQuoteFetcher(Fetcher):
    """Fetch real-time / delayed equity quote from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "equity_quote"
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
        "last_price", "open", "high", "low", "close", "prev_close",
        "volume", "change", "change_percent",
        "bid", "bid_size", "ask", "ask_size",
        "year_high", "year_low", "market_cap", "timestamp",
    ]
    data_start_date: ClassVar[str] = ""
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "US quotes are 15-min delayed. Does not provide amount (turnover). "
        "Bid/ask may be unavailable outside market hours."
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

        # Parse timestamp
        ts = None
        reg_ts = info.get("regularMarketTime")
        if reg_ts:
            try:
                ts = datetime.fromtimestamp(reg_ts)
            except (TypeError, ValueError, OSError):
                pass

        return [{
            "symbol": info.get("symbol"),
            "name": info.get("shortName") or info.get("longName"),
            "exchange": info.get("exchange"),
            "asset_type": info.get("quoteType"),
            "last_price": info.get("regularMarketPrice") or info.get("currentPrice"),
            "open": info.get("regularMarketOpen") or info.get("open"),
            "high": info.get("regularMarketDayHigh") or info.get("dayHigh"),
            "low": info.get("regularMarketDayLow") or info.get("dayLow"),
            "close": info.get("regularMarketPreviousClose") or info.get("previousClose"),
            "prev_close": info.get("regularMarketPreviousClose") or info.get("previousClose"),
            "volume": _safe_int(info.get("regularMarketVolume") or info.get("volume")),
            "amount": None,
            "change": info.get("regularMarketChange"),
            "change_percent": _to_ratio(info.get("regularMarketChangePercent")),
            "bid": info.get("bid"),
            "bid_size": _safe_int(info.get("bidSize")),
            "ask": info.get("ask"),
            "ask_size": _safe_int(info.get("askSize")),
            "year_high": info.get("fiftyTwoWeekHigh"),
            "year_low": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "timestamp": ts,
        }]


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_ratio(v: Any) -> float | None:
    """Convert percentage to ratio (yfinance returns percent, we store ratio)."""
    if v is None:
        return None
    try:
        return float(v) / 100.0
    except (ValueError, TypeError):
        return None


provider_registry.register_fetcher(YFinanceEquityQuoteFetcher)
