"""YFinance fetcher for equity_historical."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Adjust, Exchange, Interval

# Map unifin intervals to yfinance intervals
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


class YFinanceEquityHistoricalFetcher(Fetcher):
    """Fetch equity historical data from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "equity_historical"
    supported_exchanges: ClassVar[list[Exchange]] = [
        # US
        Exchange.XNYS,
        Exchange.XNAS,
        Exchange.XASE,
        Exchange.ARCX,
        # China
        Exchange.XSHG,
        Exchange.XSHE,
        # Hong Kong
        Exchange.XHKG,
        # Japan
        Exchange.XJPX,
        # UK
        Exchange.XLON,
        # Europe
        Exchange.XPAR,
        Exchange.XAMS,
        Exchange.XETR,
        Exchange.XSWX,
        Exchange.XMIL,
        # APAC
        Exchange.XSES,
        Exchange.XASX,
        Exchange.XKRX,
        Exchange.XTAI,
        Exchange.XBOM,
        Exchange.XNSE,
        # Canada
        Exchange.XTSE,
    ]
    requires_credentials: ClassVar[list[str]] = []

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    data_start_date: ClassVar[str] = "1970-01-01"
    data_delay: ClassVar[str] = "15min"
    notes: ClassVar[str] = (
        "Does not provide amount, vwap, or turnover_rate. "
        "Minute-level data limited to last 7 days. "
        "Weekly/monthly aggregation may differ from exchange official data."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        """Convert unified query to yfinance parameters."""
        today = date.today()
        start = getattr(query, "start_date", None) or (today - timedelta(days=365))
        end = getattr(query, "end_date", None) or today
        interval = getattr(query, "interval", Interval.DAILY)
        adjust = getattr(query, "adjust", Adjust.NONE)

        yf_interval = _INTERVAL_MAP.get(interval, "1d")
        auto_adjust = adjust in (Adjust.FORWARD, Adjust.BACKWARD)

        return {
            "symbol": getattr(query, "symbol", ""),
            "start": start.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
            "interval": yf_interval,
            "auto_adjust": auto_adjust,
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        """Call yfinance to download data."""
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError(
                "yfinance is not installed. Install it with: pip install 'unifin[yfinance]'"
            )

        ticker = yf.Ticker(params["symbol"])
        df = ticker.history(
            start=params["start"],
            end=params["end"],
            interval=params["interval"],
            auto_adjust=params["auto_adjust"],
        )

        if df.empty:
            return []

        # Reset index to get date as a column
        df = df.reset_index()
        return df

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        """Transform yfinance DataFrame to unified format."""
        if raw_data is None or (hasattr(raw_data, "__len__") and len(raw_data) == 0):
            return []

        import pandas as pd

        df = raw_data
        if not isinstance(df, pd.DataFrame):
            return []

        # Normalize column names (yfinance uses Title Case)
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Determine date column
        date_col = "date" if "date" in df.columns else "datetime"
        if date_col not in df.columns:
            # date might be the index
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            date_col = "date" if "date" in df.columns else df.columns[0]

        results = []
        for _, row in df.iterrows():
            dt = row.get(date_col)
            if isinstance(dt, pd.Timestamp):
                dt = dt.date() if dt.hour == 0 and dt.minute == 0 else dt.to_pydatetime()

            results.append(
                {
                    "date": dt,
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "close": _safe_float(row.get("close")),
                    "volume": _safe_int(row.get("volume")),
                    "amount": None,  # yfinance doesn't provide amount
                    "vwap": None,
                    "turnover_rate": None,
                }
            )

        return results


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


# Register
provider_registry.register_fetcher(YFinanceEquityHistoricalFetcher)
