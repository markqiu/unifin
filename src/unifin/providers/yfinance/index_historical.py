"""YFinance fetcher for index_historical."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange, Interval

# yfinance uses caret-prefixed symbols for major indices
_INDEX_SYMBOL_MAP: dict[str, str] = {
    # US
    "^GSPC": "^GSPC",  # S&P 500
    "^DJI": "^DJI",  # Dow Jones
    "^IXIC": "^IXIC",  # NASDAQ Composite
    "^RUT": "^RUT",  # Russell 2000
    "^VIX": "^VIX",  # VIX
    # China — Shanghai indices
    "000001.XSHG": "000001.SS",
    "000300.XSHG": "000300.SS",
    "000016.XSHG": "000016.SS",
    "000905.XSHG": "000905.SS",
    "000688.XSHG": "000688.SS",
    # China — Shenzhen indices
    "399001.XSHE": "399001.SZ",
    "399006.XSHE": "399006.SZ",
    "399005.XSHE": "399005.SZ",
    # Hong Kong
    "^HSI": "^HSI",
    "^HSCE": "^HSCE",
    # Japan
    "^N225": "^N225",
    # Europe
    "^FTSE": "^FTSE",
    "^GDAXI": "^GDAXI",
    "^FCHI": "^FCHI",
}

_INTERVAL_MAP: dict[Interval, str] = {
    Interval.ONE_MIN: "1m",
    Interval.FIVE_MIN: "5m",
    Interval.FIFTEEN_MIN: "15m",
    Interval.THIRTY_MIN: "30m",
    Interval.ONE_HOUR: "1h",
    Interval.DAILY: "1d",
    Interval.WEEKLY: "1wk",
    Interval.MONTHLY: "1mo",
}


class YFinanceIndexHistoricalFetcher(Fetcher):
    """Fetch index historical data from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "index_historical"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS,
        Exchange.XNAS,
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX,
        Exchange.XLON,
        Exchange.XPAR,
        Exchange.XETR,
    ]

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "change",
        "change_percent",
    ]
    data_start_date: ClassVar[str] = "1970-01-01"
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Does not provide amount (turnover). "
        "change and change_percent are computed from consecutive closes. "
        "Minute-level data limited to last 7 days."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        today = date.today()
        start = getattr(query, "start_date", None) or (today - timedelta(days=365))
        end = getattr(query, "end_date", None) or today
        interval = getattr(query, "interval", Interval.DAILY)
        symbol = getattr(query, "symbol", "")

        # Convert MIC-format index symbol to yfinance format
        yf_symbol = _INDEX_SYMBOL_MAP.get(symbol, symbol)

        return {
            "symbol": yf_symbol,
            "start": start.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),
            "interval": _INTERVAL_MAP.get(interval, "1d"),
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        ticker = yf.Ticker(params["symbol"])
        df = ticker.history(
            start=params["start"],
            end=params["end"],
            interval=params["interval"],
        )

        if df.empty:
            return []

        return df.reset_index()

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if raw_data is None or (hasattr(raw_data, "__len__") and len(raw_data) == 0):
            return []

        import pandas as pd

        df = raw_data
        if not isinstance(df, pd.DataFrame):
            return []

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        date_col = "date" if "date" in df.columns else "datetime"
        if date_col not in df.columns:
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            date_col = df.columns[0]

        results = []
        prev_close = None
        for _, row in df.iterrows():
            dt = row.get(date_col)
            if isinstance(dt, pd.Timestamp):
                dt = dt.date() if dt.hour == 0 and dt.minute == 0 else dt.to_pydatetime()

            close = _safe_float(row.get("close"))
            change = None
            change_pct = None
            if close is not None and prev_close is not None and prev_close != 0:
                change = close - prev_close
                change_pct = change / prev_close

            results.append(
                {
                    "date": dt,
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "close": close,
                    "volume": _safe_int(row.get("volume")),
                    "amount": None,
                    "change": change,
                    "change_percent": change_pct,
                }
            )
            prev_close = close

        return results


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


provider_registry.register_fetcher(YFinanceIndexHistoricalFetcher)
